"""Package the verified Phase 11 network boot image and portable evidence."""
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path
from verify_phase11_cold_boot import verify
from record_boot_stage import verify_boot

ROOT = Path(__file__).resolve().parents[1]


def main():
    cold = verify(ROOT)
    boot = verify_boot()
    read = lambda n: json.loads((ROOT / n).read_text(encoding='utf-8'))
    ram = read('reports/phase11_acceptance.json')
    sd = read(cold['sd_deployment'])
    release = ROOT / 'release/phase11_sd_verified'
    release.mkdir(parents=True, exist_ok=True)
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    assert boot['outputs']['BOOT_udp.BIN'] == sd['boot_sha256']
    names = set(ram['files']) | set(cold['files']) | set(sd['files']) | {
        'reports/phase11_acceptance.json', 'reports/phase11_boot_acceptance.json',
        'reports/phase11_sd_deployment.json', 'scripts/verify_phase11_evidence.py',
        'README.md', 'PHASE11_STATUS.md', 'VERSION.json', 'docs/Phase11_GitHub版本说明.md'}
    with zipfile.ZipFile(release / 'phase11_sd_cold_boot_evidence.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for name in sorted(names):
            z.write(ROOT / name, name)
    with zipfile.ZipFile(release / 'ethernet_sd_card.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(ROOT / 'artifacts/BOOT_udp.BIN', 'BOOT.BIN')
        z.writestr('README.txt', 'Phase 11 network firmware; physical SD cold boot verified.\n'
                   'I16/Q16, 16384-point FFT, internal replay 125 MSPS, FFT clock 150 MHz.\n'
                   'BOOT.BIN SHA-256: ' + sd['boot_sha256'] + '\n')
        for p in sorted((ROOT / 'vendor/licenses').rglob('*')):
            if p.is_file():
                z.write(p, 'LICENSES/' + p.relative_to(ROOT / 'vendor/licenses').as_posix())
    tracked = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others',
                                      '--exclude-standard'], cwd=ROOT).decode('utf-8').split('\0')
    with zipfile.ZipFile(release / 'iq_analyzer_source.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for name in sorted(set(tracked)):
            if name and not name.startswith(('reports/', 'releases/')) and (ROOT / name).is_file():
                z.write(ROOT / name, name)
    for name in ('phase11_acceptance.json', 'phase11_boot_acceptance.json'):
        (release / name).write_bytes((ROOT / 'reports' / name).read_bytes())
    manifest = dict(build_id=ram['build_id'], hardware=ram['hardware'],
                    implementation_commit=read('VERSION.json')['source_commit'],
                    publication_source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip(),
                    board_tested=True, sd_installed=True, physical_cold_boot=True,
                    board_validation_type='RAM_JTAG_AND_SD_PHYSICAL_COLD_BOOT',
                    boot_sha256=sd['boot_sha256'], validation_scope=cold['scope'],
                    artifacts=ram['artifacts'],
                    files={p.name:dict(sha256=sha(p), bytes=p.stat().st_size)
                           for p in sorted(release.iterdir()) if p.is_file() and
                           p.name not in ('manifest.json', 'SHA256SUMS.txt')})
    (release / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    (release / 'SHA256SUMS.txt').write_text(''.join(sha(p)+'  '+p.name+'\n'
        for p in sorted(release.iterdir()) if p.is_file() and p.name != 'SHA256SUMS.txt'), encoding='utf-8')
    print('PHASE11_SD_RELEASE_PACKAGE_PASS', release)


if __name__ == '__main__':
    main()
