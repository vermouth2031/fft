"""Check the portable IQ showcase with Python's standard library only.

No network, board, NumPy, FFT library or vendor installation is used. This checks
input hashes, source bindings, legal settings, exact time-domain amplitudes and
reference consistency. It does not recompute the AMD bit-accurate FFT oracle.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import struct

ROOT = Path(__file__).resolve().parents[1]
FS, N = 160_000_000, 16384
Q16 = 65536
PAYLOAD_KEYS = ("schema", "replay", "mode", "input_sha256", "sample_rate_hz",
                "detector", "windows", "snapshots", "software_reference_only")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def owned(root, relative):
    require(isinstance(relative, str) and relative and "\\" not in relative,
            f"Not a portable path: {relative!r}")
    require(not PureWindowsPath(relative).drive and not PurePosixPath(relative).is_absolute(),
            f"Absolute path: {relative!r}")
    result = (root / relative).resolve()
    require(result.is_relative_to(root.resolve()), f"Path escapes owner: {relative}")
    require(result.is_file(), f"Missing file: {relative}")
    return result


def numerical_digest(reference):
    value = {key: reference[key] for key in PAYLOAD_KEYS}
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def near(actual, expected, context):
    require(isinstance(actual, (int, float)) and math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-9),
            f"{context}: {actual} != {expected}")


def rounded(value, divisor):
    return (1 if value >= 0 else -1) * ((abs(value) + divisor // 2) // divisor)


def check_settings(request, actual, power):
    mode, profile, policy = (request[key] for key in ("detector", "threshold_profile", "threshold_policy"))
    require(mode in ("digital-zero", "threshold"), "Unknown detector")
    require(profile in ("legacy", "robust") and policy in ("fixed", "quiet-prefix"), "Unknown preset")
    require(request["window"] in ("rect", "hann") and request["cyclic"] is False, "Expected a finite window recipe")
    gap = request["gap_min"]
    require(type(gap) is int and 1 <= gap <= 65535, "Invalid digital-zero gap")
    require(type(request["seconds"]) is int and request["seconds"] > 0, "Invalid duration")
    overrides = {key: request.get(key) for key in ("ton", "toff", "kon", "koff")}
    require(all(value is None or type(value) is int for value in overrides.values()), "Noninteger override")
    require(mode != "digital-zero" or (profile == "legacy" and policy == "fixed" and all(v is None for v in overrides.values())),
            "Threshold options are forbidden for digital-zero")
    require(profile != "robust" or policy == "quiet-prefix", "robust requires quiet-prefix")
    expected = dict(ton=1048576, toff=262144, kon=16 if profile == "robust" else 8,
                    koff=8 if profile == "robust" else 32, max_burst_samples=1048576, mode=mode, gap_min=gap)
    if policy == "quiet-prefix":
        require(overrides["ton"] is None and overrides["toff"] is None, "Manual thresholds conflict with quiet-prefix")
        count = request["quiet_samples"]
        require(type(count) is int and 16 <= count <= len(power), "Invalid background prefix")
        # Integer rational arithmetic independently checks the ceil operation.
        energy = sum(power[:count])
        on_num, off_num, off_den = (3, 7, 4) if profile == "robust" else (4, 2, 1)
        expected["ton"] = max(2, (16 * energy * on_num + count - 1) // count)
        off = (16 * energy * off_num + count * off_den - 1) // (count * off_den)
        expected["toff"] = max(1, min(expected["ton"] - 1, off))
    else:
        require((overrides["ton"] is None) == (overrides["toff"] is None), "Supply both thresholds")
    expected.update({key: value for key, value in overrides.items() if value is not None})
    require(0 <= expected["toff"] < expected["ton"] < 2**36, "Invalid threshold ordering/range")
    require(all(1 <= expected[key] <= 65535 for key in ("kon", "koff")), "Invalid confirmation length")
    require(actual == expected, f"Applied detector does not match the recipe: {actual}")


def check_window(row, shot, index, power, context):
    require(row["window_id"] == index, f"{context}: window sequence")
    values = power[index * N:(index + 1) * N]
    require(row["energy"] == sum(values), f"{context}: exact raw energy")
    require(row["rms_uq16_16"] == math.isqrt(sum(values) << 18), f"{context}: exact Q16 RMS")
    require(row["peak_uq16_16"] == math.isqrt(max(values) << 32), f"{context}: exact Q16 peak")
    require(len(shot) == 1024 and all(type(v) is int and v >= 0 for v in shot), f"{context}: snapshot format")
    require(row["total"] >= 0 and row["peak_power"] == max(shot), f"{context}: snapshot peak")
    require(sum(shot) <= row["total"] <= sum(shot) * 16, f"{context}: snapshot/total bounds")
    low, high, peak = (row[key] for key in ("q_low", "q_high", "q_peak"))
    require(all(type(q) is int and 0 <= q < N for q in (low, high, peak)) and low <= high, f"{context}: bin bounds")
    require(shot[peak // 16] == row["peak_power"], f"{context}: peak bin and snapshot group")
    expected = {"f_peak_hz": rounded((peak - N // 2) * FS, N),
                "f_low_hz": rounded((low - N // 2) * FS, N),
                "f_high_hz": rounded((high - N // 2) * FS, N),
                "bandwidth_hz": rounded((high - low) * FS, N),
                "center_hz": rounded((low + high - N) * FS, 2 * N)}
    for key, value in expected.items():
        require(row[key] == (value if row["total"] else 0), f"{context}: {key}")


def check_gui_metrics(metrics, row):
    require(metrics["window_id"] == row["window_id"], "GUI window identifier")
    for gui, raw, divisor in (("rms_codes", "rms_uq16_16", Q16), ("peak_codes", "peak_uq16_16", Q16),
                              ("peak_mhz", "f_peak_hz", 1e6), ("bandwidth_mhz", "bandwidth_hz", 1e6),
                              ("center_mhz", "center_hz", 1e6)):
        near(metrics[gui], row[raw] / divisor, gui)
    flags = ["NO_POWER"] if not row["total"] else []
    if row["total"]:
        if row["q_low"] == row["q_high"]:
            flags.append("RESOLUTION_LIMITED")
        if row["q_low"] == 0 or row["q_high"] == N - 1:
            flags.append("EDGE_RISK")
    require(metrics["flags"] == flags, "GUI frequency status")


def check_pack(pack, root=ROOT):
    manifest = read_json(pack / "manifest.json")
    provenance = read_json(pack / "publication_provenance.json")
    require(manifest["schema"] == "iq-gui-showcase-pack-v1", "Manifest schema")
    require((pack / manifest["project"]).resolve() == root.resolve(), "Relative project root")
    require(manifest["sample_rate_hz"] == FS and manifest["fft_length"] == N, "Rate/FFT size")
    require(manifest["validation"]["new_board_test_performed"] is False, "Software-only provenance")
    require(manifest["publication"]["new_board_test_performed"] is False, "Publication scope")
    require(provenance["numerical_reference_values_changed"] is False, "Preserved numerical reference scope")
    cases = manifest["cases"]
    require(len(cases) == 22 and len({c["id"] for c in cases}) == 22, "Expected 22 distinct inputs")
    required_sources = {"tests/fft_reference.py", "tests/threshold_reference.py", "tests/frame_length_reference.py",
                        "host/threshold_config.py", "config/build_profile.json", "data/vectors/hann_u18_f17.mem"}
    binding_hashes, used_references, used_inputs = {}, set(), set()
    scenarios = windows = samples = snapshot_values = 0
    for case in cases:
        vector = owned(pack, case["file"])
        require(vector not in used_inputs, "Duplicate input filename")
        used_inputs.add(vector)
        require(digest(vector) == case["sha256"], f"IQ hash: {case['file']}")
        data = vector.read_bytes()
        require(len(data) == case["bytes"] == case["samples"] * 4 and case["samples"] in (N, 2 * N), "Input pair count")
        iq = list(struct.iter_unpack("<hh", data))
        power = [i * i + q * q for i, q in iq]
        stats = case["input_statistics"]
        require(stats["component_min"] == min(min(pair) for pair in iq) and stats["component_max"] == max(max(pair) for pair in iq), "Component range")
        require(stats["input_nonzero_samples"] == sum(p != 0 for p in power), "Nonzero count")
        for k in range(len(power) // N):
            part = power[k * N:(k + 1) * N]
            near(stats["window_rms"][k], math.sqrt(sum(part) / N), "Input window RMS")
            near(stats["window_peaks"][k], math.sqrt(max(part)), "Input window peak")
        if "source_sha256" in case:
            require(case["source_sha256"] == case["sha256"] and case["source_file"] == case["file"], "Historical byte identity")
        samples += len(power)
        spectral = {}
        for scenario in case["scenarios"]:
            check_settings(scenario["request"], scenario["applied_detector"], power)
            ref_path = owned(pack, scenario["reference_file"])
            require(ref_path not in used_references, "Reused scenario reference")
            used_references.add(ref_path)
            ref = read_json(ref_path)
            require(ref["schema"] == "iq-qualification-reference-v1" and ref["replay"] == "finite" and ref["software_reference_only"] is True, "Finite reference schema/scope")
            require(ref["sample_rate_hz"] == FS and ref["mode"] == scenario["request"]["window"] and ref["input_sha256"] == case["sha256"], "Reference input/window identity")
            require(ref["detector"] == scenario["applied_detector"] and ref["oracle"] == manifest["oracle"], "Reference detector/oracle identity")
            require(ref["binding_base"] == "repository", "Binding root")
            vector_binding = vector.relative_to(root).as_posix()
            require(required_sources | {vector_binding} <= ref["bindings"].keys(), "Missing numerical source/input binding")
            for name, expected in ref["bindings"].items():
                target = owned(root, name)
                if name not in binding_hashes:
                    binding_hashes[name] = digest(target)
                require(binding_hashes[name] == expected, f"Source binding: {name}")
            origin = provenance["references"][scenario["reference_file"]]
            require(ref["source_reference_sha256"] == origin["source_sha256"], "Original reference identity")
            require(numerical_digest(ref) == origin["numerical_payload_sha256"], "Original numerical values changed")
            require(len(ref["windows"]) == len(ref["snapshots"]) == len(power) // N, "Reference window count")
            for index, (row, shot) in enumerate(zip(ref["windows"], ref["snapshots"])):
                check_window(row, shot, index, power, scenario["reference_file"])
                snapshot_values += len(shot)
            check_gui_metrics(scenario["last_window"], ref["windows"][-1])
            spectral.setdefault(ref["mode"], ref["windows"])
            require(spectral[ref["mode"]] == ref["windows"], "Same input/window must have identical FFT reference")
            bursts = scenario["bursts"]
            require(scenario["burst_count"] == len(bursts) and scenario["last_burst"] == (bursts[-1] if bursts else None), "Burst count/last record")
            previous = 0
            for burst in bursts:
                start, end = burst["start"], burst["end"]
                require(previous <= start < end <= len(power), "Burst interval ordering/bounds")
                previous = end
                count = end - start
                require(burst["length_samples"] == count, "Burst length in samples")
                near(burst["length_us"], count / 160, "Burst length in microseconds")
                near(burst["rms_codes"], math.isqrt((sum(power[start:end]) << 32) // count) / Q16, "Exact burst RMS")
                near(burst["peak_codes"], math.isqrt(max(power[start:end]) << 32) / Q16, "Exact burst peak")
            scenarios += 1
            windows += len(ref["windows"])
        for mode, rows in spectral.items():
            for metric, row in zip(case["spectral_by_mode"][mode], rows):
                check_gui_metrics(metric, row)
    require(scenarios == 53 and len(used_references) == 53, "Expected 53 scenarios/references")
    require(used_references == set((pack / "参考结果").glob("*.json")), "Unexpected/orphan reference")
    require(used_inputs == set(pack.rglob("*.bin")), "Unexpected/orphan IQ file")
    hashes = {}
    for line in (pack / "IQ_SHA256SUMS.txt").read_text(encoding="utf-8-sig").splitlines():
        checksum, name = line.split("  ", 1)
        hashes[name] = checksum
    require(hashes == {c["file"]: c["sha256"] for c in cases}, "IQ_SHA256SUMS mismatch")
    favorites = read_json(pack / "favorites.json")["files"]
    require(len(favorites) == 4, "Expected four favorites")
    for entry in favorites:
        case = next(c for c in cases if c["id"] == entry["case_id"])
        require(entry["file"] == case["file"] and entry["sha256"] == case["sha256"], "Favorite identity")
    # Check publishable text as well as structured paths. Do not scan binary IQ.
    for path in pack.rglob("*"):
        if path.suffix in (".json", ".txt", ".md", ".py"):
            content = path.read_text(encoding="utf-8-sig")
            require(not re.search(r"[A-Za-z]:[\\/]|wxid_|\.codex[\\/]", content), f"Private absolute path: {path.relative_to(pack)}")
    return dict(schema="iq-showcase-portable-check-v1", status="PASS", iq_files=22, iq_pairs=samples,
                iq_bytes=samples * 4, scenarios=scenarios, reference_windows_checked=windows,
                snapshot_values_checked=snapshot_values, source_bindings_checked=len(binding_hashes),
                exact_time_domain_checks=True, amd_fft_recomputed=False, board_access=False,
                scope="Portable package integrity, legal settings, exact raw RMS/peak and preserved historical FFT reference consistency.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, default=ROOT / "examples/iq_showcase")
    parser.add_argument("--report", type=Path, help="Optional output JSON; no report is written by default")
    args = parser.parse_args()
    try:
        result = check_pack(args.pack.resolve())
    except (ValueError, KeyError, TypeError, OSError, StopIteration) as error:
        result = dict(schema="iq-showcase-portable-check-v1", status="FAIL", error=str(error), board_access=False)
    if args.report:
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
