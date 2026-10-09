"""Archive completed Phase 10 tests and bind their sources and raw evidence."""
import argparse
import datetime
import hashlib
import json
import re
import shutil
from pathlib import Path
from package_release import check as check_build
from verify_phase10_evidence import verify

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--finite', type=Path, required=True)
    parser.add_argument('--dynamic', type=Path, nargs=3, required=True)
    parser.add_argument('--references', type=Path, required=True)
    parser.add_argument('--program-log', type=Path, required=True)
    parser.add_argument('--paired-baseline', type=Path, required=True)
    parser.add_argument('--repair-summary', type=Path, required=True)
    args = parser.parse_args()
    check_build()
    finite = json.loads(args.finite.read_text(encoding='utf-8'))
    if finite['status'] != 'PASS':
        raise ValueError('Finite board acceptance must pass before archiving')
    paired = json.loads(args.paired_baseline.read_text(encoding='utf-8'))
    repair = json.loads(args.repair_summary.read_text(encoding='utf-8'))
    if paired['status'] != 'PASS' or paired.get('completed_transitions', 0) < 1000:
        raise ValueError('Matching-board Phase 9 control must pass 1000 switches')
    if repair['status'] != 'VERIFIED_USB_RAM_JTAG_REPAIR':
        raise ValueError('Repair investigation has not been closed by board evidence')
    archive = ROOT / 'reports/phase10_reference_evidence'
    archive.mkdir(exist_ok=True)
    path_map = {}

    def copy(source, destination):
        source, destination = source.resolve(), destination.resolve()
        if not destination.is_relative_to(archive):
            raise ValueError('Archive destination escapes evidence directory')
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        path_map[str(source)] = destination.relative_to(ROOT).as_posix()

    index = json.loads(args.references.read_text(encoding='utf-8'))
    copy(args.references, archive / 'reference/index.json')
    manifest = Path(index['manifest'])
    copy(manifest, archive / 'vectors/manifest.json')
    copy(manifest.parent / 'spec.json', archive / 'vectors/spec.json')
    for row in index['cases']:
        reference = args.references.parent / row['reference']
        copy(reference, archive / 'reference' / row['reference'])
        vector = Path(row['vector'])
        copy(vector, archive / 'vectors' / vector.name)
    copy(args.program_log, archive / 'program_board.txt')
    groups = json.loads((ROOT / 'build/logs/core_parallel_manifest.json').read_text())
    for group in groups['groups']:
        source = Path(group['log'])
        if sha(source) != group['sha256']:
            raise ValueError(f'Core group log changed: {source}')
        copy(source, archive / 'core_groups' / f"cases_{group['first_case']:02d}_{group['last_case']:02d}.txt")
    python_tests = json.loads((ROOT / 'reports/phase9_python_validation.json').read_text())
    for test in python_tests['tests']:
        source = ROOT / test['log']
        if sha(source) != test['sha256']:
            raise ValueError(f'Python regression log changed: {source}')
        copy(source, archive / 'build' / source.relative_to(ROOT / 'build'))
    for stage in ('simulation', 'hardware'):
        provenance = json.loads((ROOT / f'reports/{stage}_provenance.json').read_text())
        for section in ('inputs', 'evidence'):
            for name, expected in provenance[section].items():
                source = ROOT / name
                if sha(source) != expected:
                    raise ValueError(f'Stage evidence changed: {name}')
                if name.startswith('build/'):
                    copy(source, archive / 'build' / Path(name).relative_to('build'))
    save(archive / 'path_map.json', path_map)
    utilization = (ROOT / 'reports/utilization_flat.rpt').read_text()
    labels = dict(lut='Slice LUTs', lut_memory='LUT as Memory', ff='Slice Registers',
                  bram='Block RAM Tile', dsp='DSPs', slice='Slice')
    resources = {}
    for key, label in labels.items():
        match = re.search(r'\|\s*' + re.escape(label) + r'\*?\s*\|\s*([\d.]+)', utilization)
        if not match:
            raise ValueError(f'Missing resource: {label}')
        resources[key] = float(match[1])
    baseline = json.loads((ROOT / 'reports/phase10_baseline.json').read_text())
    finite_path = args.finite.resolve().relative_to(ROOT).as_posix()
    dynamic_paths = [p.resolve().relative_to(ROOT).as_posix() for p in args.dynamic]
    artifacts = {p.name: sha(p) for p in (ROOT / 'artifacts').iterdir()
                 if p.suffix in ('.bit', '.xsa', '.elf', '.BIN', '.tcl')}
    report = dict(schema='phase10-acceptance-v1', status='RAM_JTAG_PASS',
        created_at=datetime.datetime.now().astimezone().isoformat(),
        baseline_commit=baseline['commit'], build_id=finite['hardware']['build_id'],
        hardware=finite['hardware'], deployment='RAM_JTAG',
        sd_installation='NOT_PERFORMED_ORIGINAL_SD_UNCHANGED',
        power_supply='USER_CONFIRMED_USB_ONLY',
        paired_baseline_report=args.paired_baseline.resolve().relative_to(ROOT).as_posix(),
        repair_summary=args.repair_summary.resolve().relative_to(ROOT).as_posix(),
        physical_cold_boot='NOT_PERFORMED', finite_report=finite_path,
        dynamic_reports=dynamic_paths, finite_cases=len(finite['cases']),
        exact_fft_simulation_points=1048576,
        exact_board_snapshot_values=sum(c['exact_snapshot_values'] for c in finite['cases']),
        maximum_analysis_us=finite['maximum_analysis_us'],
        maximum_publish_us=finite['maximum_publish_us'],
        resources=dict(baseline=baseline['resources'], current=resources),
        artifacts=artifacts, limitations=[
            '0 dB: known baseline missed detections remain outside this storage optimization',
            'Short edge burst with Hann retains the baseline frequency error',
            'RAM/JTAG acceptance does not qualify SD startup or physical cold boot',
            '125 MSPS describes internal replay processing, not unique IQ over Ethernet'])
    files = set()
    files.update((args.paired_baseline.resolve(), args.repair_summary.resolve()))
    # Preserve failures, reset evidence and the diagnostic controls alongside
    # final passing results. None of these older images qualifies the new image.
    for relative in repair['evidence_roots']:
        evidence = (ROOT / relative).resolve()
        if not evidence.is_relative_to((ROOT / 'reports').resolve()):
            raise ValueError(f'Investigation evidence escapes reports: {relative}')
        if evidence.is_dir():
            files.update(p for p in evidence.rglob('*') if p.is_file())
        elif evidence.is_file():
            files.add(evidence)
        else:
            raise ValueError(f'Missing investigation evidence: {relative}')
    for folder in ('rtl', 'constraints', 'config', 'scripts', 'firmware', 'host', 'tests'):
        files.update(p for p in (ROOT / folder).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts)
    for folder in (args.finite.parent, archive, *(p.parent for p in args.dynamic)):
        files.update(p for p in folder.rglob('*') if p.is_file())
    for stage in ('simulation', 'hardware'):
        provenance = json.loads((ROOT / f'reports/{stage}_provenance.json').read_text())
        for section in ('inputs', 'evidence'):
            files.update(ROOT / name for name in provenance[section] if not name.startswith('build/'))
    files.update(ROOT / 'reports' / name for name in (
        'hardware_validation.json', 'software_validation.json', 'core_validation.json',
        'simulation_provenance.json', 'hardware_provenance.json', 'boot_provenance.json',
        'phase10_equivalence.json', 'phase10_baseline.json', 'phase10_deployment.json', 'phase9_python_validation.json',
        'phase2_latency_validation.json', 'timing_summary.rpt', 'utilization_flat.rpt',
        'cdc.rpt', 'drc.rpt', 'bus_skew.rpt', 'methodology.rpt', 'worst_paths.rpt'))
    report['files'] = {p.resolve().relative_to(ROOT).as_posix(): sha(p) for p in sorted(files)}
    destination = ROOT / 'reports/phase10_acceptance.json'
    save(destination, report)
    try:
        verify(ROOT)
    except Exception:
        report['status'] = 'FAIL'
        save(destination, report)
        raise
    print('PHASE10_ACCEPTANCE_RECORDED', len(files), 'files', report['build_id'])


if __name__ == '__main__':
    main()
