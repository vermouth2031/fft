"""Archive completed Phase 12 builds and real-board tests with immutable byte hashes."""
import argparse
import datetime
import json
import shutil
from pathlib import Path
from phase12_build_check import check
from record_boot_stage import verify_boot
from verify_phase12_evidence import sha, verify

ROOT = Path(__file__).resolve().parents[1]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--finite', type=Path, required=True)
    p.add_argument('--dynamic', type=Path, nargs=3, required=True)
    p.add_argument('--references', type=Path, required=True)
    p.add_argument('--program-log', type=Path, required=True)
    p.add_argument('--final-state', type=Path, required=True)
    p.add_argument('--wideband', type=Path, required=True)
    p.add_argument('--baseline-wideband', type=Path, required=True)
    p.add_argument('--baseline-continuous', type=Path, required=True)
    a = p.parse_args()
    build = check()
    verify_boot()
    read = lambda path: path.read_text(encoding='utf-8')
    finite = json.loads(read(a.finite))
    assert finite['status'] == 'PASS'
    wide = json.loads(read(a.wideband))
    assert wide['status']=='PASS'
    dynamic = [json.loads(read(path)) for path in a.dynamic]
    assert all(report['status'] == 'PASS' for report in dynamic)
    archive = ROOT / 'reports/phase12_reference_evidence'
    archive.mkdir(exist_ok=False)
    mapping = {}
    def copy(source, relative):
        dest = archive / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        return dest.relative_to(ROOT).as_posix()
    for stage in ('simulation', 'hardware'):
        provenance = json.loads(read(ROOT / f'reports/{stage}_provenance.json'))
        for section in ('inputs', 'evidence'):
            for name, expected in provenance[section].items():
                assert sha(ROOT / name) == expected
                if name.startswith('build/'):
                    mapping[name] = copy(ROOT / name, name)
    groups = json.loads(read(ROOT / 'build/logs/core_parallel_manifest.json'))
    for g in groups['groups']:
        assert sha(Path(g['log'])) == g['sha256']
        copy(Path(g['log']), f"core_groups/{g['first_case']:02d}_{g['last_case']:02d}.txt")
    py = json.loads(read(ROOT / 'reports/phase9_python_validation.json'))
    for t in py['tests']:
        assert sha(ROOT / t['log']) == t['sha256']
        copy(ROOT / t['log'], t['log'])
    shutil.copytree(a.references.parent, archive / 'reference')
    index = json.loads(read(a.references))
    manifest = Path(index['manifest'])
    shutil.copytree(manifest.parent, archive / 'vectors')
    program = copy(a.program_log, 'program_board.txt')
    relative = lambda p: p.resolve().relative_to(ROOT).as_posix()
    files = set()
    for folder in ('rtl', 'constraints', 'config', 'scripts', 'firmware', 'host', 'tests'):
        files.update(p for p in (ROOT / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    for folder in (archive, a.finite.parent, a.wideband.parent, a.baseline_wideband.parent,
                   a.baseline_continuous.parent.parent, *(p.parent for p in a.dynamic)):
        files.update(p.resolve() for p in folder.rglob('*') if p.is_file())
    files.add(a.final_state.resolve())
    baseline = json.loads(read(ROOT / 'reports/phase12_baseline.json'))
    for stage in ('simulation', 'hardware'):
        provenance = json.loads(read(ROOT / f'reports/{stage}_provenance.json'))
        for section in ('inputs', 'evidence'):
            files.update(ROOT / name for name in provenance[section] if not name.startswith('build/'))
    files.update(ROOT / 'reports' / name for name in (
        'simulation_provenance.json', 'hardware_provenance.json', 'software_validation.json',
        'boot_provenance.json', 'phase12_baseline.json', 'phase12_initial_board.json',
        'phase12_programmed_board.json', 'phase12_comparison.json'))
    r = dict(status='RAM_JTAG_PASS', created_at=datetime.datetime.now().astimezone().isoformat(),
        hardware=finite['hardware'], build_id=finite['hardware']['build_id'],
        sd_installed=False, physical_cold_boot=False, sd_state='PHASE11_UNCHANGED',
        power_supply='USB_ONLY', build=build, baseline_commit='162250cac5f53dce8e46875858307158f4941c1d',
        finite_report=relative(a.finite), wideband_report=relative(a.wideband),
        baseline_wideband_report=relative(a.baseline_wideband),
        baseline_continuous_report=relative(a.baseline_continuous),
        dynamic_reports=[relative(p) for p in a.dynamic],
        final_state=relative(a.final_state), program_log=program, build_path_map=mapping,
        artifacts={p.name: sha(p) for p in (ROOT / 'artifacts').iterdir()
                   if p.suffix in ('.bit', '.xsa', '.elf', '.BIN', '.tcl')},
        maximum_analysis_us=max([finite['maximum_analysis_us']] + [c['measurement']['maximum_analysis_us'] for c in wide['cases']] + [d['hardware_max_latency_us'] for d in dynamic]),
        maximum_publish_us=max([finite['maximum_publish_us']] + [c['measurement']['maximum_publish_us'] for c in wide['cases']] + [d['hardware_max_publish_latency_us'] for d in dynamic]),
        files={relative(p): sha(p) for p in sorted(files)})
    target = ROOT / 'reports/phase12_acceptance.json'
    target.write_text(json.dumps(r, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    try:
        verify(ROOT)
    except Exception:
        r['status'] = 'FAIL'
        target.write_text(json.dumps(r, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        raise
    print('PHASE12_ACCEPTANCE_PASS', len(files), 'files', r['build_id'])

if __name__ == '__main__':
    main()
