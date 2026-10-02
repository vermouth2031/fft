"""Validate Phase 7 evidence and create a hash-verified delivery archive."""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
from pathlib import Path
import zipfile

from package_release import check as check_build
from package_validated import check_board
from record_build_stage import sha, verify as verify_stage

ROOT = Path(__file__).resolve().parents[1]
BUILD_ID = "326086439b6ef3b8e85d1980b6744969"
DERIVED = {"frequency.json", "frequency.csv", "burst.json", "burst.csv"}
LARGE_STREAM_LIMIT = 100_000_000


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def require(value, message: str):
    if not value:
        raise ValueError(message)


def validate():
    check_build()
    verify_stage("hardware")
    verify_stage("simulation")
    board = check_board()
    require(board["hardware"]["build_id"] == BUILD_ID and len(board["cases"]) == 36,
            "Full Phase 7 board suite is missing")

    core = read(ROOT / "reports/core_validation.json")
    require(core["status"] == "PASS" and core["exact_fft_points"] == 524288,
            "Core simulation regression is incomplete")

    streaming = read(ROOT / "captures/phase7_streaming_1000_independent_redundant/validation.json")
    require(streaming["status"] == "PASS" and streaming["switches_requested"] == 1000,
            "1000-switch acceptance is incomplete")
    require(streaming["hardware"] == board["hardware"] and
            streaming["statistics"]["frequency_id_gaps"] == 0 and
            streaming["statistics"]["udp_missing_packet_count"] == 0 and
            streaming["diagnostics"]["result_queue_rejected"] == 0 and
            streaming["diagnostics"]["fft_output_windows"] == streaming["statistics"]["frequency_records"],
            "1000-switch conservation or loss gate failed")

    stability = []
    for seconds in (10, 60, 300):
        row = read(ROOT / f"captures/phase7_stability_{seconds}s/stability.json")
        require(row["status"] == "PASS" and row["duration_actual_s"] >= seconds and
                row["hardware"] == board["hardware"] and
                row["statistics"]["frequency_id_gaps"] == 0 and
                row["statistics"]["udp_missing_packet_count"] == 0 and
                row["diagnostics"]["result_queue_rejected"] == 0 and
                row["completed_windows"] == row["statistics"]["frequency_records"],
                f"{seconds}s streaming stability gate failed")
        stability.append(row)

    legacy = []
    for name in ("single", "dual", "chirp", "qpsk", "ofdm", "noise"):
        folder = ROOT / f"captures/phase7_legacy_{name}"
        row = read(folder / "capture.json")
        require(row["capture_complete"] and row["replay_readback_verified"] and
                row["throughput_conservation_valid"] and row["build_id"] == BUILD_ID and
                row["udp_missing_packet_count"] == 0 and row["frequency_records_missing"] == 0 and
                row["frequency_queue_dropped"] == 0 and row["burst_queue_dropped"] == 0 and
                sha(Path(row["vector"])) == row["vector_sha256"],
                f"Legacy compatibility case failed: {name}")
        legacy.append(row)

    board_hash = sha(ROOT / "reports/current_board_validation.json")
    sd = read(ROOT / "reports/sd_boot_update.json")
    require(sd["status"] == "PASS" and sd["sd_write_verified"] and sd["boot_medium_verified"] and
            sd["jtag_board_validation_sha256"] == board_hash and
            sd["image_sha256"] == sha(ROOT / "artifacts/BOOT_udp.BIN"),
            "SD installation is missing or stale")

    sd_hash = sha(ROOT / "reports/sd_boot_update.json")
    cold = read(ROOT / "reports/current_cold_boot_validation.json")
    require(cold["status"] == "PASS" and cold["epoch_before"] == 0 and
            not cold["jtag_used"] and not cold["program_download_performed"] and
            cold["hardware_before"] == board["hardware"] and
            cold["previous_board_validation_sha256"] == board_hash and
            cold["previous_sd_update_sha256"] == sd_hash,
            "Physical cold-boot evidence is missing or stale")
    return board, streaming, stability, legacy, sd, cold


def collect():
    selected: set[Path] = set()
    omitted = {}

    def add(path: Path, allow_large=True):
        path = path.resolve()
        if not path.is_file() or not path.is_relative_to(ROOT) or "__pycache__" in path.parts:
            return
        relative = path.relative_to(ROOT).as_posix()
        if path.name in DERIVED:
            omitted[relative] = {"reason": "derived_from_binary", "bytes": path.stat().st_size,
                                 "sha256": sha(path)}
        elif not allow_large and path.stat().st_size > LARGE_STREAM_LIMIT:
            omitted[relative] = {"reason": "large_stream_bound_by_report", "bytes": path.stat().st_size,
                                 "sha256": sha(path)}
        else:
            selected.add(path)

    for folder in ("rtl", "constraints", "scripts", "firmware", "tests", "host", "docs",
                   "vendor", "data", "config", ".github", "reports"):
        for path in (ROOT / folder).rglob("*"):
            add(path)
    for name in ("README.md", "CHANGELOG.md", "VERSION.json", "THIRD_PARTY_NOTICES.md",
                 "requirements.txt", ".gitattributes", ".gitignore", "Open_IQ_Monitor.cmd",
                 "Run_Network_Tests.cmd", "第二阶段优化实施方案.md", "第三阶段优化实施方案.md",
                 "第四阶段优化实施方案.md", "第五阶段优化实施方案.md", "项目工程总结.md"):
        add(ROOT / name)
    for path in (ROOT / "artifacts").glob("*"):
        add(path)

    capture_names = [p.name for p in (ROOT / "captures").iterdir() if p.is_dir() and
                     (p.name.startswith("phase7_") or p.name.startswith("sd_update_20261002_"))]
    for name in capture_names:
        for path in (ROOT / "captures" / name).rglob("*"):
            add(path, allow_large=False)

    simulation = read(ROOT / "reports/simulation_provenance.json")
    for name in simulation["evidence"]:
        add(ROOT / name)
    deployment = read(ROOT / "reports/current_deployment.json")
    add(Path(deployment["log"]))
    sd = read(ROOT / "reports/sd_boot_update.json")
    for path in Path(sd["output"]).rglob("*"):
        add(path)
    return selected, omitted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    archive = args.out.resolve()
    require(archive.is_relative_to(ROOT / "release") and archive.suffix.lower() == ".zip" and
            not archive.exists(), "Use a new ZIP path under release/")

    board, streaming, stability, legacy, sd, cold = validate()
    selected, omitted = collect()
    files = {p.relative_to(ROOT).as_posix(): {"bytes": p.stat().st_size, "sha256": sha(p)}
             for p in sorted(selected)}
    manifest = {
        "schema": "iq-phase7-streaming-delivery-v1",
        "created_at": datetime.datetime.now().astimezone().isoformat(),
        "hardware": board["hardware"],
        "board_cases": len(board["cases"]),
        "streaming_switches": streaming["switches_requested"],
        "stability_seconds": [row["duration_actual_s"] for row in stability],
        "legacy_compatibility_cases": len(legacy),
        "sd_boot_verified": sd["boot_medium_verified"],
        "physical_cold_boot_verified": True,
        "cold_boot_epoch_before": cold["epoch_before"],
        "files": files,
        "omitted_reconstructable_or_large_streams": omitted,
    }
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as package:
        for path in sorted(selected):
            package.write(path, path.relative_to(ROOT).as_posix())
        package.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    with zipfile.ZipFile(archive) as package:
        require(set(package.namelist()) == set(files) | {"manifest.json"}, "Archive entry set differs")
        require(json.loads(package.read("manifest.json")) == manifest, "Archive manifest differs")
        for name, record in files.items():
            with package.open(name) as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            require(digest == record["sha256"], "Archive SHA-256 mismatch: " + name)
    receipt = {"status": "PASS", "archive": str(archive), "bytes": archive.stat().st_size,
               "sha256": sha(archive), "file_count": len(files) + 1,
               "all_included_sha256_reverified": True, "omitted_count": len(omitted)}
    check_path = archive.with_name(archive.stem + "_check.json")
    check_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print("PHASE7_DELIVERY_PASS", json.dumps(receipt))


if __name__ == "__main__":
    main()
