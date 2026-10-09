"""Gate Phase 11 candidates using newly generated provenance, never old board evidence."""
import json
import re
from pathlib import Path
from record_build_stage import verify, sha
from verify_phase11_evidence import CLOCK_MODULE, mmcm_hz

ROOT = Path(__file__).resolve().parents[1]

def check():
    verify('simulation')
    verify('hardware')
    read = lambda name: json.loads((ROOT / name).read_text(encoding='utf-8'))
    profile = read('config/build_profile.json')
    assert profile['sample_rate_hz'] == profile['timestamp_clock_hz'] == 125000000
    assert profile['fft_clock_hz'] in (125000000, 150000000)
    assert profile['fft_length'] == 16384 and profile['input_fifo_memory'] == 'block'
    clocks = read('reports/phase11_clock_generation.json')
    assert clocks['source_hz'] == clocks['ps_fclk1_hz'] == profile['sample_rate_hz']
    assert clocks['fft_hz'] == profile['fft_clock_hz']
    assert clocks['pl_mmcm'] == (profile['fft_clock_hz'] != profile['sample_rate_hz'])
    if clocks['pl_mmcm']:
        assert abs(mmcm_hz((ROOT / CLOCK_MODULE).read_text()) - profile['fft_clock_hz']) < 1
    assert sha(ROOT / 'build/board/iq_board.gen/sources_1/bd/system/ip/system_ps7_0/ps7_init.tcl') == read('reports/phase11_baseline.json')['ps7_init_sha256']
    core = read('reports/core_validation.json')
    assert core['status'] == 'PASS' and core['exact_fft_points'] == 1048576
    assert core['frequency_records'] == 64 and core['maximum_analysis_latency_us'] <= 281.304
    hw = read('reports/hardware_validation.json')
    assert hw['status'] == 'PASS' and hw['setup_slack_ns'] >= 0 and hw['hold_slack_ns'] >= 0
    assert hw['cdc_critical'] == hw['unconstrained_internal_endpoints'] == 0
    eq = read('reports/phase10_equivalence.json')
    assert eq['status'] == 'PASS' and eq['spectrum_latency_cycles'] == 2127
    for name, expected in eq['files'].items():
        assert sha(ROOT / name) == expected, name
    py = read('reports/phase9_python_validation.json')
    assert py['status'] == 'PASS' and len(py['tests']) == 7
    assert all(t['exit_code'] == 0 for t in py['tests'])
    units_log = (ROOT / 'build/logs/sim_units.log').read_text(errors='replace')
    assert '1056_constant_division_cases' in units_log and '1060864_capacity_pairs_both_ring_sizes' in units_log
    assert 'UNITS_PASS' in units_log and 'Fatal:' not in units_log
    window_log = (ROOT / 'build/logs/sim_phase11_window.log').read_text(errors='replace')
    window_match = re.search(r'PHASE11_WINDOW_EQUIVALENCE_PASS comparisons=(\d+)', window_log)
    assert window_match and int(window_match[1]) >= 98304 and 'Fatal:' not in window_log
    utilization = (ROOT / 'reports/utilization_flat.rpt').read_text()
    resources = {}
    for label, maximum in [('Slice LUTs', 23500), ('LUT as Memory', 6000),
                           ('Slice Registers', 28000), ('Block RAM Tile', 128), ('DSPs', 49)]:
        match = re.search(r'\|\s*' + re.escape(label) + r'\*?\s*\|\s*([\d.]+)', utilization)
        assert match, label
        resources[label] = float(match[1])
        assert resources[label] <= maximum, (label, resources[label], maximum)
    sw = read('reports/software_validation.json')
    assert sw['status'] == 'BUILD_PASS' and sw['xsa_sha256'] == sha(ROOT / 'artifacts/iq_analyzer.xsa')
    for name, expected in sw['artifacts'].items():
        assert sha(ROOT / 'artifacts' / name) == expected, name
    for name, expected in sw['firmware_sources'].items():
        assert sha(ROOT / 'firmware' / name) == expected, name
    return dict(profile=profile, resources=resources, hardware=hw, simulation=core)

if __name__ == '__main__':
    print('PHASE11_BUILD_CHECK_PASS', json.dumps(check(), ensure_ascii=False))
