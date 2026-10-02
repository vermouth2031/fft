"""Create and fully reverify the Phase 6 A2 delivery archive."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OMIT_DERIVED = {'frequency.json', 'frequency.csv', 'burst.json', 'burst.csv'}
LARGE_STREAM_LIMIT = 100_000_000


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def require(value, message):
    if not value:
        raise ValueError(message)


def validate():
    board = read(ROOT / 'reports/current_board_validation.json')
    matrix = read(ROOT / 'reports/phase6_a2_final_matrix.json')
    gui = read(ROOT / 'captures/phase6/candidate_a2_125_125_gui_r3/gui_validation.json')
    extended = read(ROOT / 'reports/current_extended_validation.json')
    sd = read(ROOT / 'reports/current_sd_validation.json')
    boot = read(ROOT / 'reports/sd_boot_update.json')
    cold = read(ROOT / 'reports/current_cold_boot_validation.json')
    require(all(x['status'] == 'PASS' for x in (board, matrix, gui, extended, sd, boot, cold)),
            'A required acceptance report has not passed')
    require(matrix['hardware'] == board['hardware'] == gui['hardware'] == cold['hardware_before'],
            'Acceptance evidence belongs to different builds')
    require(matrix['matrix_cases'] == 2020 and matrix['legacy_compatibility_cases'] == 192,
            'Final matrix cardinality differs')
    require(matrix['maximum_analysis_us'] <= 150 and matrix['maximum_publish_us'] <= 151 and
            matrix['minimum_widest_internal_obw_hz'] >= 115000000, 'Performance gate failed')
    require(sd['numerical']['status'] == 'PASS' and len(sd['numerical']['cases']) == 16,
            'SD application matrix is incomplete')
    require(boot['sd_write_verified'] and boot['boot_medium_verified'] and
            boot['image_sha256'] == sha(ROOT / 'artifacts/BOOT_udp.BIN'), 'SD boot image is not current')
    require(cold['epoch_before'] == 0 and not cold['jtag_used'] and not cold['program_download_performed'] and
            cold['previous_sd_update_sha256'] == sha(ROOT / 'reports/sd_boot_update.json'),
            'Physical cold-start evidence is missing or stale')
    return board, matrix, cold


def collect():
    selected = set()
    omitted = {}

    def add(path, allow_large=True):
        path = Path(path).resolve()
        if not path.is_file() or not path.is_relative_to(ROOT) or '__pycache__' in path.parts:
            return
        relative = path.relative_to(ROOT).as_posix()
        if path.name in OMIT_DERIVED:
            omitted[relative] = {'reason': 'derived_from_binary', 'bytes': path.stat().st_size, 'sha256': sha(path)}
        elif not allow_large and path.stat().st_size > LARGE_STREAM_LIMIT:
            omitted[relative] = {'reason': 'large_stream_bound_by_capture_report',
                                 'bytes': path.stat().st_size, 'sha256': sha(path)}
        else:
            selected.add(path)

    for folder in ('rtl', 'constraints', 'scripts', 'firmware', 'tests', 'host', 'docs',
                   'vendor', 'data', 'config', '.github'):
        for path in (ROOT / folder).rglob('*'):
            add(path)
    for name in ('README.md', 'CHANGELOG.md', 'VERSION.json', 'THIRD_PARTY_NOTICES.md',
                 'requirements.txt', '.gitattributes', '.gitignore', 'Open_IQ_Monitor.cmd',
                 'Run_Network_Tests.cmd', '第二阶段优化实施方案.md', '第三阶段优化实施方案.md',
                 '第四阶段优化实施方案.md', '第五阶段优化实施方案.md', '项目工程总结.md'):
        add(ROOT / name)
    for path in (ROOT / 'reports').rglob('*'):
        add(path)
    for path in (ROOT / 'artifacts/phase6/candidate_a2_125_125').rglob('*'):
        add(path)
    for path in (ROOT / 'build/phase6/candidate_a2_125_125').rglob('*'):
        add(path)
    for folder in ('build/maintenance/phase6_vector_update_20261001',
                   'build/maintenance/phase6_sd_boot_update_20261001'):
        for path in (ROOT / folder).rglob('*'):
            add(path)
    capture_roots = (
        'captures/phase6/candidate_a2_125_125',
        'captures/phase6/candidate_a2_125_125_extended_r2',
        'captures/phase6/candidate_a2_125_125_gui_r3',
        'captures/phase6/candidate_a2_125_125_ofdm_finite',
        'captures/phase6/candidate_a2_125_125_ofdm_signed',
        'captures/phase6/candidate_a2_125_125_ofdm_nyquist',
        'captures/phase6/candidate_a2_125_125_final_matrix',
        'captures/phase6/candidate_a2_125_125_sd_app_r2',
        'captures/phase6/candidate_a2_125_125_cold_boot')
    for folder in capture_roots:
        for path in (ROOT / folder).rglob('*'):
            add(path, allow_large=False)
    return selected, omitted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    archive = args.out.resolve()
    require(archive.is_relative_to(ROOT / 'release') and archive.suffix.lower() == '.zip' and not archive.exists(),
            'Use a new ZIP path under release/')
    board, matrix, cold = validate()
    selected, omitted = collect()
    files = {p.relative_to(ROOT).as_posix(): {'bytes': p.stat().st_size, 'sha256': sha(p)}
             for p in sorted(selected)}
    manifest = {'schema': 'iq-phase6-a2-delivery-v1',
        'created_at': datetime.datetime.now().astimezone().isoformat(),
        'hardware': board['hardware'], 'matrix_cases': matrix['matrix_cases'],
        'legacy_compatibility_cases': matrix['legacy_compatibility_cases'],
        'physical_cold_boot_verified': True, 'cold_boot_epoch_before': cold['epoch_before'],
        'files': files, 'omitted_reconstructable_or_large_streams': omitted}
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as package:
        for path in sorted(selected):
            package.write(path, path.relative_to(ROOT).as_posix())
        package.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    with zipfile.ZipFile(archive) as package:
        require(set(package.namelist()) == set(files) | {'manifest.json'}, 'Archive entry set differs')
        require(json.loads(package.read('manifest.json')) == manifest, 'Archive manifest differs')
        for name, record in files.items():
            with package.open(name) as stream:
                require(hashlib.file_digest(stream, 'sha256').hexdigest() == record['sha256'],
                        'Archive SHA-256 mismatch: ' + name)
    receipt = {'status': 'PASS', 'archive': str(archive), 'bytes': archive.stat().st_size,
               'sha256': sha(archive), 'file_count': len(files) + 1,
               'all_included_sha256_reverified': True, 'omitted_count': len(omitted)}
    archive.with_name(archive.stem + '_check.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('PHASE6_DELIVERY_PASS', json.dumps(receipt))


if __name__ == '__main__':
    main()
