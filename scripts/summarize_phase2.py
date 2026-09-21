"""Aggregate independently verified phase-two runs without rewriting raw evidence."""
import argparse
import collections
import datetime
import json
from pathlib import Path

import numpy as np
from validate_measurements import ROOT, read, save, verify_run
from record_build_stage import sha

STAGES = ('s1_complete', 's2_training', 's2_validation', 's2_boundaries',
          's3_finite', 's3_continuous', 's3_refinement',
          's3_refinement_continuous', 's3_widest_60s')


def stats(values):
    return dict(count=len(values), minimum=min(values), median=float(np.median(values)),
                p95=float(np.percentile(values, 95)), maximum=max(values)) if values else dict(count=0)


def summarize(root):
    import csv
    stages = []
    detections = collections.defaultdict(list)
    bandwidth = collections.defaultdict(list)
    normal_frequency = []
    hann = np.array([int(line, 16) for line in
                     (ROOT/'data/vectors/hann_u18_f17.mem').read_text().splitlines()])/131072
    for stage in STAGES:
        folder = root / stage
        report = verify_run(folder)
        index = read(report['references'])
        with (folder / 'errors.csv').open(encoding='utf-8-sig', newline='') as stream:
            errors = list(csv.DictReader(stream))
        floating_bandwidth = {}
        if stage.startswith('s3'):
            for spec in index['cases']:
                mode = spec['label'].rsplit('_', 1)[1]
                iq = np.fromfile(spec['vector'], dtype='<i2').reshape(-1, 2)
                signal = iq[:, 0].astype(float)+1j*iq[:, 1]
                for wid, block in enumerate(signal.reshape(-1, 8192)):
                    power = np.abs(np.fft.fftshift(np.fft.fft(block*(hann if mode=='hann' else 1))))**2
                    cdf = np.cumsum(power)
                    if cdf[-1]:
                        lo = np.searchsorted(cdf, cdf[-1]*.005)
                        hi = np.searchsorted(cdf, cdf[-1]*.995)
                        width = (hi-lo)*100000000/8192
                    else:
                        width = 0
                    floating_bandwidth[(spec['case']['id'], mode, wid)] = float(width)
        for row in errors:
            if stage == 's1_complete' and row['normal_frequency_statistic'] == 'True':
                normal_frequency.append(abs(float(row['frequency_error_bins'])))
            if stage.startswith('s3'):
                floating = floating_bandwidth[(row['case'], row['window'], int(row['window_id']))]
                row['bandwidth_error_vs_numpy_bins'] = (float(row['bandwidth_hz'])-floating)/(100000000/8192)
                key = (stage, row['statistics_group'], row['window'], row['window_region'])
                bandwidth[key].append(row)
        for row, spec in zip(report['cases'], index['cases']):
            if stage.startswith('s2'):
                detections[(stage, spec['case']['statistics_group'])].append(row['detection_metrics'])
        stages.append(dict(stage=stage, status=report['status'], folder=str(folder),
            report_sha256=sha(folder/'measurement_validation.json'),
            references=report['references'], references_sha256=report['references_sha256'],
            legacy_cases=len(report['legacy_cases']), cases=len(report['cases']),
            frequency_records=sum(c['frequency_records'] for c in report['cases']),
            burst_records=sum(c['burst_records'] for c in report['cases']),
            maximum_analysis_us=max(c['maximum_analysis_us'] for c in report['cases']),
            maximum_publish_us=max(c['maximum_publish_us'] for c in report['cases']),
            algorithm_frequency_target=report['algorithm_frequency_target']))
        print('VERIFIED', stage, len(report['cases']), flush=True)
    groups = []
    for (stage, name), rows in sorted(detections.items()):
        group = dict(stage=stage, group=name, cases=len(rows),
            seeds=sorted({r['seed'] for r in rows if r['seed'] is not None}),
            applicability=sorted({r['applicability'] for r in rows}))
        for field in ('known_bursts', 'matched', 'normal_matches', 'missed', 'false_alarms',
                      'merged_detections', 'split_truths', 'unmatched_overlapping_detections',
                      'background_observation_us'):
            group[field] = sum(r[field] for r in rows)
        known = group['known_bursts']
        group['detection_rate'] = group['matched']/known if known else None
        group['normal_detection_rate'] = group['normal_matches']/known if known else None
        background = group['background_observation_us']
        group['false_alarms_per_second'] = group['false_alarms']*1e6/background if background else None
        for field in ('start', 'end', 'length'):
            values = [m[field+'_error_samples'] for r in rows for m in r['matches']]
            group[field+'_error_samples'] = stats(values)
            group[field+'_absolute_error_samples'] = stats([abs(v) for v in values])
            group[field+'_error_us'] = stats([v/100 for v in values])
        for key in ('measured_snr_before_quantization_db', 'measured_snr_after_quantization_db'):
            group[key] = stats([r['design'][key] for r in rows if key in r['design']])
        groups.append(group)
    bands = []
    for (stage, group, window, region), rows in sorted(bandwidth.items()):
        bands.append(dict(stage=stage, group=group, window=window, region=region,
            seeds=sorted({int(r['seed']) for r in rows}),
            bandwidth_mhz=stats([float(r['bandwidth_hz'])/1e6 for r in rows]),
            bandwidth_error_vs_numpy_bins=stats([r['bandwidth_error_vs_numpy_bins'] for r in rows]),
            flags=sorted({r['flags'] for r in rows}),
            observation_scope=sorted({r['observation_scope'] for r in rows})))
    return dict(status='PASS', created_at=datetime.datetime.now().astimezone().isoformat(),
        scope='S1 complete matrix, S2 declared detector applicability, S3 finite and continuous real-board validation; unchanged 100MSPS hardware',
        algorithm_limit='PASS means bit-exact hardware agreement and complete failure accounting, not universal successful detection',
        continuous_limit='Continuous runs repeat a fixed 32768-pair input; bandwidth statistics use its first period, every record is numerically verified',
        floating_bandwidth_reference='NumPy full 8192-point FFT of actual quantized I/Q, same quantized Hann coefficients, linear CDF 0.5% to 99.5%; analysis only, not a substitute for AMD bit-exact verification',
        stages=stages, detection_groups=groups, bandwidth_groups=bands,
        normal_frequency_error_bins=stats(normal_frequency),
        source_sha256=sha(Path(__file__)), evidence={})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('captures', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args=parser.parse_args()
    result=summarize(args.captures.resolve())
    save(args.out, result)
    print('PHASE2_SUITE_PASS', args.out, flush=True)


if __name__ == '__main__':
    main()
