"""Verify portable Phase 11 source/evidence hashes and recorded RAM/JTAG acceptance."""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLOCK_MODULE = 'build/board/iq_board.gen/sources_1/bd/system/ip/system_fft_clock_0/system_fft_clock_0_clk_wiz.v'

def require(ok, message):
    if not ok:
        raise ValueError(message)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def mmcm_hz(text):
    def parameter(name):
        match = re.search(r'\.' + name + r'\s*\(\s*([\d.]+)\s*\)', text)
        require(match is not None, 'Missing MMCM parameter: ' + name)
        return float(match[1])
    return (1e9 / parameter('CLKIN1_PERIOD') * parameter('CLKFBOUT_MULT_F') /
            parameter('DIVCLK_DIVIDE') / parameter('CLKOUT0_DIVIDE_F'))

def verify(root=ROOT):
    root = root.resolve()
    def path(name):
        p = (root / name).resolve()
        require(p.is_relative_to(root), 'Path escapes archive')
        return p
    def read(name):
        return json.loads(path(name).read_text(encoding='utf-8'))
    r = read('reports/phase11_acceptance.json')
    require(r['status'] == 'RAM_JTAG_PASS', 'Candidate has not passed board acceptance')
    require(not r['sd_installed'] and not r['physical_cold_boot'], 'Unexpected deployment scope')
    for name, expected in r['files'].items():
        require(sha(path(name)) == expected, 'Evidence changed: ' + name)
    def bound(name, expected):
        archived = r['build_path_map'].get(name, name)
        require(r['files'].get(archived) == expected, 'Unbound evidence: ' + name)
    for stage in ('simulation', 'hardware'):
        p = read('reports/' + stage + '_provenance.json')
        for section in ('inputs', 'evidence'):
            for name, expected in p[section].items():
                bound(name, expected)
        for name, expected in p['artifacts'].items():
            require(r['artifacts'][Path(name).name] == expected, 'Artifact identity mismatch')
    profile = read('config/build_profile.json')
    h = r['hardware']
    for name in ('sample_rate_hz', 'timestamp_clock_hz', 'fft_clock_hz', 'hardware_version',
                 'fft_length', 'replay_bank_samples', 'input_fifo_depth', 'scan_lanes'):
        require(h[name] == profile[name], 'Runtime configuration differs: ' + name)
    require(h['sample_rate_hz'] == h['timestamp_clock_hz'] == 125000000 and h['fft_length'] == 16384,
            'Input rate or FFT length changed')
    clocks = read('reports/phase11_clock_generation.json')
    require(clocks['source_hz'] == clocks['ps_fclk1_hz'] == h['sample_rate_hz'] and
            clocks['fft_hz'] == h['fft_clock_hz'] and
            clocks['pl_mmcm'] == (h['fft_clock_hz'] != h['sample_rate_hz']),
            'Physical clock configuration differs')
    if clocks['pl_mmcm']:
        require(abs(mmcm_hz(path(r['build_path_map'][CLOCK_MODULE]).read_text()) - h['fft_clock_hz']) < 1,
                'Generated MMCM does not implement the declared FFT frequency')
    identity = read(r['build_path_map']['build/config/build_identity.json'])
    require(r['artifacts']['ps7_init.tcl'] == read('reports/phase11_baseline.json')['ps7_init_sha256'],
            'PS/DDR initialization changed versus the validated baseline')
    require(identity['build_id'] == h['build_id'] == r['build_id'], 'Build identity differs')
    for name, expected in identity['inputs'].items():
        bound(name, expected)
    core = read('reports/core_validation.json')
    require(core['status'] == 'PASS' and core['exact_fft_points'] == 1048576 and core['frequency_records'] == 64,
            'FFT numerical coverage incomplete')
    require(core['maximum_analysis_latency_us'] <= 281.304, 'Simulation latency regressed')
    units = path(r['build_path_map']['build/logs/sim_units.log']).read_text(errors='replace')
    require('UNITS_PASS' in units and '1056_constant_division_cases' in units and
            '1060864_capacity_pairs_both_ring_sizes' in units and 'Fatal:' not in units,
            'Divider or record-capacity unit coverage incomplete')
    hw = read('reports/hardware_validation.json')
    require(hw['status'] == 'PASS' and hw['setup_slack_ns'] >= 0 and hw['hold_slack_ns'] >= 0 and
            hw['cdc_critical'] == hw['unconstrained_internal_endpoints'] == 0, 'Timing/CDC failed')
    finite = read(r['finite_report'])
    baseline = read('reports/phase11_baseline.json')
    previous = read(baseline['finite_report'])
    require(sha(path(baseline['finite_report'])) == baseline['finite_report_sha256'] and
            previous['status'] == 'PASS' and previous['hardware']['build_id'] == baseline['build_id'],
            'Baseline numerical report differs')
    require(previous['summary'] == finite['summary'] and len(previous['cases']) == len(finite['cases']) and
            all(a['label'] == b['label'] and a['detection_metrics'] == b['detection_metrics']
                for a,b in zip(previous['cases'],finite['cases'])), 'Measurement accuracy changed versus baseline')
    require(finite['hardware'] == h and finite['status'] == 'PASS' and len(finite['cases']) == 79,
            'Board matrix incomplete or wrong image')
    require(sum(c['exact_snapshot_values'] for c in finite['cases']) == 80896, 'Snapshot coverage incomplete')
    require(all(c['status'] == 'PASS' for c in finite['cases']), 'Finite case failed')
    require(finite['maximum_analysis_us'] <= 281.304 and finite['maximum_publish_us'] <= 281.584,
            'Finite board latency regressed')
    for row in [finite] + [read(n) for n in r['dynamic_reports']]:
        require(row['status'] == 'PASS' and row['hardware'] == h, 'Board identity/status differs')
        for name, expected in row['artifacts'].items():
            require(r['artifacts'][name] == expected, 'Board artifact differs')
    dynamic = [read(n) for n in r['dynamic_reports']]
    require(r['maximum_analysis_us'] == max([finite['maximum_analysis_us']] + [d['hardware_max_latency_us'] for d in dynamic]) and
            r['maximum_publish_us'] == max([finite['maximum_publish_us']] + [d['hardware_max_publish_latency_us'] for d in dynamic]),
            'Acceptance headline must include the worst continuous-test latency')
    require(len(dynamic) == 3 and dynamic[0].get('completed_transitions', 0) >= 1000 and
            dynamic[1].get('duration_actual_s', 0) >= 60 and dynamic[2].get('duration_actual_s', 0) >= 300,
            'Continuous test coverage incomplete')
    for d in dynamic:
        require(d['hardware_max_latency_us'] <= 281.304 and d['hardware_max_publish_latency_us'] <= 281.584,
                'Continuous latency regressed')
        s, stats, diag = d['final_status'], d['statistics'], d['diagnostics']
        require(not s['write_rejected'] and not s['stream_errors'] and not s['dma']['errors'] and
                not s['dma']['error'] and not s['dma']['active'] and s['dma']['done'], 'DMA error')
        require(not stats['frequency_id_gaps'] and not stats['udp_missing_packet_count'] and
                not diag['input_rejected'] and not diag['result_queue_rejected'] and not diag['input_underreads'],
                'Data loss')
        require(len({diag[k] for k in ('issued_samples', 'accepted_samples', 'fft_input_samples', 'fft_output_samples')}) == 1,
                'Sample conservation failed')
        require(d['effective_average_upload_mbps'] >= 8, 'Upload throughput regressed')
    final = read(r['final_state'])
    require(final['hardware'] == h and not final['state'] & 7 and final['errors'] == 0, 'Final board state differs')
    return r

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=ROOT)
    r = verify(p.parse_args().root)
    print('PHASE11_EVIDENCE_PASS', len(r['files']), 'files', r['build_id'])
