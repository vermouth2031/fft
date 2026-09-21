"""Record the exact source inputs and artifacts of a completed build stage."""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import subprocess
import sys
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
                  ("create_fft.tcl", "build_board.tcl", "rebuild_board.tcl", "finish_board.tcl", "phase3_replication_hook.tcl")]
    elif stage == "simulation":
        files += [p for folder in ("tests", "host") for p in (ROOT / folder).glob("*")
                  if p.suffix in (".py", ".sv")]
        files += list((ROOT / "scripts").glob("sim_*.tcl"))
        files += list((ROOT / "data").glob("*.mem"))
        files += [ROOT / "data/golden_results.json", ROOT / "scripts/create_fft.tcl"]
        files += list((ROOT / 'data/vectors').glob('*.bin'))
        files += [p for p in (ROOT / 'data/qualification').rglob('*') if p.suffix in ('.json', '.bin')]
        files += [ROOT / 'scripts' / name for name in
                  ('validate_measurements.py', 'verify_board_capture.py', 'qualification_capture.py', 'analyze_latency.py', 'run.ps1')]
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


def refresh_qualification():
    """Rerun changed Python qualification tools while retaining unchanged RTL runs.

This deliberately refuses changes to RTL, testbenches, FFT, input fixtures,
host/protocol code or simulation commands. Those still require the full Sim.
"""
    path = ROOT / 'reports/simulation_provenance.json'
    previous = json.loads(path.read_text(encoding='utf-8'))
    current = inputs('simulation')
    changed = {name for name in set(current) | set(previous['inputs'])
               if current.get(name) != previous['inputs'].get(name)}
    allowed = {'scripts/validate_measurements.py', 'tests/test_qualification.py'}
    if not changed or not changed <= allowed:
        raise ValueError(f'Scoped qualification refresh not allowed for {sorted(changed)}; run full Sim')
    for section in ('evidence', 'artifacts'):
        for name, expected in previous.get(section, {}).items():
            if sha(ROOT/name) != expected:
                raise ValueError(f'Previous validation evidence changed: {name}')
    output = ROOT/'build'/('qualification_refresh_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    output.mkdir(parents=True, exist_ok=False)
    before = output/'simulation_provenance_before.json'
    before.write_bytes(path.read_bytes())
    old_test = output/'qualification_tool_validation_before.json'
    old_test.write_bytes((ROOT/'reports/qualification_tool_validation.json').read_bytes())
    log = output/'qualification_tests.log'
    with log.open('w', encoding='utf-8') as stream:
        result = subprocess.run([sys.executable, str(ROOT/'tests/test_qualification.py')],
                                cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode or 'QUALIFICATION_TOOLS_PASS' not in log.read_text(encoding='utf-8'):
        raise ValueError(f'Qualification tests failed: {log}; provenance was not refreshed')
    if inputs('simulation') != current:
        raise ValueError('Source changed during qualification tests')
    record = dict(previous, inputs=current,
                  captured_at=datetime.datetime.now().astimezone().isoformat())
    record['evidence'] = dict(previous['evidence'])
    record['evidence']['reports/qualification_tool_validation.json'] = sha(ROOT/'reports/qualification_tool_validation.json')
    for file in (before, old_test, log, Path(__file__).resolve()):
        record['evidence'][file.relative_to(ROOT).as_posix()] = sha(file)
    record['qualification_refresh'] = dict(changed_inputs=sorted(changed),
        scope='Reran qualification Python tests; all HDL sources, inputs, simulator commands and HDL result logs unchanged',
        previous_provenance=str(before.relative_to(ROOT)), previous_provenance_sha256=sha(before))
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    verify('simulation')
    print('QUALIFICATION_REFRESH_PASS', output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("simulation", "hardware"))
    parser.add_argument("--check", action="store_true")
    parser.add_argument('--refresh-qualification', action='store_true')
    args = parser.parse_args()
    if args.refresh_qualification:
        if args.stage != 'simulation' or args.check:
            parser.error('--refresh-qualification requires simulation and cannot be combined with --check')
        refresh_qualification()
    elif args.check:
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
            evidence_paths = [ROOT / 'reports/core_validation.json',
                              ROOT / 'reports/qualification_tool_validation.json',
                              ROOT / 'reports/phase2_latency_validation.json',
                              ROOT / 'build/vivado/iq_analyzer.sim/sim_1/behav/xsim/latency_events.csv']
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
