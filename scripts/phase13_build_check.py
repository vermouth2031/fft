"""Gate Phase 13 candidates using newly generated provenance, never old board evidence."""
import json
import re
import csv
from pathlib import Path
from record_build_stage import verify, sha
from verify_phase11_evidence import CLOCK_MODULE, mmcm_hz

ROOT = Path(__file__).resolve().parents[1]

def check():
    verify('simulation')
    verify('hardware')
    read = lambda name: json.loads((ROOT / name).read_text(encoding='utf-8'))
    profile = read('config/build_profile.json')
    assert profile['sample_rate_hz'] == profile['timestamp_clock_hz'] == 160000000
    assert profile['fft_clock_hz'] == 160000000
    assert profile['fft_length'] == 16384 and profile['input_fifo_memory'] == 'block'
    ports = read('reports/phase13_replay_enable_inspection.json')
    assert ports['status'] == 'BOTH_NATIVE_PORT_ENABLES_CONFIRMED'
    assert ports['build_id'] == read('build/config/build_identity.json')['build_id']
    assert sha(ROOT / ports['checkpoint']) == ports['checkpoint_sha256']
    port_table = ROOT / 'reports/phase13_replay_port_enables.tsv'
    assert sha(port_table) == ports['table_sha256']
    rows = list(csv.DictReader(port_table.read_text().splitlines(), delimiter='\t'))
    assert len(rows) == 128 and len({row['cell'] for row in rows}) == 64
    assert all(row['driver_type'] not in ('VCC', 'GND', '') for row in rows)
    assert sum(row['port_enable'] == 'ENARDEN' for row in rows) == 64
    assert sum(row['port_enable'] == 'ENBWREN' for row in rows) == 64
    clocks = read('reports/phase13_clock_generation.json')
    assert clocks['source_hz'] == profile['sample_rate_hz'] and clocks['ps_fclk1_hz'] == 125000000
    assert clocks['fft_hz'] == profile['fft_clock_hz']
    assert clocks['pl_mmcm'] is True
    if clocks['pl_mmcm']:
        text = (ROOT / CLOCK_MODULE).read_text()
        assert abs(mmcm_hz(text) - profile['sample_rate_hz']) < 1
        def param(name):
            return float(re.search(r'\.'+name+r'\s*\(\s*([\d.]+)', text)[1])
        assert abs(1e9/param('CLKIN1_PERIOD')*param('CLKFBOUT_MULT_F')/param('DIVCLK_DIVIDE')/param('CLKOUT1_DIVIDE')-profile['fft_clock_hz']) < 1
    assert sha(ROOT / 'build/board/iq_board.gen/sources_1/bd/system/ip/system_ps7_0/ps7_init.tcl') == read('reports/phase13_baseline.json')['ps7_init_sha256']
    core = read('reports/core_validation.json')
    assert core['status'] == 'PASS' and core['exact_fft_points'] == 1048576
    assert core['frequency_records'] == 64 and core['maximum_analysis_latency_us'] <= 234.426667
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
    math_log = (ROOT / 'build/logs/sim_phase12_math_ranges.log').read_text(errors='replace')
    assert 'PHASE12_MATH_RANGES_PASS vectors=10220' in math_log and 'Fatal:' not in math_log
    axi_log = (ROOT / 'build/logs/sim_axi.log').read_text(errors='replace')
    assert 'ACK_INTERVAL_PASS cases=65536' in axi_log
    assert 'SEGMENTED_COMPARE_PASS cases=65536' in axi_log
    ack_pipeline = re.search(r'ACK_PIPELINE_PASS transactions=(\d+)', axi_log)
    assert ack_pipeline and int(ack_pipeline[1]) >= 5
    capacity_pages = re.search(r'CAPACITY_PAGE_METADATA_PASS cycles=(\d+)', axi_log)
    assert capacity_pages and int(capacity_pages[1]) >= 32768
    replay = re.search(r'REPLAY_PIPELINE_SCOREBOARD_PASS samples=(\d+) switches=(\d+)', axi_log)
    assert replay and int(replay[1]) >= 32768 and int(replay[2]) >= 1
    time_log = (ROOT / 'build/logs/sim_phase12_time_equivalence.log').read_text(errors='replace')
    assert 'PHASE12_TIME_EQUIVALENCE_PASS' in time_log and 'Fatal:' not in time_log
    units_log = (ROOT / 'build/logs/sim_units.log').read_text(errors='replace')
    assert '1056_constant_division_cases' in units_log and '1060864_capacity_pairs_both_ring_sizes' in units_log
    assert 'UNITS_PASS' in units_log and 'Fatal:' not in units_log
    window_log = (ROOT / 'build/logs/sim_phase11_window.log').read_text(errors='replace')
    window_match = re.search(r'PHASE11_WINDOW_EQUIVALENCE_PASS comparisons=(\d+)', window_log)
    assert window_match and int(window_match[1]) >= 98304 and 'Fatal:' not in window_log
    utilization = (ROOT / 'reports/utilization_flat.rpt').read_text()
    resources = {}
    for label, maximum in [('Slice LUTs', 23400), ('LUT as Memory', 6000),
                           ('Slice Registers', 29200), ('Block RAM Tile', 128), ('DSPs', 49)]:
        match = re.search(r'\|\s*' + re.escape(label) + r'\*?\s*\|\s*([\d.]+)', utilization)
        assert match, label
        resources[label] = float(match[1])
        assert resources[label] <= maximum, (label, resources[label], maximum)
    commit_log = (ROOT / 'build/logs/sim_phase13_commit.log').read_text(errors='replace')
    assert 'PHASE13_COMMIT_PASS transactions=64 cancel_stages=3' in commit_log and 'Fatal:' not in commit_log
    sw = read('reports/software_validation.json')
    assert sw['status'] == 'BUILD_PASS' and sw['xsa_sha256'] == sha(ROOT / 'artifacts/iq_analyzer.xsa')
    for name, expected in sw['artifacts'].items():
        assert sha(ROOT / 'artifacts' / name) == expected, name
    for name, expected in sw['firmware_sources'].items():
        assert sha(ROOT / 'firmware' / name) == expected, name
    return dict(profile=profile, resources=resources, hardware=hw, simulation=core)

if __name__ == '__main__':
    print('PHASE13_BUILD_CHECK_PASS', json.dumps(check(), ensure_ascii=False))
