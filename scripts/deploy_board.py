"""Deploy the checked design through JTAG and record its binary identity.

This programs FPGA/DDR only. It does not write QSPI or the physical SD card.
"""
from __future__ import annotations
import argparse
import datetime
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
from iq_client import Client
from package_release import check
from record_build_stage import sha
from phase4_identity import check_identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", default="192.168.1.10")
    parser.add_argument("--out", type=Path, help="Separate recovery deployment record; preserve existing campaign bindings")
    parser.add_argument("--xsdb", type=Path, default=Path(r"D:\VivadoMM\2026.1\Vitis\bin\xsdb.bat"))
    args = parser.parse_args()
    check()
    names = ("iq_analyzer.bit", "iq_analyzer.xsa", "iq_udp.elf", "ps7_init.tcl")
    before = {name: sha(ROOT / "artifacts" / name) for name in names}
    report = dict(status="RUNNING", board=args.board, method="JTAG FPGA and ARM DDR load",
                  boot_medium_written=False, started_at=datetime.datetime.now().astimezone().isoformat(),
                  artifacts=before)
    log = ROOT / "build/logs" / ("deploy_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".log")
    report["log"] = str(log)
    destination = args.out.resolve() if args.out else ROOT / "reports/current_deployment.json"
    if args.out:
        if not destination.is_relative_to(ROOT) or destination.exists():
            raise ValueError("Use a new project-local recovery record")
        destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with log.open("w", encoding="utf-8") as stream:
            result = subprocess.run([str(args.xsdb), str(ROOT / "scripts/program_board.tcl")],
                                    cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=180)
        if result.returncode != 0 or "Firmware started." not in log.read_text(encoding="utf-8", errors="replace"):
            raise RuntimeError(f"JTAG programming failed; inspect {log}")
        deadline = time.monotonic() + 30
        while True:
            client = Client(args.board)
            try:
                info = client.hardware_info("digital-zero")
                check_identity(info)
                state, errors = client.read(8)[0] & 7, client.read(0x60)[0]
                if state or errors:
                    raise RuntimeError(f"Loaded design is not idle/clean: state={state}, errors={errors}")
                break
            except (OSError, TimeoutError):
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.5)
            finally:
                client.close()
        after = {name: sha(ROOT / "artifacts" / name) for name in names}
        if before != after:
            raise RuntimeError("Artifacts changed while programming the board")
        report.update(status="PASS", hardware=info, log_sha256=sha(log),
                      finished_at=datetime.datetime.now().astimezone().isoformat())
    except Exception as error:
        report.update(status="FAIL", error=str(error))
        raise
    finally:
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
