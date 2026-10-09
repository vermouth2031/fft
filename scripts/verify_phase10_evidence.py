"""Check archived Phase 10 evidence without Vivado or a connected board.

This verifies recorded results and source/capture integrity; it does not rerun
hardware tests, prove every possible input, or qualify physical cold boot.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(root):
    root = root.resolve()

    def path(name):
        result = (root / name).resolve()
        require(result.is_relative_to(root), f'Path outside evidence root: {name}')
        return result

    def read(name):
        return json.loads(path(name).read_text(encoding='utf-8'))

    report = read('reports/phase10_acceptance.json')
    require(report['status'] == 'RAM_JTAG_PASS', 'RAM/JTAG acceptance did not pass')
    require(report['deployment'] == 'RAM_JTAG', 'Unexpected deployment scope')
    require(report['power_supply'] == 'USER_CONFIRMED_USB_ONLY', 'Supply test scope missing')
    for name, expected in report['files'].items():
        actual = hashlib.sha256(path(name).read_bytes()).hexdigest()
        require(actual == expected, f'Evidence changed: {name}')
    repair = read(report['repair_summary'])
    require(repair['status'] == 'VERIFIED_USB_RAM_JTAG_REPAIR', 'Repair evidence incomplete')
    require(repair['build_id'] == report['build_id'], 'Repair targets another image')
    paired = read(report['paired_baseline_report'])
    require(paired['status'] == 'PASS' and paired['completed_transitions'] >= 1000,
            'Paired Phase 9 control incomplete')
    require(paired['hardware']['build_id'] == '48ec8e97bf87f19a0cbf4efcb7c8a501',
            'Unexpected Phase 9 control image')
    require(paired['hardware_max_latency_us'] <= 281.304 and
            paired['hardware_max_publish_latency_us'] <= 281.584,
            'Paired control no longer supports the latency gates')
    archive = 'reports/phase10_reference_evidence/'
    path_map = read(archive + 'path_map.json')
    build_map = {destination.split('/build/', 1)[1]: destination
                 for destination in path_map.values() if '/build/' in destination}

    def archived_digest(name, expected):
        resolved = build_map[name[6:]] if name.startswith('build/') else name
        require(resolved in report['files'], f'Evidence is not archived: {resolved}')
        require(report['files'][resolved] == expected, f'Provenance differs: {name}')

    for stage in ('simulation', 'hardware'):
        provenance = read(f'reports/{stage}_provenance.json')
        for section in ('inputs', 'evidence'):
            for name, expected in provenance[section].items():
                archived_digest(name, expected)
    groups = read(build_map['logs/core_parallel_manifest.json'])
    require(groups['status'] == 'PASS' and len(groups['groups']) == 8,
            'Core group coverage incomplete')
    for group in groups['groups']:
        name = path_map[group['log']]
        require(report['files'][name] == group['sha256'], f'Core group log differs: {name}')
    python_tests = read('reports/phase9_python_validation.json')
    require(python_tests['status'] == 'PASS' and len(python_tests['tests']) == 7,
            'Python regressions incomplete')
    for test in python_tests['tests']:
        require(test['exit_code'] == 0, f'Python regression failed: {test["script"]}')
        archived_digest(test['log'].replace('\\', '/'), test['sha256'])
    for name, expected in python_tests['inputs'].items():
        archived_digest(name.replace('\\', '/'), expected)

    expected_hardware = dict(hardware_version=65544, fft_length=16384,
        sample_rate_hz=125000000, timestamp_clock_hz=125000000,
        fft_clock_hz=125000000, replay_bank_samples=32768,
        frequency_ring_records=128, burst_ring_records=128,
        snapshot_points=1024, input_fifo_depth=4096, scan_lanes=8,
        snapshot_group=16, record_format_version=1, hardware_capabilities=31)

    def identity(result):
        hardware = result['hardware']
        require(hardware['build_id'] == report['build_id'], 'Hardware identity differs')
        for key, value in expected_hardware.items():
            require(hardware[key] == value, f'Hardware contract changed: {key}')

    identity(report)
    deployment = read('reports/phase10_deployment.json')
    identity(deployment)
    require(deployment['status'] == 'RAM_JTAG_LOADED' and not deployment['sd_modified'],
            'Unexpected deployment record')
    for name, expected in deployment['files'].items():
        if name.startswith('artifacts/'):
            require(report['artifacts'][name[10:]] == expected, f'Deployed artifact differs: {name}')
        elif name == 'build/logs/phase10_program_board.log':
            require(report['files'][archive + 'program_board.txt'] == expected, 'JTAG log differs')
        else:
            archived_digest(name, expected)
    hardware = read('reports/hardware_validation.json')
    require(hardware['status'] == 'PASS', 'Hardware build failed')
    require(hardware['setup_slack_ns'] >= 0 and hardware['hold_slack_ns'] >= 0,
            'Physical timing failed')
    require(hardware['cdc_critical'] == 0 and hardware['unconstrained_internal_endpoints'] == 0,
            'CDC/constraint validation failed')
    resources = report['resources']['current']
    utilization = path('reports/utilization_flat.rpt').read_text()
    for key, label in dict(lut='Slice LUTs', lut_memory='LUT as Memory',
                          ff='Slice Registers', bram='Block RAM Tile',
                          dsp='DSPs', slice='Slice').items():
        match = re.search(r'\|\s*' + re.escape(label) + r'\*?\s*\|\s*([\d.]+)', utilization)
        require(match is not None and float(match[1]) == resources[key],
                f'Resource report differs: {key}')
    require(resources['lut'] <= 23500 and resources['lut_memory'] <= 6000
            and resources['ff'] <= 28000,
            'Repaired implementation logic/register budget exceeded')
    require(resources['bram'] <= 128 and resources['dsp'] <= 49,
            'BRAM/DSP resource limit exceeded')
    core = read('reports/core_validation.json')
    require(core['status'] == 'PASS' and core['exact_fft_points'] == 1048576
            and core['frequency_records'] == 64, 'Full numerical simulation incomplete')
    require(core['maximum_analysis_latency_us'] <= 281.304, 'RTL latency regressed')
    equivalent = read('reports/phase10_equivalence.json')
    require(equivalent['status'] == 'PASS' and equivalent['spectrum_latency_cycles'] == 2127,
            'Cycle equivalence failed')
    require(equivalent['queue_high_water'] <= 2123, 'Deferred queue bound regressed')
    for name, expected in equivalent['files'].items():
        archived_digest(name, expected)

    finite = read(report['finite_report'])
    identity(finite)
    for name, expected in finite['artifacts'].items():
        require(expected == report['artifacts'][name], f'Finite test image differs: {name}')
    require(finite['status'] == 'PASS' and len(finite['cases']) == 79,
            'Finite board matrix incomplete')
    require(finite['maximum_analysis_us'] <= 281.304 and
            finite['maximum_publish_us'] <= 281.584, 'Finite board latency regressed')
    require(sum(c['exact_snapshot_values'] for c in finite['cases']) == 80896,
            'Board snapshot verification incomplete')
    for case in finite['cases']:
        require(case['status'] == 'PASS', f'Board case failed: {case["label"]}')
        folder = Path(report['finite_report']).parent / case['label']
        for name, expected in case['files'].items():
            actual = hashlib.sha256(path(folder / name).read_bytes()).hexdigest()
            require(actual == expected, f'Capture changed: {folder / name}')

    require(len(report['dynamic_reports']) == 3, 'Dynamic acceptance incomplete')
    dynamic = []
    for name in report['dynamic_reports']:
        result = read(name)
        dynamic.append(result)
        identity(result)
        for artifact, expected in result['artifacts'].items():
            require(expected == report['artifacts'][artifact], f'Dynamic image differs: {name}')
        require(result['status'] == 'PASS', f'Dynamic acceptance failed: {name}')
        require(result['effective_average_upload_mbps'] >= 8.0,
                f'Upload throughput regressed: {name}')
        final = result['final_status']
        require(not final['write_rejected'] and not final['stream_errors'] and
                not final['dma']['errors'] and not final['dma']['error'] and
                not final['dma']['active'] and final['dma']['done'],
                f'DMA/stream telemetry failed: {name}')
        stats, diag = result['statistics'], result['diagnostics']
        require(not stats['frequency_id_gaps'] and not stats['udp_missing_packet_count'],
                f'Record integrity failed: {name}')
        require(not diag['input_rejected'] and not diag['result_queue_rejected']
                and not diag['input_underreads'], f'Hardware rejected data: {name}')
        require(len({diag[k] for k in ('issued_samples', 'accepted_samples',
                'fft_input_samples', 'fft_output_samples')}) == 1,
                f'Sample conservation failed: {name}')
        require(result['hardware_max_latency_us'] <= 281.304 and
                result['hardware_max_publish_latency_us'] <= 281.584,
                f'Dynamic latency regressed: {name}')
    require(any(r.get('completed_transitions', 0) >= 1000 for r in dynamic),
            '1000 bank switches not verified')
    for samples, seconds in ((16384, 60), (32768, 300)):
        require(any(r.get('samples_per_bank') == samples and
                    r.get('duration_actual_s', 0) >= seconds for r in dynamic),
                f'Stability coverage missing: {samples} samples, {seconds} seconds')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    report = verify(args.root)
    print('PHASE10_EVIDENCE_PASS', len(report['files']), 'files;',
          'physical SD/cold boot remain outside RAM/JTAG acceptance')


if __name__ == '__main__':
    main()
