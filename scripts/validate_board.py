"""Run current-hardware numerical acceptance without changing network settings."""
from __future__ import annotations
import argparse
import datetime
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
import iq_client
from record_build_stage import inputs, sha, verify as verify_stage
from package_release import check as check_build
from verify_board_capture import verify as verify_capture

VECTORS = ("zero", "tone_pos_fs4", "tone_neg_fs4", "burst_fs4",
           "qpsk_sps4", "qpsk_sps2", "short512_boundary", "negative_fullscale_dc")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", default="192.168.1.10")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--suite", choices=("smoke", "full"), default="full")
    args = parser.parse_args()
    check_build()
    deployment_path = ROOT / 'reports/current_deployment.json'
    deployment = json.loads(deployment_path.read_text(encoding='utf-8'))
    if deployment.get('status') != 'PASS' or deployment.get('board') != args.board:
        raise RuntimeError('Deploy this checked build with scripts/deploy_board.py before acceptance')
    if sha(Path(deployment['log'])) != deployment['log_sha256']:
        raise RuntimeError('Deployment log changed')
    for name, expected in deployment['artifacts'].items():
        if sha(ROOT / 'artifacts' / name) != expected:
            raise RuntimeError(f'Deployment artifact changed: {name}')
    args.out.mkdir(parents=True, exist_ok=False)
    artifact_hashes = {name: sha(ROOT / 'artifacts' / name) for name in
                       ('iq_analyzer.bit', 'iq_analyzer.xsa', 'iq_udp.elf', 'iq_sd.elf', 'zynq_fsbl.elf')}
    initial_sources = {folder: {p.relative_to(ROOT).as_posix(): sha(p)
                                for p in (ROOT / folder).glob("*") if p.is_file()}
                       for folder in ("rtl", "firmware", "host")}
    client = iq_client.Client(args.board)
    try:
        hardware = client.hardware_info("digital-zero")
        if client.read(8)[0] & 7:
            raise RuntimeError("Board is already running; stop its current capture before acceptance")
    finally:
        client.close()
    report = dict(status="RUNNING", created_at=datetime.datetime.now().astimezone().isoformat(),
                  board=args.board, hardware=hardware, suite=args.suite,
                  artifacts=artifact_hashes, source_files=initial_sources, cases=[],
                  deployment=deployment, deployment_sha256=sha(deployment_path),
                  input="PC-preloaded I16/Q16 RAM replay at nominal 100 MSPS",
                  metrology_calibrated=False, boot_medium_verified=False,
                  scope="New hardware version: finite exact numerical, snapshot and selected continuous acceptance")

    def save():
        (args.out / "board_validation.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def run_case(name, window, detector, seconds=0):
        label = f"{name}_{window}_{detector}" + (f"_{seconds}s" if seconds else "")
        folder = args.out / label
        vector = ROOT / "data/vectors" / (name + ".bin")
        print(f"BOARD_TEST_START {label}", flush=True)
        iq_client.capture(SimpleNamespace(board=args.board, port=5001, vector=str(vector),
                          out=str(folder), window=window, cyclic=bool(seconds), seconds=seconds or 1,
                          detector=detector, gap_min=32))
        row = verify_capture(folder, vector)
        (folder / "measurement_validation.json").write_text(
            json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        row['measurement_report_sha256'] = sha(folder / 'measurement_validation.json')
        report["cases"].append(row)
        save()
        print(f"BOARD_TEST_PASS {label}", flush=True)

    save()
    try:
        names = VECTORS if args.suite == "full" else ("burst_fs4", "qpsk_sps2")
        windows = ("rect", "hann") if args.suite == "full" else ("hann",)
        for detector in ("threshold", "digital-zero"):
            for window in windows:
                for name in names:
                    run_case(name, window, detector)
            if args.suite == "full":
                run_case("qpsk_sps4", "hann", detector, 10)
                run_case("qpsk_sps2", "hann", detector, 60)
        for folder, files in initial_sources.items():
            for name, expected in files.items():
                if sha(ROOT / name) != expected:
                    raise RuntimeError(f"Source changed during board acceptance: {name}")
        verify_stage("hardware")
        verify_stage("simulation")
        report["status"] = "PASS"
        report["finished_at"] = datetime.datetime.now().astimezone().isoformat()
        report["frequency_records"] = sum(r["frequency_records"] for r in report["cases"])
        report["burst_records"] = sum(r["burst_records"] for r in report["cases"])
        report["maximum_analysis_us"] = max(r["maximum_analysis_us"] for r in report["cases"])
        report["maximum_publish_us"] = max(r["maximum_publish_us"] for r in report["cases"])
        save()
        if args.suite == "full":
            (ROOT / "reports/current_board_validation.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("CURRENT_BOARD_ACCEPTANCE_PASS", args.out, flush=True)
    except Exception as error:
        report["status"] = "FAIL"
        report["error"] = str(error)
        save()
        raise


if __name__ == "__main__":
    main()
