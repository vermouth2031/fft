"""Verify a saved board capture against integer references, without board access.

Frequency checks support the standard golden vectors. Cyclic burst verification
requires a quiet seam; unsupported input patterns fail explicitly.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "host"), str(ROOT / "tests")]
import numpy as np
from iq_client import decode_record
from generate_iq_vectors import burst_reference
from frame_length_reference import reference_digital_zero

FREQUENCY_FIELDS = {
    "total_spectrum_power": "total", "peak_spectrum_power": "peak_power",
    "q_peak": "q_peak", "q_low": "q_low", "q_high": "q_high",
    "peak_hz": "f_peak_hz", "low_hz": "f_low_hz", "high_hz": "f_high_hz",
    "bandwidth_hz": "bandwidth_hz", "bandcenter_hz": "center_hz",
    "raw_energy": "energy",
}


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def burst_expectations(iq, mode, gap, maximum, finish):
    if mode == "digital-zero":
        return reference_digital_zero(iq[:, 0], iq[:, 1], gap_min=gap,
                                      max_burst=maximum, finish=finish)
    require(mode == "threshold", "Unknown detector mode")
    require(maximum == 1048576, "Threshold verifier currently covers default maximum only")
    # The default threshold model is independently maintained with the vectors.
    result = []
    power = iq[:, 0].astype(np.int64) ** 2 + iq[:, 1].astype(np.int64) ** 2
    for row in burst_reference(iq):
        if not row["complete"] and not finish:
            continue
        start = row["start"]
        end = row.get("end_exclusive", len(iq))
        values = power[start:end]
        energy = int(values.sum())
        result.append(dict(start_sample=start, end_sample=end,
                           length_samples=end-start, energy=energy,
                           peak_q16=math.isqrt(int(values.max()) << 32),
                           rms_q16=math.isqrt((energy << 32) // len(values)),
                           flags=0 if row["complete"] else 256))
    return result


def verify(folder, vector=None):
    folder = Path(folder)
    meta = json.loads((folder / "capture.json").read_text(encoding="utf-8-sig"))
    require(meta.get("capture_complete") is True, "Capture is incomplete")
    require(meta.get("replay_readback_verified") is True, "Input readback not verified")
    for field in ("error_status", "frequency_queue_dropped", "burst_queue_dropped",
                  "udp_missing_packet_count", "frequency_records_missing",
                  "burst_records_missing", "duplicate_frequency_records"):
        require(meta.get(field) == 0, f"Nonzero or absent integrity field: {field}")
    require(meta.get("frequency_sequence_valid") is True, "Sequence integrity failed")
    vector = Path(vector or meta["vector"])
    require(digest(vector) == meta["vector_sha256"], "Input vector hash mismatch")
    iq = np.fromfile(vector, dtype="<i2").reshape(-1, 2)
    require(len(iq) in (8192, 16384, 24576, 32768), "Invalid replay length")
    accepted = meta["input_samples"]
    require(accepted > 0 and accepted % 8192 == 0, "Invalid accepted sample count")
    if not meta.get("cyclic"):
        require(accepted == len(iq), "Finite capture length mismatch")
    rate = meta.get("sample_rate_hz", 100000000)
    require(rate == 100000000, "This oracle is calibrated to the 100 MSPS baseline")
    mode = meta.get("detector_mode", "threshold")
    gap = meta.get("gap_min", 32)
    maximum = meta.get("max_burst_samples", 1048576)
    golden_path = ROOT / "data/golden_results.json"
    golden = json.loads(golden_path.read_text(encoding="utf-8"))["cases"]
    config_id = None
    previous_tick = None
    maximum_latency = 0
    count = 0
    chosen = None
    with (folder / "frequency.bin").open("rb") as stream:
        while raw := stream.read(128):
            actual = decode_record(raw, "frequency")
            if chosen is None:
                chosen = next((g for g in golden
                               if g["name"] == vector.stem and g["mode"] == actual["window"]), None)
                require(chosen is not None, "Vector has no reviewed spectral oracle")
                original = ROOT / "data/vectors" / (chosen["name"] + ".bin")
                require(digest(original) == digest(vector), "Named vector differs from spectral oracle input")
                config_id = actual["config_id"]
                if 'config_id' in meta:
                    require(config_id == meta['config_id'], 'Capture configuration metadata mismatch')
            expected = chosen["windows"][count % len(chosen["windows"])]
            require(actual["id"] == count == actual["sequence"], f"Frequency sequence {count}")
            require(actual["first_sample"] == count * 8192, "Sample position mismatch")
            require(actual["epoch"] == meta["epoch"] and actual["config_id"] == config_id, "Epoch/config mismatch")
            require(actual["sample_rate_hz"] == rate and actual["fft_length"] == 8192, "Rate/FFT mismatch")
            require(actual["window"] == chosen["mode"], "Window changed")
            for target, source in FREQUENCY_FIELDS.items():
                require(actual[target] == expected[source], f"Window {count} {target}: {actual[target]} != {expected[source]}")
            require(actual["peak_codes"] * 65536 == expected["peak_uq16_16"], "Peak amplitude mismatch")
            require(actual["rms_codes"] * 65536 == expected["rms_uq16_16"], "RMS amplitude mismatch")
            flags = (1 if not expected["total"] else 0)
            if expected["total"]:
                flags |= 32 if expected["q_low"] == expected["q_high"] else 0
                flags |= 16 if expected["q_low"] == 0 or expected["q_high"] == 8191 else 0
            require(actual["flags_raw"] == flags, f"Frequency flags {count}")
            latency = actual["latency_cycles"]
            require(0 < latency <= rate * .002, "Analysis deadline exceeded")
            require(actual["done_tick"] - actual["start_tick"] == latency, "Latency timestamp mismatch")
            if previous_tick is not None:
                require(actual["start_tick"] - previous_tick == 8192, "Source timing discontinuity")
            previous_tick = actual["start_tick"]
            maximum_latency = max(maximum_latency, latency)
            count += 1
    require(count == meta["completed_windows"] == meta["frequency_records"] == accepted // 8192,
            "Frequency count mismatch")
    require(maximum_latency == meta["hardware_max_latency_cycles"], "Maximum latency mismatch")
    require(0 < meta["hardware_max_publish_latency_cycles"] <= rate * .002, "Publication deadline exceeded")

    if meta.get("cyclic"):
        quiet = max(gap if mode == "digital-zero" else 47, 16)
        require(not np.any(iq[:quiet]) and not np.any(iq[-quiet:]),
                "Cyclic burst oracle requires a quiet seam; use a dedicated reference for this input")
    whole, remainder = divmod(accepted, len(iq))
    full_refs = burst_expectations(iq, mode, gap, maximum, finish=not meta.get("cyclic"))
    tail_refs = burst_expectations(iq[:remainder], mode, gap, maximum, finish=True) if remainder else []
    burst_count = 0
    with (folder / "burst.bin").open("rb") as stream:
        for period in range(whole + bool(remainder)):
            refs = full_refs if period < whole else tail_refs
            offset = period * len(iq)
            for expected in refs:
                actual = decode_record(stream.read(64), "burst")
                require(actual["id"] == burst_count == actual["sequence"], "Burst sequence mismatch")
                require(actual["epoch"] == meta["epoch"] and actual["config_id"] == config_id, "Burst epoch/config mismatch")
                require(actual["sample_rate_hz"] == rate, "Burst sampling rate mismatch")
                require(actual["start_sample"] == offset + expected["start_sample"], "Burst start mismatch")
                require(actual["end_sample_exclusive"] == offset + expected["end_sample"], "Burst end mismatch")
                for target, source in (("length_samples", "length_samples"), ("raw_energy", "energy"),
                                       ("flags_raw", "flags")):
                    require(actual[target] == expected[source], f"Burst {burst_count}: {target}")
                require(actual["peak_codes"] * 65536 == expected["peak_q16"], "Burst peak mismatch")
                require(actual["rms_codes"] * 65536 == expected["rms_q16"], "Burst RMS mismatch")
                burst_count += 1
        require(not stream.read(1), "Unexpected trailing burst records")
    require(burst_count == meta["burst_records"], "Burst count mismatch")

    snapshot_count = 0
    shot_file = folder / "snapshot.json"
    if shot_file.exists():
        shot = json.loads(shot_file.read_text(encoding="utf-8"))
        if shot and "power" in shot:
            require(0 <= shot['window_id'] < meta['completed_windows'], 'Snapshot window is outside this capture')
            case = golden.index(chosen)
            packed = np.array([int(x, 16) for x in (ROOT / "data/golden_fft.mem").read_text().splitlines()],
                              dtype=np.int64).reshape(len(golden), 4, 8192)
            values = packed[case, shot["window_id"] % 4]
            re = ((values & 0xffffff) ^ 0x800000) - 0x800000
            im = (((values >> 24) & 0xffffff) ^ 0x800000) - 0x800000
            expected_power = np.fft.fftshift(re * re + im * im).reshape(1024, 8).max(axis=1)
            require(np.array_equal(expected_power, shot["power"]), "Hardware snapshot mismatch")
            snapshot_count = 1024
    return dict(status="PASS", scope="Exact frequency, burst, flags, sequences, timestamps and available snapshot",
                folder=str(folder.resolve()), detector_mode=mode, gap_min=gap,
                hardware_version=meta.get("hardware_version"),
                frequency_records=count, burst_records=burst_count,
                exact_snapshot_values=snapshot_count,
                maximum_analysis_us=maximum_latency * 1e6 / rate,
                maximum_publish_us=meta["hardware_max_publish_latency_cycles"] * 1e6 / rate,
                input_sha256=digest(vector), golden_sha256=digest(golden_path),
                files={name: digest(folder / name) for name in ("capture.json", "frequency.bin", "burst.bin", 'snapshot.bin', 'snapshot.json')
                       if (folder / name).is_file()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--vector", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    out = args.out or args.capture / "measurement_validation.json"
    try:
        report = verify(args.capture, args.vector)
    except Exception as error:
        out.write_text(json.dumps(dict(status="FAIL", error=str(error)), indent=2), encoding="utf-8")
        raise
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
