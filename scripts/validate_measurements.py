"""Prepare or verify explicit finite S1 matrices; never programs FPGA or SD.

prepare --manifest ... --out ...
capture --references ... --out ... --board 192.168.1.10
verify --run ...
"""
from __future__ import annotations
import argparse
import contextlib
import csv
import datetime
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tests'), str(ROOT / 'host')]
import numpy as np
import iq_client
from fft_reference import FFTReference, FS, N, digest
from generate_qualification_vectors import validate_case, waveform
from generate_qualification_vectors import waveform_details
from qualification_capture import capture as capture_configured
from detection_metrics import evaluate as evaluate_detection
from verify_board_capture import verify as verify_capture, require
from package_release import check as check_build
from package_validated import check_board
from record_boot_stage import verify_boot
from phase4_identity import check_identity
from build_rates import FFT_CLOCK_HZ


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def bindings():
    files = ['tests/fft_reference.py', 'tests/generate_qualification_vectors.py',
             'tests/generate_iq_vectors.py', 'tests/frame_length_reference.py',
             'scripts/validate_measurements.py', 'scripts/verify_board_capture.py',
             'scripts/qualification_capture.py','tests/threshold_reference.py','tests/detection_metrics.py',
             'scripts/create_fft.tcl', 'host/iq_client.py', 'host/threshold_config.py', 'data/vectors/hann_u18_f17.mem',
             'scripts/phase4_identity.py', 'scripts/phase4_build_config.py',
             'config/build_profile.json', 'build/config/build_identity.json', 'host/build_rates.py']
    return {str((ROOT / name).resolve()): digest(ROOT / name) for name in files}


def check_bindings(values):
    require(bool(values), 'Empty provenance binding')
    for path, expected in values.items():
        require(digest(path) == expected, f'Dependency changed: {path}')


def load_manifest(path):
    path = Path(path).resolve()
    manifest = read(path)
    require(manifest['schema'] == 'iq-qualification-manifest-v1', 'Unsupported manifest schema')
    require(manifest['generator_sha256'] == digest(ROOT / 'tests/generate_qualification_vectors.py'),
            'Generator changed; regenerate vectors into a new directory')
    spec_path = path.parent / manifest['spec']
    require(digest(spec_path) == manifest['spec_sha256'], 'Specification hash mismatch')
    spec = read(spec_path)
    require(len(spec['cases']) == len(manifest['cases']) > 0, 'Specification case count mismatch')
    ids = [c['id'] for c in manifest['cases']]
    require(len(set(ids)) == len(ids), 'Duplicate case id')
    for case, designed in zip(manifest['cases'], spec['cases']):
        validate_case(case)
        require(all(case.get(k) == v for k, v in designed.items()), 'Manifest differs from source specification')
        vector = (path.parent / case['binary']).resolve()
        require(vector.is_relative_to(path.parent), 'Vector escapes manifest directory')
        require(vector.stat().st_size == case['samples'] * 4 and digest(vector) == case['sha256'],
                'Vector length/hash mismatch')
        _, regenerated, details = waveform_details(designed)
        require(vector.read_bytes() == regenerated.tobytes(), 'Vector differs from declared design')
        require(case.get('measurement_design')==details and case.get('applied_detector')==details['applied_detector'],
                'Generated measurement metadata differs from design')
    return manifest


def prepare(manifest_path, out):
    manifest_path, out = Path(manifest_path).resolve(), Path(out).resolve()
    manifest = load_manifest(manifest_path)
    out.mkdir(parents=True, exist_ok=False)
    source = bindings()
    source[str(manifest_path)] = digest(manifest_path)
    source[str(manifest_path.parent / manifest['spec'])] = manifest['spec_sha256']
    index = dict(schema='iq-qualification-index-v1', manifest=str(manifest_path),
                 manifest_sha256=digest(manifest_path), bindings=source, cases=[])
    with FFTReference() as model:
        index['model'] = model.identity
        source[model.identity['archive_path']] = model.identity['archive_sha256']
        source[model.identity['dll_path']] = model.identity['dll_sha256']
        for case in manifest['cases']:
            vector = manifest_path.parent / case['binary']
            iq = np.fromfile(vector, dtype='<i2').reshape(-1, 2)
            floating, _ = waveform(case)
            for mode in case['windows']:
                label = case['id'] + '_' + mode
                oracle = dict(schema='iq-qualification-reference-v1', case_id=case['id'], mode=mode,
                    input_sha256=digest(vector), sample_rate_hz=FS, detector=case['applied_detector'],replay=case['replay'],
                    bindings=source, model=model.identity, windows=[], snapshots=[], algorithm=[])
                for wid in range(len(iq)//N):
                    raw = iq[wid*N:(wid+1)*N].astype(np.int64)
                    expected, _, snapshot = model.window(raw, mode, wid)
                    oracle['windows'].append(expected)
                    oracle['snapshots'].append(snapshot.tolist())
                    power = raw[:, 0]**2 + raw[:, 1]**2
                    complex_iq = raw[:, 0] + 1j*raw[:, 1]
                    coeff = model.hann / 131072 if mode == 'hann' else np.ones(N)
                    float_power = np.abs(np.fft.fftshift(np.fft.fft(complex_iq * coeff)))**2
                    x = floating[wid*N:(wid+1)*N]
                    oracle['algorithm'].append(dict(window_id=wid,
                        quantized_peak_codes=float(np.sqrt(power.max())),
                        quantized_rms_codes=float(np.sqrt(power.mean())),
                        floating_peak_codes=float(np.max(np.abs(x))),
                        floating_rms_codes=float(np.sqrt(np.mean(np.abs(x)**2))),
                        numpy_peak_hz=float((int(np.argmax(float_power))-N//2)*FS/N) if power.sum() else None))
                reference_path = out / (label + '.json')
                save(reference_path, oracle)
                index['cases'].append(dict(label=label, case=case, vector=str(vector),
                    reference=reference_path.name, reference_sha256=digest(reference_path)))
    check_bindings(source)
    save(out / 'index.json', index)
    return out / 'index.json'


def load_index(path):
    path = Path(path).resolve()
    index = read(path)
    require(index['schema'] == 'iq-qualification-index-v1', 'Unsupported index')
    check_bindings(index['bindings'])
    require(digest(index['manifest']) == index['manifest_sha256'], 'Manifest changed')
    manifest = load_manifest(index['manifest'])
    expected = [(c, w) for c in manifest['cases'] for w in c['windows']]
    require(len(index['cases']) == len(expected), 'Reference matrix incomplete')
    for row, (case, mode) in zip(index['cases'], expected):
        require(row['case'] == case and row['label'] == case['id']+'_'+mode, 'Reference case mapping mismatch')
        require(Path(row['vector']).resolve() == (Path(index['manifest']).parent/case['binary']).resolve(),
                'Reference vector mapping mismatch')
        reference = path.parent / row['reference']
        require(digest(reference) == row['reference_sha256'], 'Reference hash mismatch')
        oracle = read(reference)
        require(oracle['case_id'] == case['id'] and oracle['mode'] == mode
                and oracle['input_sha256'] == case['sha256'] and oracle['detector']==case['applied_detector']
                and oracle['model']==index['model'], 'Reference metadata mismatch')
        check_bindings(oracle['bindings'])
    return index


def configuration(board, port):
    client = iq_client.Client(board, port)
    try:
        return dict(hardware=client.hardware_info(), state=client.read(8)[0],
                    epoch=client.read(0x68)[0], config_id=client.read(0x6c)[0],
                    registers=list(client.read(0x10, 16)), detector=list(client.read(0x84, 2)))
    finally:
        client.close()


def verify_configuration(folder, case, mode):
    actual, meta = read(Path(folder)/'configuration.json'), read(Path(folder)/'capture.json')
    d = case['applied_detector']
    expected = [FS, FFT_CLOCK_HZ, N, case['samples'], 0, int(case['replay']=='cyclic'), int(mode=='hann'), 0, N-1,
                d['ton']&0xffffffff, d['ton']>>32, d['toff']&0xffffffff, d['toff']>>32, d['kon'], d['koff'], d['max_burst_samples']]
    require(actual['registers'] == expected, 'Actual register configuration mismatch')
    require(actual['detector'] == [iq_client.DETECTOR_MODES[d['mode']], d['gap_min']], 'Actual detector mismatch')
    require(actual['config_id'] == meta['config_id'] and actual['epoch'] == meta['epoch'],
            'Readback belongs to a different capture')
    require(actual['state'] & 7 == 0, 'Readback requires completed finite capture')
    check_identity(actual['hardware'])
    check_identity(meta)


def error_rows(folder, case, oracle):
    # Every record is independently checked by verify_capture. For cyclic input,
    # this table stores the first period, avoiding millions of identical rows.
    with (Path(folder)/'frequency.bin').open('rb') as stream:
        raw=stream.read(len(oracle['windows'])*128)
    result = []
    for wid in range(len(raw)//128):
        actual = iq_client.decode_record(raw[wid*128:(wid+1)*128], 'frequency')
        reference, algorithm = oracle['windows'][wid], oracle['algorithm'][wid]
        signal = case['signal']
        design_hz = signal['tones'][0]['bin']*FS/N if signal['kind']=='tone' else None
        eligible = (signal['kind']=='tone' and signal['tones'][0]['amplitude']>=256
                    and case['category'] not in ('edge-tone', 'burst-boundary') and reference['total']>0)
        error_hz = actual['peak_hz']-design_hz if design_hz is not None and reference['total'] else None
        row = dict(algorithm, case=case['id'], category=case['category'], window=oracle['mode'],
            design_frequency_hz=design_hz, numpy_peak_hz=algorithm['numpy_peak_hz'],
            reference_peak_hz=reference['f_peak_hz'], hardware_peak_hz=actual['peak_hz'],
            frequency_error_hz=error_hz, frequency_error_bins=error_hz/(FS/N) if error_hz is not None else None,
            normal_frequency_statistic=eligible,
            nearest_bin_match=(actual['q_peak'] == int(np.floor(signal['tones'][0]['bin']+0.5))+N//2)
                if eligible else None,
            bandwidth_hz=actual['bandwidth_hz'], raw_energy=actual['raw_energy'],
            reference_energy=reference['energy'], flags_raw=actual['flags_raw'],
            flags='|'.join(actual['flags']), capture=str(Path(folder).resolve()))
        row['observation_scope']='first_period_of_exact_repeated_capture' if case['replay']=='cyclic' else 'finite_window'
        design=case['measurement_design']
        row.update(statistics_group=case.get('statistics_group',case['category']),seed=case['seed'],
            configured_snr_db=case['noise'].get('snr_db'),
            measured_snr_before_quantization_db=design.get('measured_snr_before_quantization_db'),
            measured_snr_after_quantization_db=design.get('measured_snr_after_quantization_db'),
            rolloff=case['signal'].get('rolloff'),symbol_rate_baud=design.get('symbol_rate_baud'),
            ideal_support_hz=design.get('ideal_support_hz'),papr_db=design['papr_db'],
            threshold_on=case['applied_detector']['ton'],threshold_off=case['applied_detector']['toff'])
        interval=[wid*N,(wid+1)*N]
        support=case['measurement_design']['shaped_intervals']
        row['window_region']='steady' if any(a<=interval[0] and b>=interval[1] for a,b in support) else (
            'edge' if any(min(b,interval[1])>max(a,interval[0]) for a,b in support) else 'background')
        for name in ('peak', 'rms'):
            measured = actual[name+'_codes']
            row['hardware_'+name+'_codes'] = measured
            row['reference_'+name+'_codes'] = reference[name+'_uq16_16']/65536
            for target in ('quantized', 'floating'):
                value = algorithm[target+'_'+name+'_codes']
                error = measured-value
                row[name+'_error_vs_'+target] = error
                row[name+'_relative_error_vs_'+target] = error/value if value else None
        result.append(row)
    return result


def summarize(rows):
    result = {}
    for category in sorted({r['category'] for r in rows}):
        group = [r for r in rows if r['category']==category]
        summary = dict(windows=len(group))
        for field in ('frequency_error_bins', 'peak_error_vs_quantized', 'rms_error_vs_quantized',
                      'peak_error_vs_floating', 'rms_error_vs_floating'):
            values = [abs(r[field]) for r in group if r[field] is not None
                      and (field!='frequency_error_bins' or r['normal_frequency_statistic'])]
            summary[field] = dict(count=len(values), maximum=max(values), median=float(np.median(values)),
                                 p95=float(np.percentile(values, 95))) if values else dict(count=0)
        result[category] = summary
    return result


def write_errors(out, rows):
    if rows:
        with (Path(out)/'errors.csv').open('w', newline='', encoding='utf-8-sig') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def capture_matrix(index_path, out, board, port):
    index_path, out = Path(index_path).resolve(), Path(out).resolve()
    index = load_index(index_path)
    check_build()
    verify_boot()
    accepted = check_board()
    require(accepted['board'] == board, 'Qualification target differs from accepted deployment')
    out.mkdir(parents=True, exist_ok=False)
    report = dict(status='RUNNING', scope='Manifest-driven measurement qualification; no hardware/SD modification',
        started_at=datetime.datetime.now().astimezone().isoformat(), references=str(index_path),
        references_sha256=digest(index_path), bindings=bindings(), legacy_cases=[], cases=[],
        hardware_identity_limit='Register version and local build evidence; no runtime bitstream hash register',
        artifacts={str(p):digest(p) for p in (ROOT/'artifacts').glob('*') if p.is_file()},
        build_evidence={str(ROOT/'reports'/name):digest(ROOT/'reports'/name) for name in
            ('hardware_provenance.json','simulation_provenance.json','boot_provenance.json',
             'current_board_validation.json','current_deployment.json')})
    errors = []
    current = None
    try:
        info = configuration(board, port)
        require(info['state'] & 7 == 0, 'Another controller is running the board')
        check_identity(info['hardware'])
        require(info['hardware'] == accepted['hardware'], 'Hardware differs from board acceptance')
        report['initial_hardware'] = info
        save(out/'measurement_validation.json', report)
        # Gate each new matrix by fresh finite captures of all 16 legacy combinations.
        legacy = read(ROOT/'data/golden_results.json')['cases']
        for case in legacy:
            current = 'legacy_'+case['name']+'_'+case['mode']
            folder = out/current
            print('LEGACY_START', current, flush=True)
            with (out/(current+'.log')).open('w', encoding='utf-8') as log, contextlib.redirect_stdout(log):
                iq_client.capture(SimpleNamespace(board=board, port=port, vector=str(ROOT/'data/vectors'/(case['name']+'.bin')),
                    out=str(folder), window=case['mode'], cyclic=False, seconds=1, detector='threshold', gap_min=32))
            verified = verify_capture(folder)
            save(folder/'measurement_validation.json', verified)
            report['legacy_cases'].append(verified)
            save(out/'measurement_validation.json', report)
        for row in index['cases']:
            current = row['label']
            case, folder = row['case'], out/current
            reference_path = index_path.parent/row['reference']
            oracle = read(reference_path)
            print('QUALIFICATION_START', current, flush=True)
            with (out/(current+'.log')).open('w', encoding='utf-8') as log, contextlib.redirect_stdout(log):
                capture_configured(SimpleNamespace(board=board, port=port, vector=row['vector'], out=str(folder),
                    window=oracle['mode'], cyclic=case['replay']=='cyclic', seconds=case.get('seconds',1),
                    detector=case['applied_detector']['mode'], gap_min=case['applied_detector']['gap_min']),case['applied_detector'])
            save(folder/'configuration.json', configuration(board, port))
            verify_configuration(folder, case, oracle['mode'])
            verified = verify_capture(folder, row['vector'], qualification=reference_path)
            case_errors = error_rows(folder, case, oracle)
            targets = [r for r in case_errors if r['normal_frequency_statistic']]
            verified.update(case_id=case['id'], label=current, reference_sha256=digest(reference_path),
                configuration_sha256=digest(folder/'configuration.json'),
                algorithm_frequency_target=('NOT_APPLICABLE' if not targets else
                    'PASS' if all(abs(r['frequency_error_bins'])<=1 and r['nearest_bin_match']
                    for r in targets) else 'FAIL'), algorithm_frequency_samples=len(targets))
            if case['replay']=='finite':
                burst_bytes=(folder/'burst.bin').read_bytes()
                intervals=[]
                for offset in range(0,len(burst_bytes),64):
                    b=iq_client.decode_record(burst_bytes[offset:offset+64],'burst')
                    intervals.append([b['start_sample'],b['end_sample_exclusive']])
                metric=evaluate_detection(case['measurement_design']['truth_intervals'],intervals,case['samples'])
                metric['applicability']='NOT_APPLICABLE' if (case['applied_detector']['mode']=='digital-zero' and
                    (case['noise']['kind']!='none' or case['offset_iq']!=[0,0])) else 'APPLICABLE'
                metric['seed']=case['seed'];metric['noise']=case['noise'];metric['offset_iq']=case['offset_iq']
                metric['detector']=case['applied_detector'];metric['design']=case['measurement_design']
                save(folder/'detection_metrics.json',metric)
                verified['detection_metrics_sha256']=digest(folder/'detection_metrics.json')
                verified['detection_metrics']=metric
            save(folder/'measurement_validation.json', verified)
            errors.extend(case_errors)
            report['cases'].append(verified)
            save(out/'measurement_validation.json', report)
        check_bindings(report['bindings'])
        check_bindings(report['artifacts'])
        check_bindings(report['build_evidence'])
        report['status'] = 'PASS'
    except Exception as error:
        report.update(status='FAIL', failed_case=current, error=str(error))
        raise
    finally:
        report['finished_at'] = datetime.datetime.now().astimezone().isoformat()
        report['summary'] = summarize(errors)
        report['algorithm_frequency_target'] = 'PASS' if report['status']=='PASS' and all(
            c['algorithm_frequency_target'] in ('PASS','NOT_APPLICABLE') for c in report['cases']) else 'NOT_PASS'
        write_errors(out, errors)
        if (out/'errors.csv').exists():
            report['errors_sha256'] = digest(out/'errors.csv')
        save(out/'measurement_validation.json', report)
    return report


def verify_run(out):
    out = Path(out).resolve()
    report = read(out/'measurement_validation.json')
    require(report['status']=='PASS', 'Capture matrix did not complete')
    for field in ('bindings','artifacts','build_evidence'):
        check_bindings(report[field])
    index_path = Path(report['references'])
    require(digest(index_path)==report['references_sha256'], 'Reference index changed')
    index = load_index(index_path)
    require(len(report['legacy_cases'])==16 and len(report['cases'])==len(index['cases']), 'Matrix incomplete')
    for legacy in report['legacy_cases']:
        for name, value in legacy['files'].items():
            require(digest(Path(legacy['folder'])/name)==value, 'Legacy capture changed')
        require(verify_capture(legacy['folder'])==legacy, 'Legacy verification differs')
    errors = []
    for row, previous in zip(index['cases'], report['cases']):
        require(row['label']==previous['label'], 'Case sequence mismatch')
        folder = out/row['label']
        require(digest(folder/'configuration.json')==previous['configuration_sha256'], 'Readback changed')
        require(read(folder/'measurement_validation.json')==previous, 'Case report changed')
        if 'detection_metrics_sha256' in previous:
            require(digest(folder/'detection_metrics.json')==previous['detection_metrics_sha256'],'Detection metrics changed')
        for name, value in previous['files'].items():
            require(digest(folder/name)==value, 'Capture file changed')
        oracle = read(index_path.parent/row['reference'])
        verify_configuration(folder, row['case'], oracle['mode'])
        actual = verify_capture(folder, row['vector'], qualification=index_path.parent/row['reference'])
        require(all(previous[k]==v for k,v in actual.items()), 'Numerical verification changed')
        errors.extend(error_rows(folder,row['case'],oracle))
    require(summarize(errors)==report['summary'], 'Error summary changed')
    require(digest(out/'errors.csv')==report['errors_sha256'], 'Error table changed')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p = sub.add_parser('capture')
    p.add_argument('--references', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--board', default='192.168.1.10')
    p.add_argument('--port', type=int, default=5001)
    p = sub.add_parser('verify')
    p.add_argument('--run', type=Path, required=True)
    args = parser.parse_args()
    if args.command=='prepare':
        print(prepare(args.manifest, args.out))
    elif args.command=='capture':
        result = capture_matrix(args.references, args.out, args.board, args.port)
        print('QUALIFICATION_'+result['status'], args.out)
    else:
        result = verify_run(args.run)
        print('QUALIFICATION_REVERIFY_'+result['status'], args.run)


if __name__=='__main__':
    main()
