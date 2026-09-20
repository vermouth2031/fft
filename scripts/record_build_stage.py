"""Record the exact source inputs and artifacts of a completed build stage."""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
from verify_fft_config import check as check_fft, XCI

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inputs(stage):
    check_fft()
    files = list((ROOT / "rtl").glob("*.sv"))
    files.append(XCI)
    if stage == "hardware":
        files += list((ROOT / "constraints").glob("*"))
        files += list((ROOT / "vendor/boards").rglob("*.xml"))
        files += [ROOT / "data/hann_u18_f17.mem"]
        files += [ROOT / "scripts" / name for name in
                  ("create_fft.tcl", "build_board.tcl", "rebuild_board.tcl", "finish_board.tcl")]
    elif stage == "simulation":
        files += [p for folder in ("tests", "host") for p in (ROOT / folder).glob("*")
                  if p.suffix in (".py", ".sv")]
        files += list((ROOT / "scripts").glob("sim_*.tcl"))
        files += list((ROOT / "data").glob("*.mem"))
        files += [ROOT / "data/golden_results.json", ROOT / "scripts/create_fft.tcl"]
        files += list((ROOT / 'data/vectors').glob('*.bin'))
    else:
        raise ValueError(stage)
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(set(files)) if p.is_file()}


def verify(stage):
    report = json.loads((ROOT / "reports" / f"{stage}_provenance.json").read_text(encoding="utf-8"))
    if report["inputs"] != inputs(stage):
        raise ValueError(f"{stage} evidence does not match current source inputs")
    for name, expected in report.get("artifacts", {}).items():
        if sha(ROOT / name) != expected:
            raise ValueError(f"{stage} artifact changed: {name}")
    if not report.get("evidence"):
        raise ValueError(f"{stage} provenance does not bind validation evidence")
    for name, expected in report["evidence"].items():
        if sha(ROOT / name) != expected:
            raise ValueError(f"{stage} validation evidence changed: {name}")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("simulation", "hardware"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        verify(args.stage)
    else:
        artifacts = {}
        if args.stage == "hardware":
            artifacts = {f"artifacts/{name}": sha(ROOT / "artifacts" / name)
                         for name in ("iq_analyzer.bit", "iq_analyzer.xsa")}
            evidence_paths = [ROOT / 'reports' / name for name in (
                'hardware_validation.json', 'timing_summary.rpt', 'utilization_flat.rpt',
                'cdc.rpt', 'drc.rpt', 'bus_skew.rpt', 'worst_paths.rpt')]
        else:
            evidence_paths = [ROOT / 'reports/core_validation.json']
            evidence_paths += [ROOT / 'build/logs' / (name + '.log') for name in (
                'sim_units', 'sim_builder', 'sim_measurements', 'sim_digital_burst',
                'sim_spectrum_edges', 'sim_core', 'sim_axi')]
        record = dict(stage=args.stage, captured_at=datetime.datetime.now().astimezone().isoformat(),
                      inputs=inputs(args.stage), artifacts=artifacts,
                      evidence={p.relative_to(ROOT).as_posix(): sha(p) for p in evidence_paths},
                      scope="Completed build stage; does not assert board validation")
        (ROOT / "reports" / f"{args.stage}_provenance.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{args.stage.upper()}_PROVENANCE_PASS")


if __name__ == "__main__":
    main()
