"""Generate independent manifest-driven, unclipped finite qualification inputs."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import numpy as np
from fft_reference import FS, N, digest
from threshold_reference import validate_detector, runs
from generate_iq_vectors import rrc_taps

DEFAULT_DETECTOR = dict(mode='threshold', ton=1048576, toff=262144,
                        kon=8, koff=32, gap_min=32, max_burst_samples=1048576)


def validate_case(case):
    if not re.fullmatch(r'[a-z0-9_]+', case['id']):
        raise ValueError('Case id must contain lowercase letters, digits and underscores')
    if case['sample_rate_hz'] != FS or case['fft_length'] != N:
        raise ValueError('Sample rate and FFT length must match the selected build profile')
    if case['samples'] not in (8192, 16384, 24576, 32768) or case['replay'] not in ('finite','cyclic'):
        raise ValueError('Only whole-window replay up to 32768 pairs is supported')
    if case['replay']=='cyclic' and (case.get('seconds') not in (10,60) or case.get('seam')!='quiet'):
        raise ValueError('Cyclic qualification requires an explicit quiet seam and 10/60 seconds')
    detector = case['detector']
    validate_detector(detector)
    if not case['windows'] or len(set(case['windows'])) != len(case['windows']) or any(
            w not in ('rect', 'hann') for w in case['windows']):
        raise ValueError('Invalid windows')
    noise=case['noise']
    if noise.get('kind') not in ('none','awgn'):
        raise ValueError('Unsupported noise kind')
    if noise['kind']=='awgn':
        keys=[k for k in ('snr_db','power_codes2') if k in noise]
        if len(keys)!=1 or type(case['seed']) is not int:
            raise ValueError('AWGN needs exactly one SNR or absolute power and an integer seed')
        value=noise[keys[0]]
        if not isinstance(value,(int,float)) or not np.isfinite(value) or (keys[0]=='power_codes2' and value<=0):
            raise ValueError('Invalid noise level')
    if len(case['offset_iq'])!=2 or any(type(v) is not int for v in case['offset_iq']):
        raise ValueError('DC offset must be two integer codes')
    signal = case['signal']
    if signal['kind'] not in ('tone', 'two-tone', 'zero', 'constant','qpsk','rrc-qpsk'):
        raise ValueError('Unsupported waveform')
    intervals = case['design_intervals']
    if signal['kind'] == 'zero':
        if intervals:
            raise ValueError('Zero input must have no designed signal intervals')
    elif not intervals or any(not (0<=a<b<=case['samples']) for a,b in intervals) or any(
            intervals[n][1]>intervals[n+1][0] for n in range(len(intervals)-1)):
        raise ValueError('Signal intervals must be explicit, sorted and non-overlapping')
    if signal['kind'] in ('qpsk','rrc-qpsk'):
        if type(case['seed']) is not int or signal['sps'] not in (2,4):
            raise ValueError('QPSK requires integer seed and validated integer SPS=2 or 4')
        if signal['normalization'] not in ('peak','rms') or not 0<signal['amplitude']<=32767:
            raise ValueError('Invalid QPSK normalization/amplitude')
        if any((b-a)%signal['sps'] for a,b in intervals):
            raise ValueError('Symbol intervals must contain whole symbols')
        if signal['kind']=='rrc-qpsk' and not (0<signal['rolloff']<=1 and signal['span_symbols'] in (10,16)):
            raise ValueError('Invalid RRC shape')
    if signal['kind'] in ('tone', 'two-tone'):
        if len(signal['tones']) != (1 if signal['kind'] == 'tone' else 2):
            raise ValueError('Incorrect tone count')
        for tone in signal['tones']:
            if not (np.isfinite(tone['bin']) and -N/2 <= tone['bin'] < N/2
                    and np.isfinite(tone['amplitude']) and tone['amplitude'] > 0):
                raise ValueError('Invalid tone bin or amplitude')


def waveform_details(case):
    validate_case(case)
    signal = case['signal']
    value = np.zeros(case['samples'], dtype=complex)
    shaped=[]
    rng=np.random.default_rng(case['seed'])
    if signal['kind'] != 'zero':
        for start,end in case['design_intervals']:
            if signal['kind']=='constant':
                burst=np.full(end-start,complex(*signal['iq']))
            elif signal['kind'] in ('qpsk','rrc-qpsk'):
                sps=signal['sps'];count=(end-start)//sps
                symbols=((2*rng.integers(0,2,count)-1)+1j*(2*rng.integers(0,2,count)-1))/np.sqrt(2)
                if signal['kind']=='rrc-qpsk':
                    up=np.zeros(count*sps,dtype=complex);up[::sps]=symbols
                    taps=rrc_taps(signal['rolloff'],sps,signal['span_symbols'])
                    burst=np.convolve(up,taps,mode='full')
                else:
                    burst=np.repeat(symbols,sps)
                normalizer=np.max(np.abs(burst)) if signal['normalization']=='peak' else np.sqrt(np.mean(np.abs(burst)**2))
                burst=burst*(signal['amplitude']/normalizer)
                burst*=np.exp(2j*np.pi*signal.get('carrier_hz',0)*np.arange(start,start+len(burst))/FS)
            else:
                t=np.arange(start,end);burst=np.zeros(end-start,dtype=complex)
                for tone in signal['tones']:
                    burst+=tone['amplitude']*np.exp(2j*np.pi*tone['bin']*t/N)
            actual_end=start+len(burst)
            if actual_end>len(value) or (shaped and start<shaped[-1][1]):
                raise ValueError('Shaped signal exceeds capture or overlaps the preceding tail')
            value[start:actual_end]=burst
            shaped.append([start,actual_end])
    clean=value.copy()
    active=np.zeros(len(value),dtype=bool)
    for a,b in shaped:active[a:b]=True
    added=np.zeros(len(value),dtype=complex)
    if case['noise']['kind']=='awgn':
        if 'power_codes2' in case['noise']:
            sigma=np.sqrt(case['noise']['power_codes2']/2)
        else:
            if not np.any(active):raise ValueError('SNR requires a nonzero designed signal interval')
            power=float(np.mean(np.abs(clean[active])**2))
            sigma=np.sqrt(power/10**(case['noise']['snr_db']/10)/2)
        noise_rng=np.random.default_rng(np.random.SeedSequence([case['seed'],0x4157474e]))
        added=sigma*(noise_rng.standard_normal(len(value))+1j*noise_rng.standard_normal(len(value)))
    value=clean+added+complex(*case['offset_iq'])
    rounded = np.rint(np.column_stack((value.real, value.imag)))
    if not np.all(np.isfinite(rounded)) or np.any(rounded < -32768) or np.any(rounded > 32767):
        raise ValueError('int16 overflow: rejected rather than clipped')
    iq=rounded.astype('<i2')
    noiseless=np.rint(np.column_stack((clean.real,clean.imag))).astype(np.int64)
    noise_quantized=iq.astype(np.int64)-noiseless-np.array(case['offset_iq'])
    details=dict(symbol_intervals=case['design_intervals'] if signal['kind'] in ('qpsk','rrc-qpsk') else [],
        shaped_intervals=shaped,quantized_nonzero_intervals=[list(x) for x in runs(np.any(iq!=0,axis=1))],
        noiseless_quantized_nonzero_intervals=[list(x) for x in runs(np.any(noiseless!=0,axis=1))],
        truth_intervals=shaped if case.get('truth_basis')=='shaped' else case['design_intervals'],
        papr_db=float(10*np.log10(np.max(np.abs(clean[active])**2)/np.mean(np.abs(clean[active])**2))) if np.any(active) else None,
        component_peak_codes=int(np.max(np.abs(iq.astype(np.int64)))),
        component_headroom_codes=int(min(32767-int(iq.max()),int(iq.min())+32768)))
    if signal['kind']=='rrc-qpsk':
        details.update(symbol_rate_baud=FS/signal['sps'],rrc_tap_count=signal['span_symbols']*signal['sps']+1,
                       ideal_support_hz=(1+signal['rolloff'])*FS/signal['sps'])
    if case['noise']['kind']=='awgn' and np.any(active):
        details.update(measured_snr_before_quantization_db=float(10*np.log10(np.mean(np.abs(clean[active])**2)/np.mean(np.abs(added[active])**2))),
            measured_snr_after_quantization_db=float(10*np.log10(np.mean(np.sum(noiseless[active]**2,axis=1))/np.mean(np.sum(noise_quantized[active]**2,axis=1)))))
    if 'power_codes2' in case['noise']:
        details.update(configured_noise_power_codes2=case['noise']['power_codes2'],
                       measured_noise_power_codes2=float(np.mean(np.sum(noise_quantized**2,axis=1))))
    applied=dict(case['detector'])
    policy=case.get('threshold_policy',{'kind':'fixed'})
    if policy['kind']=='quiet-prefix':
        length=policy['samples']
        if not 16<=length<=len(iq) or any(a<length for a,b in shaped):
            raise ValueError('Noise estimation requires the declared leading quiet interval')
        background=float(np.mean(np.sum(iq[:length].astype(np.int64)**2,axis=1)))
        applied['ton']=max(2,int(np.ceil(16*background*policy['on_multiple'])))
        applied['toff']=max(1,min(applied['ton']-1,int(np.ceil(16*background*policy['off_multiple']))))
        details['estimated_background_power']=background
    elif policy['kind']!='fixed':raise ValueError('Unknown threshold policy')
    validate_detector(applied);details['applied_detector']=applied
    if case['replay']=='cyclic':
        quiet=max(47,applied['gap_min'],applied['koff']+15)
        if np.any(iq[:quiet]) or np.any(iq[-quiet:]):raise ValueError('Cyclic oracle requires an exact quiet seam')
    return value,iq,details


def waveform(case):
    floating,iq,_=waveform_details(case)
    return floating,iq


def generate(spec_path, out):
    spec_path, out = Path(spec_path), Path(out)
    spec = json.loads(spec_path.read_text(encoding='utf-8'))
    if spec['schema'] != 'iq-qualification-spec-v1' or not spec['cases']:
        raise ValueError('Unsupported or empty qualification specification')
    identifiers = [case['id'] for case in spec['cases']]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError('Duplicate case id')
    # Validate every waveform before creating output; never overwrite old evidence.
    signals = [(case, *waveform_details(case)) for case in spec['cases']]
    out.mkdir(parents=True, exist_ok=False)
    (out / 'spec.json').write_bytes(spec_path.read_bytes())
    manifest = dict(schema='iq-qualification-manifest-v1', spec='spec.json',
                    spec_sha256=digest(spec_path), generator_sha256=digest(__file__), cases=[])
    for case, floating, iq, details in signals:
        binary = out / (case['id'] + '.bin')
        binary.write_bytes(iq.tobytes())
        row = dict(case, binary=binary.name, sha256=digest(binary), floating_windows=[],measurement_design=details,
                   applied_detector=details['applied_detector'])
        for wid in range(len(iq)//N):
            x = floating[wid*N:(wid+1)*N]
            row['floating_windows'].append(dict(window_id=wid,
                peak_codes=float(np.max(np.abs(x))), rms_codes=float(np.sqrt(np.mean(np.abs(x)**2)))))
        manifest['cases'].append(row)
    path = out / 'manifest.json'
    path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(generate(args.spec, args.out))
