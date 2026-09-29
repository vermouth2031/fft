"""Freeze and check new-rate signals, boundary semantics and continuous service."""
import argparse
import contextlib
import datetime
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT/'tests'), str(ROOT/'host')]
import numpy as np
from fft_reference import FFTReference, FS, N, digest
from generate_qualification_vectors import DEFAULT_DETECTOR, waveform_details
from make_phase2_specs import case, qpsk
from phase4_ofdm import make_case, waveform as ofdm_waveform
from validate_measurements import bindings, check_bindings
from qualification_capture import capture as capture_one
from verify_board_capture import verify, require
from package_release import check
from package_validated import check_board
from record_boot_stage import verify_boot
from phase4_identity import check_identity
from iq_client import Client


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def waveform(kind, seed):
    rng = np.random.default_rng(seed)
    start, end = 2048, 26624
    t = np.arange(end-start)/FS
    phase = rng.uniform(-np.pi, np.pi, 2)
    x = np.zeros(32768, dtype=complex)
    truth = dict(kind=kind, seed=seed, sample_rate_hz=FS, active_interval=[start,end],
                 active_seconds=(end-start)/FS, phases_rad=phase.tolist())
    if kind == 'tone':
        truth.update(frequency_hz=12000000, amplitude=7000)
        x[start:end] = 7000*np.exp(1j*(2*np.pi*12e6*t+phase[0]))
    elif kind == 'two_tone':
        truth.update(frequencies_hz=[-17000000,23000000], amplitudes=[6000,3000])
        x[start:end] = 6000*np.exp(1j*(2*np.pi*-17e6*t+phase[0]))+3000*np.exp(1j*(2*np.pi*23e6*t+phase[1]))
    elif kind == 'chirp':
        slope = 40e6/((end-start)/FS)
        truth.update(start_hz=-20000000, stop_hz_exclusive=20000000, amplitude=7000)
        x[start:end] = 7000*np.exp(1j*(2*np.pi*(-20e6*t+.5*slope*t*t)+phase[0]))
    elif kind == 'qpsk':
        spec = case('rate_qpsk', qpsk(5000,shaped=True,sps=4,alpha=.35),
                    seed=seed, intervals=[[start,end]])
        x, iq, details = waveform_details(spec)
        interval=details['shaped_intervals'][0]
        truth.update(specification=spec, details=details, symbol_rate_baud=FS/4,
                     design_interval=[start,end],active_interval=interval,active_seconds=(interval[1]-interval[0])/FS)
        return iq, truth
    elif kind == 'ofdm':
        spec = make_case(85,'qam16',seed,gain=3500)
        x, iq, details = ofdm_waveform(spec)
        interval=details['signal_interval']
        truth.update(specification=spec, details=details, active_interval=interval,active_seconds=(interval[1]-interval[0])/FS)
        return iq, truth
    else:
        raise ValueError(kind)
    rounded = np.rint(np.c_[x.real,x.imag])
    require(rounded.min()>=-32768 and rounded.max()<=32767, 'Input overflow, no seed replacement')
    return rounded.astype('<i2'), truth


def prepare(out, compatible_vectors):
    require(FS==125000000, 'This holdout is declared for 125 MSPS')
    require(out.is_relative_to(ROOT/'build'), 'Rate references must stay inside build/')
    out.mkdir(parents=True,exist_ok=False)
    for folder in ('vectors','references'): (out/folder).mkdir()
    spec = dict(sample_rate_hz=FS, kinds=['tone','two_tone','chirp','qpsk','ofdm'],
                seeds=list(range(311000,311008)), windows=['rect','hann'],
                detectors=['threshold','digital-zero'], finite_cases=160,
                boundary_cases=32, continuous_seconds=[10,60,300],
                continuous_detector='threshold', continuous_signal='ofdm', continuous_seed=311005,
                scope='New declared physical signals; boundary cases check exact semantics, not universal detection',
                continuous_scope='Cyclic 32768-pair RAM replay; no claim of unique external input',
                fifo_high_water_limit_exclusive=1024, normal_analysis_target_us=150,
                compatibility_scope='Same saved I/Q integers as the qualified 100 MSPS build, interpreted at 125 MSPS')
    save(out/'specification.json',spec)
    source = bindings()
    for path in (Path(__file__),ROOT/'scripts/phase4_ofdm.py',out/'specification.json'):
        source[str(path.resolve())]=digest(path)
    inputs=[]
    for kind in spec['kinds']:
        for seed in spec['seeds']:
            iq, truth=waveform(kind,seed)
            inputs.append(dict(label=f'{kind}_{seed}',group='finite',iq=iq,truth=truth,
                               windows=['rect','hann'],detectors=spec['detectors'],seconds=0))
    frequencies=[-FS/2,-FS/2+.5*FS/N,-.5*FS/N,0,.5*FS/N,FS/2-.5*FS/N,-12500000.5,12500000.5]
    for i, frequency in enumerate(frequencies):
        x=np.zeros(32768,complex);x[32:32736]=7000*np.exp(2j*np.pi*frequency*np.arange(32704)/FS)
        iq=np.rint(np.c_[x.real,x.imag]).astype('<i2')
        inputs.append(dict(label=f'frequency_boundary_{i}',group='boundary',iq=iq,
                           truth=dict(frequency_hz=frequency,active_interval=[32,32736]),
                           windows=['hann'],detectors=spec['detectors'],seconds=0))
    intervals=[(0,1),(0,2),(0,31),(32,64),(8190,8193),(100,132),(100,32768),(0,32768)]
    for i,(start,end) in enumerate(intervals):
        x=np.zeros(32768,complex);x[start:end]=7000*np.exp(2j*np.pi*.25*np.arange(end-start))
        inputs.append(dict(label=f'length_boundary_{i}',group='boundary',iq=np.rint(np.c_[x.real,x.imag]).astype('<i2'),
                           truth=dict(active_interval=[start,end],physical_seconds=(end-start)/FS),
                           windows=['hann'],detectors=spec['detectors'],seconds=0))
    for seconds in spec['continuous_seconds']:
        iq,truth=waveform('ofdm',spec['continuous_seed'])
        inputs.append(dict(label=f'continuous_{seconds}s',group='continuous',iq=iq,truth=truth,
                           windows=['hann'],detectors=['threshold'],seconds=seconds))
    for path in sorted(compatible_vectors.glob('*.bin')):
        iq=np.fromfile(path,dtype='<i2').reshape(-1,2)
        require(iq.shape==(32768,2),'Unexpected compatibility vector shape')
        inputs.append(dict(label='same_iq_'+path.stem,group='same_iq',iq=iq,
                           truth=dict(original_rate_hz=100000000,source_name=path.name,original_sha256=digest(path)),
                           windows=['rect','hann'],detectors=spec['detectors'],seconds=0))
    require(sum(r['group']=='same_iq' for r in inputs)==8,'Expected eight frozen integer vectors')
    index=dict(status='PREPARED',specification=str(out/'specification.json'),bindings=source,cases=[])
    with FFTReference() as model:
        source[model.identity['archive_path']]=model.identity['archive_sha256']
        source[model.identity['dll_path']]=model.identity['dll_sha256']
        for row in inputs:
            support=np.flatnonzero(np.any(row['iq']!=0,axis=1))
            row['truth']['quantized_support']=[int(support[0]),int(support[-1])+1] if len(support) else None
            vector=out/'vectors'/(row['label']+'.bin');vector.write_bytes(row['iq'].tobytes())
            for window in row['windows']:
                results=[model.window(row['iq'][wid*N:(wid+1)*N],window,wid) for wid in range(4)]
                for detector in row['detectors']:
                    label=row['label']+'_'+window+'_'+detector
                    d=dict(DEFAULT_DETECTOR,mode=detector)
                    oracle=dict(schema='iq-qualification-reference-v1',case_id=label,mode=window,
                                input_sha256=digest(vector),sample_rate_hz=FS,detector=d,
                                replay='cyclic' if row['seconds'] else 'finite',bindings=source,
                                model=model.identity,windows=[r[0] for r in results],snapshots=[r[2].tolist() for r in results])
                    reference=out/'references'/(label+'.json');save(reference,oracle)
                    index['cases'].append(dict(label=label,group=row['group'],vector=str(vector),
                        vector_sha256=digest(vector),reference=str(reference),reference_sha256=digest(reference),
                        window=window,detector=d,seconds=row['seconds'],truth=row['truth']))
    require(sum(r['group']=='finite' for r in index['cases'])==160,'Incomplete finite grid')
    require(sum(r['group']=='boundary' for r in index['cases'])==32,'Incomplete boundary grid')
    check_bindings(source);save(out/'index.json',index)
    print('RATE_REFERENCES_PREPARED',len(index['cases']),flush=True)


def capture(index_path,out,groups,board):
    check();verify_boot();accepted=check_board()
    require(out.is_relative_to(ROOT/'captures'), 'Rate captures must stay inside captures/')
    index=json.loads(index_path.read_text());check_bindings(index['bindings'])
    out.mkdir(parents=True,exist_ok=False)
    report=dict(status='RUNNING',hardware=accepted['hardware'],references=str(index_path),
                reference_sha256=digest(index_path),groups=groups,cases=[],started_at=datetime.datetime.now().astimezone().isoformat())
    save(out/'validation.json',report)
    client=Client(board)
    try:check_identity(client.hardware_info('digital-zero'));require(client.read(8)[0]&7==0,'Board is busy')
    finally:client.close()
    try:
        for row in index['cases']:
            if row['group'] not in groups:continue
            vector,reference=Path(row['vector']),Path(row['reference'])
            require(digest(vector)==row['vector_sha256'] and digest(reference)==row['reference_sha256'],'Reference changed')
            folder=out/row['label'];print('RATE_CASE_START',row['label'],flush=True)
            with (out/(row['label']+'.log')).open('w',encoding='utf-8') as log,contextlib.redirect_stdout(log):
                capture_one(SimpleNamespace(board=board,port=5001,vector=str(vector),out=str(folder),window=row['window'],
                    cyclic=bool(row['seconds']),seconds=row['seconds'] or 1,detector=row['detector']['mode'],gap_min=32),row['detector'])
            result=verify(folder,vector,qualification=reference)
            meta=json.loads((folder/'capture.json').read_text())
            require(meta['build_id']==accepted['hardware']['build_id'] and meta['throughput_conservation_valid'],'Identity/conservation failed')
            high=meta['throughput_diagnostics']['input_fifo_high_water']
            require(high<1024,'FIFO exceeds preliminary 25% capacity budget')
            result.update(label=row['label'],group=row['group'],seconds=row['seconds'],input_fifo_high_water=high,
                          analysis_target_met=result['maximum_analysis_us']<=150,truth=row['truth'])
            save(folder/'measurement_validation.json',result);report['cases'].append(result);save(out/'validation.json',report)
            print('RATE_CASE_PASS',row['label'],result['maximum_analysis_us'],flush=True)
        require(bool(report['cases']),'No selected rate cases')
        report.update(status='PASS',maximum_analysis_us=max(r['maximum_analysis_us'] for r in report['cases']),
                      maximum_fifo_high_water=max(r['input_fifo_high_water'] for r in report['cases']),
                      analysis_target_status='PASS' if all(r['analysis_target_met'] for r in report['cases']) else 'FAIL')
    except Exception as e:
        report.update(status='FAIL',error=str(e));raise
    finally:
        report['finished_at']=datetime.datetime.now().astimezone().isoformat();save(out/'validation.json',report)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','capture'])
    p.add_argument('--out',type=Path,required=True);p.add_argument('--references',type=Path)
    p.add_argument('--compatible-vectors',type=Path);p.add_argument('--board',default='192.168.1.10')
    p.add_argument('--groups',nargs='+',default=['finite','boundary','same_iq'])
    a=p.parse_args()
    if a.action=='prepare':
        if not a.compatible_vectors:p.error('--compatible-vectors is required')
        prepare(a.out.resolve(),a.compatible_vectors.resolve())
    else:
        if not a.references:p.error('--references is required')
        capture(a.references.resolve(),a.out.resolve(),a.groups,a.board)
