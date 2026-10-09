"""Record/check Phase 10 SD installation and user-confirmed physical cold boot.

The record command runs only after the network-only tests finish. Neither mode
uses JTAG, downloads software or resets the board. Check works in a Git export.
"""
import argparse
import datetime
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = 'reports/phase10_boot_acceptance.json'


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def verify(root):
    root = root.resolve()

    def path(name):
        p = (root / name).resolve()
        require(p.is_relative_to(root), 'Evidence escapes project')
        return p

    def read(name):
        return json.loads(path(name).read_text(encoding='utf-8'))

    from verify_phase10_evidence import verify as verify_ram
    ram = verify_ram(root)
    r = read(REPORT)
    require(r['status'] == 'SD_PHYSICAL_COLD_BOOT_PASS', 'Cold boot did not pass')
    for name, expected in r['files'].items():
        require(sha(path(name)) == expected, f'Boot evidence changed: {name}')
    require(r['ram_acceptance_sha256'] == sha(path('reports/phase10_acceptance.json')),
            'Different RAM acceptance')
    require(r['build_id'] == ram['build_id'], 'Different hardware image')
    require(not r['jtag_used_after_physical_cycle'] and not r['program_download_after_physical_cycle'],
            'Cold boot was contaminated by a download')
    installation = read(r['installation'])
    for name, expected in installation['sources'].items():
        require(sha(path(name)) == expected, f'SD installer source differs: {name}')
    require(installation['status'] == 'SD_INSTALL_AND_SYSTEM_RESET_PASS' and
            installation['sd_write_verified'] and installation['boot_medium_verified'] and
            installation['boot_mode'] == 5, 'SD installation incomplete')
    for name, expected in installation['artifacts'].items():
        require(expected == ram['artifacts'][name], f'Installed artifact differs: {name}')
    require(installation['image_sha256'] == ram['artifacts']['BOOT_udp.BIN'] ==
            installation['readback_sha256'], 'SD readback targets another boot image')
    installation_dir = Path(r['installation']).parent
    for name, expected in installation['files'].items():
        require(sha(path(installation_dir / name)) == expected, f'SD transaction evidence changed: {name}')
    require(sha(path(installation_dir / 'sd_boot_readback.bin')) == ram['artifacts']['BOOT_udp.BIN'],
            'SD bytes differ from the accepted BOOT image')
    preflight = read(r['preflight'])
    require(preflight['user_confirmation'].strip() == r['user_confirmation'].strip() and
            bool(r['user_confirmation'].strip()), 'Physical-cycle confirmation missing')
    require(preflight['method'] == 'NETWORK_ONLY_NO_JTAG_NO_DOWNLOAD' and
            preflight['epoch'] == 0 and not preflight['state'] & 7 and preflight['errors'] == 0,
            'Initial state is not a clean, fresh boot')

    def identity(value):
        require(value['hardware'] == ram['hardware'], 'Runtime hardware contract differs')

    identity(preflight)
    finite = read(r['finite'])
    identity(finite)
    require(finite['status'] == 'PASS' and len(finite['cases']) == 79 and
            sum(c['exact_snapshot_values'] for c in finite['cases']) == 80896,
            'Cold-start finite numerical coverage incomplete')
    require(finite['maximum_analysis_us'] <= 281.304 and finite['maximum_publish_us'] <= 281.584,
            'Cold-start finite latency regressed')
    for name, expected in finite['artifacts'].items():
        require(expected == ram['artifacts'][name], 'Finite tests target another image')
    for case in finite['cases']:
        require(case['status'] == 'PASS', 'A finite case failed')
        folder = Path(r['finite']).parent / case['label']
        for name, expected in case['files'].items():
            require(sha(path(folder / name)) == expected, f'Finite capture differs: {folder / name}')
    dynamics = [read(r['dma1000']), read(r['continuous300'])]
    require(dynamics[0].get('completed_transitions', 0) >= 1000 and
            dynamics[1].get('duration_actual_s', 0) >= 300 and
            dynamics[1].get('samples_per_bank') == 32768, 'Cold-start DMA coverage incomplete')
    for d in dynamics:
        identity(d)
        require(d['status'] == 'PASS' and d['effective_average_upload_mbps'] >= 8,
                'Cold-start DMA failed or throughput regressed')
        for name, expected in d['artifacts'].items():
            require(expected == ram['artifacts'][name], 'DMA tests target another image')
        s, stats, diag = d['final_status'], d['statistics'], d['diagnostics']
        require(not s['write_rejected'] and not s['stream_errors'] and not s['dma']['errors'] and
                not s['dma']['error'] and not s['dma']['active'] and s['dma']['done'],
                'DMA error or incomplete final state')
        require(not stats['frequency_id_gaps'] and not stats['udp_missing_packet_count'] and
                not diag['input_rejected'] and not diag['result_queue_rejected'] and
                not diag['input_underreads'], 'Cold-start data loss')
        require(len({diag[k] for k in ('issued_samples', 'accepted_samples', 'fft_input_samples',
                                     'fft_output_samples')}) == 1, 'Sample conservation failed')
        require(d['hardware_max_latency_us'] <= 281.304 and d['hardware_max_publish_latency_us'] <= 281.584,
                'Cold-start dynamic latency regressed')
    final = read(r['final_state'])
    identity(final)
    require(not final['state'] & 7 and final['errors'] == 0, 'Final board not stopped/clean')
    return r


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('record', 'check', 'package'))
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--installation', type=Path)
    parser.add_argument('--cold-folder', type=Path)
    parser.add_argument('--user-confirmation')
    args = parser.parse_args()
    root = args.root.resolve()
    if args.mode == 'record':
        require(root == ROOT, 'Record must use this live project')
        require(args.installation and args.cold_folder and args.user_confirmation,
                'Installation, completed cold tests and actual user confirmation required')
        install, cold = args.installation.resolve(), args.cold_folder.resolve()
        require(install.is_relative_to(root / 'reports') and cold.is_relative_to(root / 'reports'),
                'Use project reports paths')
        sys.path.insert(0, str(root / 'host'))
        from iq_client import Client
        client = Client('192.168.1.10', source_ip='192.168.1.20')
        try:
            final = dict(hardware=client.hardware_info(), state=client.read(8)[0],
                         errors=client.read(0x60)[0], epoch=client.read(0x68)[0],
                         checked_at=datetime.datetime.now().astimezone().isoformat())
        finally:
            client.close()
        save(cold / 'final_state.json', final)
        relative = lambda p: p.relative_to(root).as_posix()
        ram = json.loads((root / 'reports/phase10_acceptance.json').read_text())
        r = dict(status='SD_PHYSICAL_COLD_BOOT_PASS', created_at=datetime.datetime.now().astimezone().isoformat(),
            build_id=ram['build_id'], hardware=ram['hardware'], power_supply='USER_CONFIRMED_USB_ONLY',
            user_confirmation=args.user_confirmation, physical_cycle_evidence='User-confirmed unplug/wait/replug, then network-only identity with epoch zero',
            jtag_used_after_physical_cycle=False, program_download_after_physical_cycle=False,
            ram_acceptance_sha256=sha(root / 'reports/phase10_acceptance.json'), installation=relative(install),
            preflight=relative(cold / 'preflight.json'), final_state=relative(cold / 'final_state.json'),
            finite=relative(cold / 'finite/validation.json'), dma1000=relative(cold / 'dma1000/validation.json'),
            continuous300=relative(cold / 'continuous300/stability.json'))
        files = {p for folder in (install.parent, cold) for p in folder.rglob('*') if p.is_file()}
        files.update((Path(__file__).resolve(), root / 'scripts/phase10_sd_install.py'))
        r['files'] = {relative(p): sha(p) for p in sorted(files)}
        save(root / REPORT, r)
        try:
            verify(root)
        except Exception:
            r['status'] = 'FAIL'
            save(root / REPORT, r)
            raise
    result = verify(root)
    print('PHASE10_SD_COLD_BOOT_EVIDENCE_PASS', len(result['files']), 'files', result['build_id'])
    if args.mode == 'package':
        require(root == ROOT, 'Package must use this built project')
        from package_release import package
        package()
        release = root / 'release'
        manifest = json.loads((release / 'manifest.json').read_text())
        manifest.update(board_validation_type='RAM_JTAG_AND_SD_PHYSICAL_COLD_BOOT',
            physical_cold_boot=True, sd_installed=True,
            boot_acceptance_sha256=sha(root / REPORT))
        save(release / 'manifest.json', manifest)
        shutil.copyfile(root / REPORT, release / 'phase10_boot_acceptance.json')
        ram = json.loads((root / 'reports/phase10_acceptance.json').read_text())
        names = set(result['files']) | set(ram['files']) | {
            REPORT, 'reports/phase10_acceptance.json', 'README.md', 'PHASE10_STATUS.md', 'VERSION.json'}
        with zipfile.ZipFile(release / 'phase10_sd_cold_boot_evidence.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
            for name in sorted(names):
                archive.write(root / name, name)
        print('PHASE10_SD_COLD_BOOT_PACKAGE_PASS', release)


if __name__ == '__main__':
    main()
