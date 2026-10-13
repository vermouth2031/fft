"""Frozen OFDM bandwidth campaign against an explicitly selected built project.

Uses the production network capture, AMD integer oracle and an independent
float64 occupied-power reference. Never programs hardware or writes an SD card.
"""
import argparse
import contextlib
import datetime
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--capture', action='store_true')
    parser.add_argument('--board', default='192.168.1.10')
    args = parser.parse_args()
    project, out = args.project.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    sys.path[:0] = [str(project / d) for d in ('scripts', 'host', 'tests')]
    import numpy as np
    from build_rates import SAMPLE_RATE_HZ as fs, FFT_LENGTH as n
    from fft_reference import FFTReference
    from phase9_ofdm import symbols
    from generate_qualification_vectors import DEFAULT_DETECTOR
    from iq_client import Client, capture, decode_record
    from verify_board_capture import verify

    expected = json.loads((project/'build/config/build_identity.json').read_text())
    report = dict(status='RUNNING', started_at=datetime.datetime.now().astimezone().isoformat(),
        project=str(project), build_id=expected['build_id'], sample_rate_hz=fs,
        fft_length=n, definition='Equal-tail 99 percent occupied power; no spectral interpolation',
        scope='Finite OFDM steady windows; independent held-out seeds; no ADC or fresh-IQ throughput claim',
        policy=dict(primary_seed_range=[312100,312109], component_gains=[1500,6000,9000],
                    maximum_component_codes=32767, maximum_edge_error_bins=2,
                    maximum_width_error_bins=4, maximum_analysis_us=234.426667,
                    target_bandwidth_hz=158000000 if fs==160000000 else 120000000), cases=[])
    # Fixed spans scale with Fs for directly comparable fractional occupancy.
    widths = [fs*r for r in (.16,.48,.80,.96)] + [8190*fs/8192]
    definitions = []
    for wi, width in enumerate(widths):
        half = min(4095, int(round(width*8192/(2*fs))))
        for modulation in ('qpsk','qam16'):
            for seed in range(312100,312110):
                definitions.append(dict(label=f'w{wi}_{modulation}_{seed}_g6000', half=half,
                    modulation=modulation, seed=seed, gain=6000, shift_hz=0, group='primary'))
    for gain in (1500,9000):
        for modulation in ('qpsk','qam16'):
            for seed in range(312100,312103):
                definitions.append(dict(label=f'full_{modulation}_{seed}_g{gain}', half=4095,
                    modulation=modulation, seed=seed, gain=gain, shift_hz=0, group='amplitude'))
    for wi in (0,1,2):
        half = int(round(widths[wi]*8192/(2*fs)))
        shift = fs/2 - half*fs/8192 - .016*fs
        for sign in (-1,1):
            for modulation in ('qpsk','qam16'):
                for seed in (312110,312111):
                    definitions.append(dict(label=f'shift{sign}_w{wi}_{modulation}_{seed}',half=half,
                        modulation=modulation,seed=seed,gain=6000,shift_hz=sign*shift,group='shift'))
    save(out/'specification.json', dict(policy=report['policy'], definitions=definitions))
    dependencies = [Path(__file__).resolve(),out/'specification.json',project/'config/build_profile.json',
                    project/'build/config/build_identity.json']
    dependencies += [project / name for name in ('tests/fft_reference.py','tests/phase9_ofdm.py',
        'scripts/verify_board_capture.py','host/iq_client.py','tests/threshold_reference.py')]
    bindings = {str(p):sha(p) for p in dependencies}
    if args.capture:
        client=Client(args.board,source_ip='192.168.1.20')
        try:
            info=client.hardware_info()
            if info['build_id'] != expected['build_id'] or client.read(8)[0]&7 or client.read(0x60)[0]:
                raise RuntimeError('Board is not idle, clean and running selected build')
            report['hardware']=info
        finally:client.close()
    save(out/'validation.json',report)
    try:
        with FFTReference() as model:
            for spec in definitions:
                signal=dict(ifft_length=8192,cyclic_prefix=512,active_half=spec['half'],
                            modulation=spec['modulation'],gain=spec['gain'])
                _, parts = symbols(signal,spec['seed'],4)
                # Generate uninterrupted OFDM, then observe two complete FFT windows.
                wave=np.concatenate([p[1] for p in parts])[:2*n]
                if spec['shift_hz']:
                    wave=wave*np.exp(2j*np.pi*spec['shift_hz']*np.arange(len(wave))/fs)
                quantized=np.column_stack((np.rint(wave.real),np.rint(wave.imag)))
                if np.max(quantized)>32767 or np.min(quantized)<-32768:
                    raise ValueError('Clipping in frozen stimulus: '+spec['label'])
                iq=quantized.astype('<i2');vector=out/(spec['label']+'.bin');vector.write_bytes(iq.tobytes())
                for mode in ('rect','hann'):
                    label=spec['label']+'_'+mode
                    oracle=dict(schema='iq-qualification-reference-v1',input_sha256=sha(vector),
                        sample_rate_hz=fs,mode=mode,replay='finite',bindings=bindings,
                        detector=dict(DEFAULT_DETECTOR,mode='digital-zero'),windows=[],snapshots=[])
                    independent=[]
                    for wid in range(2):
                        raw=iq[wid*n:(wid+1)*n].astype(np.int64)
                        integer,_,snapshot=model.window(raw,mode,wid)
                        oracle['windows'].append(integer);oracle['snapshots'].append(snapshot.tolist())
                        coeff=model.hann/131072 if mode=='hann' else np.ones(n)
                        power=np.abs(np.fft.fftshift(np.fft.fft((raw[:,0]+1j*raw[:,1])*coeff)))**2
                        cumulative=np.cumsum(power);total=cumulative[-1]
                        low=int(np.searchsorted(cumulative,.005*total))
                        high=int(np.searchsorted(cumulative,.995*total))
                        independent.append(dict(q_low=low,q_high=high,bandwidth_hz=(high-low)*fs/n,
                            low_hz=(low-n//2)*fs/n,high_hz=(high-n//2)*fs/n,
                            integer_low_error_bins=integer['q_low']-low,
                            integer_high_error_bins=integer['q_high']-high))
                    reference=out/(label+'_reference.json');save(reference,oracle)
                    result=dict(label=label,group=spec['group'],mode=mode,signal=spec,
                        design_span_hz=2*spec['half']*fs/8192,independent=independent,
                        component_peak_codes=int(np.max(np.abs(iq.astype(np.int64)))),
                        reference_sha256=sha(reference),vector_sha256=sha(vector),
                        integer_bandwidth_hz=[w['bandwidth_hz'] for w in oracle['windows']],status='REFERENCE_ONLY')
                    result['independent_accuracy_pass']=all(
                        abs(w['integer_low_error_bins'])<=2 and abs(w['integer_high_error_bins'])<=2 and
                        abs(w['integer_high_error_bins']-w['integer_low_error_bins'])<=4 for w in independent)
                    if args.capture:
                        folder=out/label
                        with (out/(label+'.log')).open('w',encoding='utf-8') as stream,contextlib.redirect_stdout(stream):
                            capture(SimpleNamespace(board=args.board,port=5001,source_ip='192.168.1.20',
                                vector=str(vector),out=str(folder),window=mode,cyclic=False,seconds=1,
                                detector='digital-zero',gap_min=32))
                        checked=verify(folder,vector,qualification=reference)
                        if checked['maximum_analysis_us']>234.426667:
                            raise AssertionError('Analysis latency regressed')
                        result.update(status='PASS',measurement=checked)
                        save(folder/'measurement_validation.json',checked)
                    report['cases'].append(result);save(out/'validation.json',report)
                    print('WIDEBAND_CASE',label,result['status'],result['independent_accuracy_pass'],flush=True)
        failed=[c['label'] for c in report['cases'] if not c['independent_accuracy_pass']]
        report.update(status='PASS' if args.capture and not failed else ('ACCURACY_FAIL' if failed else 'REFERENCE_PASS'),
            independent_accuracy_failures=failed,case_count=len(report['cases']),
            minimum_primary_full_bandwidth_hz=min(b for c in report['cases']
                if c['group']=='primary' and c['signal']['half']==4095 for b in c['integer_bandwidth_hz']),
            maximum_primary_full_bandwidth_hz=max(b for c in report['cases']
                if c['group']=='primary' and c['signal']['half']==4095 for b in c['integer_bandwidth_hz']))
    except Exception as error:
        report.update(status='FAIL',error=str(error));raise
    finally:
        report['finished_at']=datetime.datetime.now().astimezone().isoformat()
        save(out/'validation.json',report)
    if report['status']=='ACCURACY_FAIL':
        raise RuntimeError('Independent bandwidth tolerance failed; retain all results')
    print('WIDEBAND_CAMPAIGN_PASS',report['case_count'],flush=True)


if __name__=='__main__':main()
