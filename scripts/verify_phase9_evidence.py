"""Verify archived Phase 9 evidence without a board or Vivado installation.

This checks evidence integrity and recorded acceptance gates. It does not rerun
the simulator or replace a physical power-cycle test.
"""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    report = json.loads((root / 'reports/phase9_acceptance.json').read_text(encoding='utf-8'))
    if report['status'] != 'RAM_JTAG_PASS':
        raise ValueError('RAM/JTAG acceptance did not pass')
    for name, expected in report['files'].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f'Path outside evidence root: {name}')
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f'Evidence changed: {name}')
    for name in report['dynamic_reports']:
        result = json.loads((root / name).read_text(encoding='utf-8'))
        if result['status'] != 'PASS' or result['hardware']['build_id'] != report['build_id']:
            raise ValueError(f'Acceptance/identity mismatch: {name}')
        stats, diag = result['statistics'], result['diagnostics']
        if stats['frequency_id_gaps'] or stats['udp_missing_packet_count']:
            raise ValueError(f'Record integrity failed: {name}')
        if diag['input_rejected'] or diag['result_queue_rejected'] or diag['input_underreads']:
            raise ValueError(f'Hardware rejected samples/results: {name}')
        if len({diag[k] for k in ('issued_samples', 'accepted_samples', 'fft_input_samples', 'fft_output_samples')}) != 1:
            raise ValueError(f'Sample conservation failed: {name}')
        if result['hardware_max_latency_us'] > 350 or result['hardware_max_publish_latency_us'] > 360:
            raise ValueError(f'Phase 9 latency target failed: {name}')
    print('PHASE9_EVIDENCE_PASS', len(report['files']), 'files; SD/cold boot remain unverified')


if __name__ == '__main__':
    main()
