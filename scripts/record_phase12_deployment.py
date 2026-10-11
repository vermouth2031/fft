"""Record completed SD installation or user-confirmed physical cold-boot tests."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
from verify_phase12_evidence import verify as verify_ram
from verify_phase12_cold_boot import verify as verify_cold

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return path.read_text(encoding='utf-8')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path):
    return path.resolve().relative_to(ROOT).as_posix()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('sd', 'cold'))
    parser.add_argument('--finite', type=Path, required=True)
    parser.add_argument('--final-state', type=Path, required=True)
    parser.add_argument('--installation', type=Path)
    parser.add_argument('--initial-state', type=Path)
    parser.add_argument('--continuous300', type=Path)
    args = parser.parse_args()
    ram = verify_ram(ROOT)
    finite = json.loads(read(args.finite))
    final = json.loads(read(args.final_state))
    assert finite['status'] == 'PASS' and finite['hardware'] == ram['hardware']
    assert len(finite['cases']) == 79 and sum(c['exact_snapshot_values'] for c in finite['cases']) == 80896
    assert finite['maximum_analysis_us'] <= 278.448 and finite['maximum_publish_us'] <= 278.728
    assert final['hardware'] == ram['hardware'] and final['state'] & 7 == 0 and final['errors'] == 0
    for name, expected in finite['artifacts'].items():
        assert ram['artifacts'][name] == expected
    files = {args.finite.resolve(), args.final_state.resolve()}
    folders = [args.finite.parent.parent]
    report = dict(created_at=datetime.datetime.now().astimezone().isoformat(),
        build_id=ram['build_id'], hardware=ram['hardware'], final_state=relative(args.final_state))
    if args.stage == 'sd':
        if args.installation is None:
            parser.error('sd requires --installation')
        installation = json.loads(read(args.installation))
        assert installation['status'] == 'SD_INSTALL_AND_SYSTEM_RESET_PASS'
        assert installation['sd_write_verified'] and installation['boot_medium_verified']
        assert installation['image_sha256'] == installation['readback_sha256'] == ram['artifacts']['BOOT_udp.BIN']
        assert installation['acceptance_sha256'] == digest(ROOT/'reports/phase12_acceptance.json')
        assert installation['reboot_hardware'] == ram['hardware']
        for name, expected in installation['files'].items():
            p = (args.installation.parent/name).resolve()
            assert p.is_relative_to(args.installation.parent.resolve()) and digest(p) == expected
        folders.append(args.installation.parent)
        report.update(status='SD_INSTALL_RESET_NUMERICAL_PASS', sd_installed=True,
            boot_medium_verified=True, physical_cold_boot=False,
            physical_cold_boot_scope='SD-mode system reset is not a physical power cycle.',
            boot_sha256=installation['image_sha256'], original_boot_backup=installation['original_boot_backup'],
            installation_report=relative(args.installation), numerical_report=relative(args.finite),
            cases=len(finite['cases']), frequency_records=finite['frequency_records'],
            burst_records=finite['burst_records'], maximum_analysis_us=finite['maximum_analysis_us'],
            maximum_publish_us=finite['maximum_publish_us'])
        target = ROOT/'reports/phase12_sd_deployment.json'
    else:
        if args.initial_state is None or args.continuous300 is None:
            parser.error('cold requires --initial-state and --continuous300')
        initial = json.loads(read(args.initial_state))
        continuous = json.loads(read(args.continuous300))
        assert initial['user_confirmation'].strip()
        assert continuous['status'] == 'PASS' and continuous['duration_actual_s'] >= 300
        assert continuous['hardware'] == ram['hardware']
        files.add(args.initial_state.resolve())
        files.add(ROOT/'reports/phase12_sd_deployment.json')
        folders.append(args.continuous300.parent)
        report.update(status='SD_PHYSICAL_COLD_BOOT_PASS', physical_cold_boot=True,
            user_confirmation=initial['user_confirmation'],
            physical_cycle_evidence='User-reported power-off/on followed by network-only identity and epoch zero; physical switching is not instrumented',
            jtag_used_after_physical_cycle=False, program_download_after_physical_cycle=False,
            system_reset_after_physical_cycle=False, initial_state=relative(args.initial_state),
            sd_deployment='reports/phase12_sd_deployment.json', finite=relative(args.finite),
            continuous300=relative(args.continuous300),
            scope='79 finite numerical cases and 300 seconds of full-band OFDM DDR/DMA after this user-confirmed physical cycle; 272-case bandwidth matrix and 1000-switch fault tests belong to earlier RAM/JTAG acceptance.',
            maximum_analysis_us=max(finite['maximum_analysis_us'],continuous['hardware_max_latency_us']),
            maximum_publish_us=max(finite['maximum_publish_us'],continuous['hardware_max_publish_latency_us']))
        target = ROOT/'reports/phase12_boot_acceptance.json'
    assert not target.exists(), 'Acceptance output already exists; review it before retrying'
    for folder in folders:
        files.update(p.resolve() for p in folder.rglob('*') if p.is_file())
    report['files'] = {relative(p):digest(p) for p in sorted(files)}
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if args.stage == 'cold':
        try:
            verify_cold(ROOT)
        except Exception:
            report['status']='FAIL'
            target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            raise
    print('PHASE12_DEPLOYMENT_RECORDED', report['status'], len(files))


if __name__ == '__main__':
    main()
