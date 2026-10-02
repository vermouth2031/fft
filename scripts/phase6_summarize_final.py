"""Reverify and summarize the complete A2 final board campaign."""
import argparse
import datetime
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAPTURES = ROOT / 'captures/phase6/candidate_a2_125_125_final_matrix'
WIDEST = ROOT / 'captures/phase6/candidate_a2_125_125_ofdm_finite/measurement_validation.json'

from record_build_stage import sha
from summarize_phase3 import summarize as summarize_regression


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def require(value, message):
    if not value:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'reports/phase6_a2_final_matrix.json')
    args = parser.parse_args()
    require(not args.out.exists(), 'Do not overwrite an existing final summary')
    campaign = read(CAPTURES / 'campaign.json')
    expected_stages = ['validation', 'noise_only', 'legacy_regression', 'robust_regression',
        'wide_continuous', 'sensitivity', 'ofdm_finite', 'ofdm_boundary', 'ofdm_continuous',
        'widest_finite', 'widest_continuous', 'noise']
    require(campaign['status'] == 'PASS' and [x['stage'] for x in campaign['stages']] == expected_stages,
            'Final campaign is incomplete')

    regression = summarize_regression(CAPTURES, False)
    require(regression['targets_met'], 'Frozen detector regression targets failed')
    matrices = []
    all_rows = []
    expected = {'validation': 625, 'noise_only': 256, 'legacy_regression': 431,
        'robust_regression': 212, 'wide_continuous': 17, 'sensitivity': 112,
        'ofdm_finite': 240, 'ofdm_boundary': 24, 'ofdm_continuous': 7,
        'widest_finite': 80, 'widest_continuous': 7, 'noise': 9}
    evidence = {'captures/phase6/candidate_a2_125_125_final_matrix/campaign.json':
                sha(CAPTURES / 'campaign.json')}
    widest_values = []
    for stage in expected_stages:
        path = WIDEST if stage == 'widest_finite' else CAPTURES / stage / 'measurement_validation.json'
        matrix = read(path)
        require(matrix['status'] == 'PASS' and len(matrix['cases']) == expected[stage]
                and len(matrix['legacy_cases']) == 16, f'Incomplete matrix: {stage}')
        matrices.append({'stage': stage, 'cases': len(matrix['cases']),
                         'legacy_cases': len(matrix['legacy_cases']), 'report': str(path),
                         'report_sha256': sha(path)})
        evidence[path.relative_to(ROOT).as_posix()] = sha(path)
        all_rows.extend(matrix['cases'])
        if stage == 'widest_finite':
            for row in matrix['cases']:
                for window in row['bandwidth']['windows']:
                    if window['region'] == 'internal':
                        require(window['normal_records'] == window['records'], 'Flagged widest finite window')
                        widest_values.append(window['bandwidth_min_hz'])
        if stage == 'widest_continuous':
            for row in matrix['cases']:
                require(row['bandwidth']['all_internal_windows_meet_minimum'],
                        'Widest continuous bandwidth gate failed')
                for window in row['bandwidth']['windows']:
                    if window['region'] == 'internal':
                        widest_values.append(window['bandwidth_min_hz'])

    board = read(ROOT / 'reports/current_board_validation.json')
    hardware = board['hardware']
    high_water = []
    issued = []
    for row in all_rows:
        require(row['status'] == 'PASS', 'A matrix row failed')
        meta = read(Path(row['folder']) / 'capture.json')
        require(meta['build_id'] == hardware['build_id'] and meta['sample_rate_hz'] == 125000000,
                'Capture belongs to a different build')
        d = meta['throughput_diagnostics']
        require(meta['throughput_conservation_valid'] and
                d['issued_samples'] == d['accepted_samples'] == d['fft_input_samples'] ==
                d['fft_output_samples'] == meta['input_samples'] == 8192*d['fft_output_windows'] and
                d['fft_output_windows'] == meta['completed_windows'] and
                not (d['input_rejected'] or d['result_queue_rejected'] or d['input_underreads']) and
                meta['frequency_queue_dropped'] == meta['burst_queue_dropped'] ==
                meta['udp_missing_packet_count'] == 0, 'Throughput conservation failed')
        high_water.append(d['input_fifo_high_water'])
        issued.append(d['issued_samples'])

    maximum_analysis = max(row['maximum_analysis_us'] for row in all_rows)
    maximum_publish = max(row['maximum_publish_us'] for row in all_rows)
    require(maximum_analysis <= 150 and maximum_publish <= 151, 'A2 latency target failed')
    require(min(widest_values) >= 115000000, 'A2 115 MHz OBW target failed')
    require(sum(expected.values()) == 2020 and sum(x['legacy_cases'] for x in matrices) == 192,
            'Final matrix cardinality changed')

    result = {'schema': 'iq-phase6-a2-final-matrix-v1', 'status': 'PASS',
        'created_at': datetime.datetime.now().astimezone().isoformat(), 'hardware': hardware,
        'matrix_cases': 2020, 'legacy_compatibility_cases': 192, 'matrices': matrices,
        'regression_targets': regression['target_results'],
        'maximum_analysis_us': maximum_analysis, 'maximum_publish_us': maximum_publish,
        'minimum_widest_internal_obw_hz': min(widest_values),
        'maximum_input_fifo_high_water': max(high_water),
        'maximum_samples_in_one_capture': max(issued),
        'normal_transport_failures': 0, 'evidence': evidence}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('PHASE6_FINAL_SUMMARY_PASS', args.out)


if __name__ == '__main__':
    main()
