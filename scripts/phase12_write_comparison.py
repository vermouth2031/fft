"""Write the Phase 11/12 comparison from completed, matching board reports."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
from phase12_build_check import check

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--finite', type=Path, required=True)
    parser.add_argument('--wideband', type=Path, required=True)
    parser.add_argument('--baseline-wideband', type=Path, required=True)
    parser.add_argument('--baseline-continuous', type=Path, required=True)
    parser.add_argument('--dynamic', type=Path, nargs=3, required=True)
    args = parser.parse_args()
    sources = [ROOT/'reports/phase12_baseline.json', ROOT/'reports/phase11_acceptance.json',
               args.finite, args.wideband, args.baseline_wideband,
               args.baseline_continuous, *args.dynamic]
    baseline, previous, finite, wide, base_wide, base_continuous, *dynamic = [
        json.loads(p.read_text(encoding='utf-8')) for p in sources]
    build = check()
    hardware = finite['hardware']
    assert all(r['status'] == 'PASS' and r['hardware'] == hardware
               for r in [finite, wide, *dynamic])
    assert all(r['status'] == 'PASS' and r['hardware'] == baseline['hardware']
               for r in [base_wide, base_continuous])
    assert previous['hardware'] == baseline['hardware']
    assert len(finite['cases']) == 79 and len(wide['cases']) == len(base_wide['cases']) == 272
    analysis = max([finite['maximum_analysis_us']] +
                   [c['measurement']['maximum_analysis_us'] for c in wide['cases']] +
                   [r['hardware_max_latency_us'] for r in dynamic])
    publish = max([finite['maximum_publish_us']] +
                  [c['measurement']['maximum_publish_us'] for c in wide['cases']] +
                  [r['hardware_max_publish_latency_us'] for r in dynamic])
    assert analysis <= baseline['maximum_analysis_us'] and publish <= baseline['maximum_publish_us']
    fs, old_fs, n = hardware['sample_rate_hz'], baseline['hardware']['sample_rate_hz'], hardware['fft_length']
    pair = lambda old, new: dict(before=old, after=new, change_percent=(new/old-1)*100)
    report = dict(status='BOARD_COMPARISON_PASS',
        created_at=datetime.datetime.now().astimezone().isoformat(),
        baseline_build_id=baseline['hardware']['build_id'], candidate_build_id=hardware['build_id'],
        metrics=dict(i_bits=pair(16,16), q_bits=pair(16,16), sample_rate_hz=pair(old_fs,fs),
            fft_points=pair(baseline['hardware']['fft_length'],n),
            maximum_analysis_us=pair(baseline['maximum_analysis_us'],analysis),
            maximum_publish_us=pair(baseline['maximum_publish_us'],publish),
            minimum_primary_99_percent_bandwidth_hz=pair(base_wide['minimum_primary_full_bandwidth_hz'],wide['minimum_primary_full_bandwidth_hz']),
            maximum_primary_99_percent_bandwidth_hz=pair(base_wide['maximum_primary_full_bandwidth_hz'],wide['maximum_primary_full_bandwidth_hz'])),
        resources={name:pair(previous['build']['resources'][name],value)
                   for name,value in build['resources'].items()},
        frequency_bin_spacing_hz=pair(old_fs/baseline['hardware']['fft_length'],fs/n),
        timing=build['hardware'],
        measurement_definition='Equal-tail 99% occupied bandwidth of the same quantized I16/Q16 OFDM matrix, without interpolation',
        input_scope='FPGA replay-bank consumption rate; network upload of continuously unique samples at this rate is not claimed',
        tradeoffs=['FFT point count remains fixed, so increasing the sample rate increases frequency-bin spacing in Hz.',
                   'Extra control registers support 150 MHz timing; register count is allowed up to 3% above Phase11.',
                   'FFT clock is 150 MHz; the earlier 180 MHz candidates failed timing.'],
        physical_cold_boot='NOT_ESTABLISHED_BY_THIS_REPORT',
        files={p.resolve().relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sources})
    target = ROOT/'reports/phase12_comparison.json'
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('PHASE12_COMPARISON_PASS', analysis, publish, wide['minimum_primary_full_bandwidth_hz'])


if __name__ == '__main__':
    main()
