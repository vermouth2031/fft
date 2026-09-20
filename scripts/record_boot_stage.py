"""Bind Bootgen outputs to their exact FSBL, bitstream and application inputs."""
from pathlib import Path
import argparse
import datetime
import json
from record_build_stage import ROOT, sha, verify as verify_stage

INPUTS = ("zynq_fsbl.elf", "iq_analyzer.bit", "iq_sd.elf", "iq_udp.elf")
OUTPUTS = ("BOOT_sd.BIN", "BOOT_udp.BIN", "BOOT.BIN")


def verify_boot():
    row = json.loads((ROOT / "reports/boot_provenance.json").read_text(encoding="utf-8"))
    for section in ("inputs", "outputs"):
        for name, value in row[section].items():
            if sha(ROOT / "artifacts" / name) != value:
                raise ValueError(f"Boot image/source changed: {name}; rerun Package")
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        verify_boot()
    else:
        verify_stage("hardware")
        paths = [ROOT / "artifacts" / name for name in INPUTS]
        newest = max(p.stat().st_mtime for p in paths)
        for name in OUTPUTS:
            if (ROOT / "artifacts" / name).stat().st_mtime < newest:
                raise ValueError(f"Boot output predates input: {name}")
        row = dict(created_at=datetime.datetime.now().astimezone().isoformat(),
                   inputs={name: sha(ROOT / "artifacts" / name) for name in INPUTS},
                   outputs={name: sha(ROOT / "artifacts" / name) for name in OUTPUTS})
        if row["outputs"]["BOOT.BIN"] != row["outputs"]["BOOT_sd.BIN"]:
            raise ValueError("Default BOOT.BIN is not the SD-test image")
        (ROOT / "reports/boot_provenance.json").write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    print("BOOT_PROVENANCE_PASS")


if __name__ == "__main__":
    main()

