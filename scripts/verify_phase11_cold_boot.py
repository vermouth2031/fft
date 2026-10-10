"""Offline verification of Phase 11 user-confirmed SD cold-boot evidence."""
import argparse
import hashlib
import json
from pathlib import Path
from verify_phase11_evidence import verify as verify_ram


def verify(root):
    root = root.resolve()
    def path(name):
        p = (root / name).resolve()
        if not p.is_relative_to(root):
            raise ValueError('Evidence path escapes project')
        return p
    def read(name):
        return json.loads(path(name).read_text(encoding='utf-8'))
    def sha(name):
        return hashlib.sha256(path(name).read_bytes()).hexdigest()
    def require(ok, message):
        if not ok:
            raise ValueError(message)
    ram = verify_ram(root)
    r = read('reports/phase11_boot_acceptance.json')
    require(r['status'] == 'SD_PHYSICAL_COLD_BOOT_PASS', 'Cold boot did not pass')
    for name, digest in r['files'].items():
        require(sha(name) == digest, 'Evidence changed: ' + name)
    initial = read(r['initial_state'])
    require(initial['user_confirmation'].strip() and
            not initial['jtag_used'] and not initial['program_download_performed'] and
            not initial['system_reset_performed'], 'Missing uncontaminated physical-cycle evidence')
    before = initial['before']
    require(before['hardware'] == ram['hardware'] and before['epoch'] == 0 and
            before['state'] & 7 == 0 and before['errors'] == 0, 'Cold-start identity/state differs')
    sd = read(r['sd_deployment'])
    require(sha(r['sd_deployment']) == initial['sd_deployment_sha256'], 'SD history changed')
    require(sd['sd_installed'] and sd['boot_medium_verified'] and
            sd['boot_sha256'] == ram['artifacts']['BOOT_udp.BIN'] == initial['boot_sha256'],
            'SD image differs from accepted build')
    for name, digest in sd['files'].items():
        require(sha(name) == digest, 'SD transaction evidence changed: ' + name)
    finite, continuous = read(r['finite']), read(r['continuous60'])
    require(len(finite['cases']) == 79 and
            sum(c['exact_snapshot_values'] for c in finite['cases']) == 80896,
            'Finite numerical coverage incomplete')
    require(continuous['duration_actual_s'] >= 60, 'Continuous test incomplete')
    for tested in (finite, continuous):
        require(tested['status'] == 'PASS' and tested['hardware'] == ram['hardware'],
                'Board validation failed or build differs')
        for name, digest in tested['artifacts'].items():
            require(ram['artifacts'][name] == digest, 'Test artifact differs')
    require(continuous['hardware_max_latency_us'] <= 281.304 and
            continuous['hardware_max_publish_latency_us'] <= 281.584, 'Latency regressed')
    diag = continuous['diagnostics']
    stats, status = continuous['statistics'], continuous['final_status']
    require(not stats['frequency_id_gaps'] and not stats['udp_missing_packet_count'] and
            not diag['input_rejected'] and not diag['result_queue_rejected'] and
            not diag['input_underreads'] and not status['write_rejected'] and
            not status['stream_errors'] and not status['dma']['errors'] and
            not status['dma']['error'] and not status['dma']['active'] and
            status['dma']['done'], 'Cold-start data loss or DMA error')
    require(len({diag[k] for k in ('issued_samples', 'accepted_samples',
            'fft_input_samples', 'fft_output_samples')}) == 1, 'Sample conservation failed')
    final = read(r['final_state'])
    require(final['hardware'] == ram['hardware'] and final['state'] & 7 == 0 and
            final['errors'] == 0, 'Final board state differs')
    return r


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    result = verify(parser.parse_args().root)
    print('PHASE11_SD_COLD_BOOT_EVIDENCE_PASS', result['build_id'], len(result['files']), 'files')
