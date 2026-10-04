"""Create a new, hash-verified Phase 8 r17 SD cold-boot archive."""
from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "releases/phase8_20261004_r17_ethernet_sd_boot"
TRIAL = ROOT / "releases/phase8_20261004_r17_sd_trial"
SMOKE = ROOT / "captures/phase8_20261004_r17_coldboot_smoke_12/validation.json"
LONG = ROOT / "captures/phase8_20261004_r17_coldboot_dma_1000/validation.json"
DEST = ROOT / "releases/phase8_20261004_r17_sd_verified"
BUILD_ID = "bae26b27515a813bbef3093a68992465"
BOOT_SHA256 = "1f07038642b609a01da5f6e6b67d09f4045181b2c3f3651ce09d994b4663f4f8"


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def check_test(report: dict, switches: int) -> None:
    require(report["status"] == "PASS", f"{switches}-switch report did not pass")
    require(report["switches_requested"] == switches and
            report["completed_transitions"] == switches,
            f"{switches}-switch transition count mismatch")
    hardware = report["hardware"]
    require(hardware["build_id"] == BUILD_ID and
            hardware["hardware_version"] == 0x00010004 and
            hardware["hardware_capabilities"] & 0xC == 0xC,
            f"{switches}-switch report uses unexpected hardware")
    require(report["effective_average_upload_mbps"] >= 8.0,
            f"{switches}-switch throughput is below 8 Mbit/s")
    require(report["hardware_max_latency_us"] <= 2000 and
            report["hardware_max_publish_latency_us"] <= 2000,
            f"{switches}-switch deadline failed")
    stats = report["statistics"]
    require(stats["frequency_id_gaps"] == 0 and
            stats["udp_missing_packet_count"] == 0 and
            stats["recovered_malformed_packets"] == 0,
            f"{switches}-switch record transport errors found")
    diagnostics = report["diagnostics"]
    require(diagnostics["issued_samples"] == diagnostics["accepted_samples"] ==
            diagnostics["fft_input_samples"] == diagnostics["fft_output_samples"],
            f"{switches}-switch sample conservation failed")
    require(diagnostics["input_rejected"] == 0 and
            diagnostics["result_queue_rejected"] == 0 and
            diagnostics["input_underreads"] == 0,
            f"{switches}-switch diagnostics reported errors")
    final = report["final_status"]
    require(final["dma"]["active"] is False and
            final["dma"]["error"] is False and
            final["dma"]["errors"] == 0 and
            final["write_rejected"] == 0 and
            final["stream_errors"] == 0,
            f"{switches}-switch final hardware status reported errors")


def main() -> None:
    require(CANDIDATE.is_dir(), "Candidate release directory is missing")
    require(not DEST.exists(), f"Refusing to overwrite existing archive: {DEST}")
    smoke, long = read(SMOKE), read(LONG)
    check_test(smoke, 12)
    check_test(long, 1000)

    candidate_manifest = read(CANDIDATE / "manifest.json")
    candidate_boot = CANDIDATE / "BOOT.BIN"
    card_boot = TRIAL / "card_after/BOOT.BIN"
    card_before = TRIAL / "card_before/BOOT.BIN"
    write_record = read(TRIAL / "write_record.json")
    require(sha(candidate_boot) == BOOT_SHA256 and sha(card_boot) == BOOT_SHA256,
            "Candidate image and SD read-back image do not match expected SHA-256")
    require(write_record["new_boot_sha256"].lower() == BOOT_SHA256 and
            write_record["old_boot_sha256"].lower() == sha(card_before),
            "SD write record hashes do not match preserved card images")
    require(candidate_manifest["build_id"] == BUILD_ID and
            candidate_manifest["files"]["BOOT.BIN"] == BOOT_SHA256,
            "Candidate manifest does not identify the expected image")

    shutil.copytree(CANDIDATE, DEST)
    reports = DEST / "reports"
    (reports / "cold_boot_smoke").mkdir(parents=True)
    (reports / "cold_boot_dma_1000").mkdir(parents=True)
    (reports / "sd_backup").mkdir(parents=True)
    shutil.copy2(SMOKE, reports / "cold_boot_smoke/validation.json")
    shutil.copy2(LONG, reports / "cold_boot_dma_1000/validation.json")
    shutil.copy2(LONG.parent / "progress.json", reports / "cold_boot_dma_1000/progress.json")
    shutil.copy2(TRIAL / "write_record.json", reports / "sd_write_record_at_install.json")
    shutil.copy2(TRIAL / "manifest.json", reports / "sd_trial_manifest.json")
    shutil.copy2(card_before, reports / "sd_backup/BOOT_before_update.BIN")
    (reports / "r17_candidate_manifest.json").write_text(
        json.dumps(candidate_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    cold_boot = {
        "schema": "phase8-sd-cold-boot-validation-v1",
        "status": "PASS",
        "confirmation_source": "User confirmed the updated SD card was reinstalled and the board was fully power-cycled until its power indicator went out, then powered on again.",
        "confirmed_at": datetime.datetime.now().astimezone().isoformat(),
        "sd_image_sha256": BOOT_SHA256,
        "board": long["board"],
        "host_source_ip": "192.168.1.20",
        "hardware": long["hardware"],
        "smoke_report": "reports/cold_boot_smoke/validation.json",
        "dma_acceptance_report": "reports/cold_boot_dma_1000/validation.json",
        "sd_write_record": "reports/sd_write_record_at_install.json",
        "preserved_pre_update_image": "reports/sd_backup/BOOT_before_update.BIN",
        "acceptance": {
            "smoke_switches": smoke["completed_transitions"],
            "dma_switches": long["completed_transitions"],
            "average_upload_mbps": long["effective_average_upload_mbps"],
            "hardware_max_latency_us": long["hardware_max_latency_us"],
            "hardware_max_publish_latency_us": long["hardware_max_publish_latency_us"],
            "frequency_id_gaps": long["statistics"]["frequency_id_gaps"],
            "udp_missing_packets": long["statistics"]["udp_missing_packet_count"],
            "dma_errors": long["final_status"]["dma"]["errors"],
        },
    }
    (reports / "cold_boot_validation.json").write_text(
        json.dumps(cold_boot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (DEST / "README.md").write_text(
        "# Phase 8 r17 SD verified release\n\n"
        "This independent release retains the r17 PC UDP sender and the SD boot image. "
        "The SD card was written and read back by SHA-256, installed in the Zybo Z7-20, "
        "and cold-booted after a full power removal. The resulting board identity and "
        "12-switch smoke test plus 1000-switch DMA acceptance are recorded under `reports/`.\n\n"
        f"Build ID: `{BUILD_ID}`\n\n"
        f"BOOT.BIN SHA-256: `{BOOT_SHA256}`\n\n"
        "The prior card image is retained at `reports/sd_backup/BOOT_before_update.BIN`. "
        "The r17 candidate directory and its Git tag remain unchanged.\n",
        encoding="utf-8")

    manifest = dict(candidate_manifest)
    manifest.update({
        "version": "phase8_20261004_r17_sd_verified",
        "archived_at": datetime.datetime.now().astimezone().isoformat(),
        "target": "Zynq Ethernet streaming over physically cold-booted SD",
        "physical_sd_written": True,
        "cold_boot_status": "PASS",
        "cold_boot_evidence": "reports/cold_boot_validation.json",
        "cold_boot_smoke_switches": 12,
        "cold_boot_dma_switches": 1000,
        "measured_cold_boot_1000_switch_average_mbps": long["effective_average_upload_mbps"],
        "sd_previous_boot_sha256": sha(card_before),
        "source_candidate": "phase8_20261004_r17_ethernet_sd_boot",
        "files": {},
    })
    manifest_path = DEST / "manifest.json"
    files = {
        path.relative_to(DEST).as_posix(): sha(path)
        for path in sorted(DEST.rglob("*"))
        if path.is_file() and path != manifest_path
    }
    manifest["files"] = files
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")

    for name, digest in files.items():
        require(sha(DEST / name) == digest, f"Archived file hash mismatch: {name}")
    written_manifest = read(manifest_path)
    require(written_manifest["cold_boot_status"] == "PASS" and
            written_manifest["files"] == files,
            "Verified release manifest read-back mismatch")
    print(json.dumps({
        "status": "PASS",
        "archive": str(DEST),
        "file_count": len(files) + 1,
        "boot_sha256": sha(DEST / "BOOT.BIN"),
        "manifest_sha256": sha(manifest_path),
        "all_file_hashes_reverified": True,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
