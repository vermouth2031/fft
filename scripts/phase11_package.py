"""Package the exact Phase 11 build; never install an SD image or infer board tests."""
import hashlib
import json
import shutil
import stat
import subprocess
import zipfile
from pathlib import Path
from phase11_build_check import check
from record_boot_stage import verify_boot

ROOT = Path(__file__).resolve().parents[1]

def main():
    build = check()
    boot = verify_boot()
    release = ROOT / 'release'
    release.mkdir(exist_ok=True)
    net = release / 'ethernet_sd_card'
    net.mkdir(exist_ok=True)
    shutil.copyfile(ROOT / 'artifacts/BOOT_udp.BIN', net / 'BOOT.BIN')
    (net / 'README.txt').write_text(
        'Phase 11 network firmware. See PHASE11_STATUS.md for the exact validation scope.\n'
        'Packaging does not install the image. The existing SD keeps Phase 10 until explicitly updated.\n',
        encoding='utf-8')
    for p in (net / 'LICENSES').glob('*'):
        if p.is_file():
            p.chmod(stat.S_IREAD | stat.S_IWRITE)
    shutil.copytree(ROOT / 'vendor/licenses', net / 'LICENSES', dirs_exist_ok=True,
                    copy_function=shutil.copyfile)
    with zipfile.ZipFile(release / 'ethernet_sd_card.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for p in sorted(net.rglob('*')):
            if p.is_file():
                z.write(p, p.relative_to(net))
    manifest = dict(build=build, boot=boot, board_tested=False,
                    sd_installed=False, physical_cold_boot=False,
                    sd_state='PHASE10_UNCHANGED',
                    build_id=json.loads((ROOT / 'build/config/build_identity.json').read_text())['build_id'])
    acceptance = ROOT / 'reports/phase11_acceptance.json'
    if acceptance.exists():
        from verify_phase11_evidence import verify
        report = verify(ROOT)
        assert report['build_id'] == manifest['build_id']
        for name, expected in report['artifacts'].items():
            assert hashlib.sha256((ROOT / 'artifacts' / name).read_bytes()).hexdigest() == expected
        manifest.update(board_tested=True, board_validation_type='RAM_JTAG',
                        acceptance_sha256=hashlib.sha256(acceptance.read_bytes()).hexdigest())
        shutil.copyfile(acceptance, release / 'phase11_acceptance.json')
        with zipfile.ZipFile(release / 'phase11_acceptance_evidence.zip', 'w', zipfile.ZIP_DEFLATED) as z:
            names = set(report['files']) | {'reports/phase11_acceptance.json',
                     'PHASE11_STATUS.md', 'README.md', 'VERSION.json'}
            for name in sorted(names):
                z.write(ROOT / name, name)
    (release / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    # Git's file list omits generated build trees; include current bytes and new
    # source/document files even before the final local commit.
    names = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'],
                                    cwd=ROOT).decode('utf-8').split('\0')
    with zipfile.ZipFile(release / 'iq_analyzer_source.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for name in sorted(set(names)):
            p = ROOT / name
            if name and p.is_file():
                z.write(p, name)
    print('PHASE11_PACKAGE_PASS', release, 'board_tested=', manifest['board_tested'])

if __name__ == '__main__':
    main()
