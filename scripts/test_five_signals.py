"""Generate five fresh teaching signals and verify ten captures on the accepted board."""
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
import iq_client
from fft_reference import FFTReference, FS, N, digest
from generate_qualification_vectors import DEFAULT_DETECTOR, waveform_details
from phase4_ofdm import make_case, waveform as ofdm_waveform
from phase4_identity import check_identity
from qualification_capture import capture
from verify_board_capture import verify, require
from validate_measurements import bindings, check_bindings


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def generate():
    base = dict(sample_rate_hz=FS, fft_length=N, samples=32768, replay='finite',
                windows=['rect', 'hann'], noise={'kind': 'none'}, offset_iq=[0, 0],
                detector=dict(DEFAULT_DETECTOR, mode='digital-zero'),
                design_intervals=[[2048, 26624]])
    specs = [
        dict(base, id='tone', seed=230901, signal=dict(kind='tone', tones=[dict(bin=1024, amplitude=8000)])),
        dict(base, id='two_tone', seed=230902, signal=dict(kind='two-tone', tones=[dict(bin=-1024, amplitude=6000), dict(bin=1536, amplitude=3000)])),
        dict(base, id='qpsk', seed=230904, signal=dict(kind='rrc-qpsk', sps=4, normalization='rms', amplitude=5000,
             rolloff=0.35, span_symbols=10, carrier_hz=0)),
    ]
    names = {'tone': ('单音', '一个固定音调：+12.5 MHz，幅度8000码值。'),
             'two_tone': ('双音', '同时存在−12.5 MHz和+18.75 MHz两个音调，幅度分别为6000和3000。'),
             'qpsk': ('QPSK通信信号', '随机QPSK数据，25 M符号/秒，RRC滚降0.35；类似连续说话而不是一个固定音。')}
    rows = []
    for spec in specs:
        _, iq, details = waveform_details(spec)
        rows.append(dict(id=spec['id'], name=names[spec['id']][0], explanation=names[spec['id']][1], spec=spec, details=details, iq=iq))
    start, end = 2048, 26624
    t = np.arange(end-start)/FS
    sweep_rate = 40e6/((end-start)/FS)
    x = np.zeros(32768, dtype=complex)
    x[start:end] = 7000*np.exp(2j*np.pi*(-20e6*t+0.5*sweep_rate*t*t))
    iq = np.rint(np.c_[x.real, x.imag])
    require(iq.min() >= -32768 and iq.max() <= 32767, 'Chirp overflow')
    rows.insert(2, dict(id='chirp', name='扫频信号', explanation='音调从−20 MHz逐渐升至接近+20 MHz；每个短窗口只看到其中一段。',
        spec=dict(base, id='chirp', seed=None, signal=dict(kind='linear-chirp', start_hz=-20000000,
             stop_hz_exclusive=20000000, amplitude=7000, sweep_duration_samples=end-start)),
        details=dict(signal_interval=[start,end]), iq=iq.astype('<i2')))
    spec = make_case(95, 'qam16', 230905, gain=4500)
    spec['detector'] = dict(DEFAULT_DETECTOR, mode='digital-zero')
    _, iq, details = ofdm_waveform(spec)
    rows.append(dict(id='ofdm', name='宽带OFDM信号', explanation='许多子载波同时传数据，使用16QAM；像很多不同音调同时出现。', spec=spec, details=details, iq=iq))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--board', default='192.168.1.10')
    parser.add_argument('--out', type=Path, required=True)
    a = parser.parse_args()
    out = a.out.resolve()
    require(out.is_relative_to(ROOT/'captures'), 'Output must be a new captures directory')
    out.mkdir(parents=True, exist_ok=False)
    for name in ('vectors','references','board'): (out/name).mkdir()
    accepted = json.loads((ROOT/'reports/phase4_complete_validation.json').read_text(encoding='utf-8'))
    require(accepted['status']=='PASS', 'Accepted build required')
    for name, value in accepted['artifacts'].items():
        require(digest(ROOT/'artifacts'/name)==value, 'Accepted artifact changed: '+name)
    client = iq_client.Client(a.board)
    try:
        hardware = client.hardware_info('digital-zero')
        check_identity(hardware)
        require(hardware==accepted['hardware'], 'Different hardware build')
        require(client.read(8)[0]&7==0, 'Another capture is active')
    finally: client.close()
    report = dict(status='RUNNING', started_at=datetime.datetime.now().astimezone().isoformat(), hardware=hardware,
        scope='Five newly generated known signals; board measurement, not automatic modulation classification; no added noise.',
        accepted_report_sha256=digest(ROOT/'reports/phase4_complete_validation.json'), cases=[])
    save(out/'validation.json', report)
    rows = generate()
    source = bindings()
    for p in (Path(__file__), ROOT/'scripts/phase4_ofdm.py', ROOT/'reports/phase4_complete_validation.json'):
        source[str(p.resolve())] = digest(p)
    manifest = dict(sample_rate_hz=FS, fft_length=N, detector='digital-zero', gap_min=32, cases=[])
    for row in rows:
        iq = row['iq']
        require(iq.shape==(32768,2) and iq.dtype==np.dtype('<i2'), 'Invalid vector format')
        vector = out/'vectors'/(row['id']+'.bin')
        vector.write_bytes(iq.tobytes())
        active = np.flatnonzero(np.any(iq!=0,axis=1))
        row['vector'] = vector
        row['support'] = [int(active[0]), int(active[-1])+1]
        manifest['cases'].append(dict(id=row['id'], name=row['name'], explanation=row['explanation'],
            spec=row['spec'], details=row['details'], vector=str(vector), sha256=digest(vector),
            quantized_support=row['support'], component_peak=int(np.abs(iq.astype(np.int64)).max())))
    save(out/'manifest.json',manifest)
    source[str(out/'manifest.json')] = digest(out/'manifest.json')
    try:
        with FFTReference() as model:
            source[model.identity['archive_path']] = model.identity['archive_sha256']
            source[model.identity['dll_path']] = model.identity['dll_sha256']
            for row in rows:
                for window in ('rect','hann'):
                    oracle = dict(schema='iq-qualification-reference-v1', case_id=row['id'], mode=window,
                        input_sha256=digest(row['vector']), sample_rate_hz=FS, detector=dict(DEFAULT_DETECTOR,mode='digital-zero'),
                        replay='finite', bindings=source, model=model.identity, windows=[], snapshots=[])
                    for wid in range(4):
                        expected, _, shot = model.window(row['iq'][wid*N:(wid+1)*N], window, wid)
                        oracle['windows'].append(expected); oracle['snapshots'].append(shot.tolist())
                    reference = out/'references'/(row['id']+'_'+window+'.json')
                    save(reference,oracle)
        # All references are frozen before the first measurement.
        for row in rows:
            for window in ('rect','hann'):
                label = row['id']+'_'+window
                folder = out/'board'/label
                reference = out/'references'/(label+'.json')
                print('FIVE_SIGNALS_START',label,flush=True)
                with (out/'board'/(label+'.log')).open('w',encoding='utf-8') as log, contextlib.redirect_stdout(log):
                    capture(SimpleNamespace(board=a.board,port=5001,vector=str(row['vector']),out=str(folder),
                        window=window,cyclic=False,seconds=1,detector='digital-zero',gap_min=32),
                        dict(DEFAULT_DETECTOR,mode='digital-zero'))
                result = verify(folder,row['vector'],qualification=reference)
                meta = json.loads((folder/'capture.json').read_text(encoding='utf-8'))
                require(meta['build_id']==hardware['build_id'] and meta['throughput_conservation_valid'], 'Identity or throughput failed')
                freq = json.loads((folder/'frequency.json').read_text(encoding='utf-8'))
                bursts = json.loads((folder/'burst.json').read_text(encoding='utf-8'))
                require(len(bursts)==1, 'Expected one complete burst')
                b = bursts[0]
                require(b['start_confirmed'] and b['end_confirmed'] and b['start_sample']==row['support'][0]
                        and b['end_sample_exclusive']==row['support'][1], 'Support measurement failed')
                result.update(id=row['id'], name=row['name'], window=window,
                    representative_window=1, representative=freq[1], all_frequency_windows=freq,
                    burst=b, throughput=meta['throughput_diagnostics'], reference_sha256=digest(reference))
                save(folder/'measurement_validation.json',result)
                report['cases'].append(result)
                save(out/'validation.json',report)
                print('FIVE_SIGNALS_PASS',label,flush=True)
        check_bindings(source)
        report.update(status='PASS', finished_at=datetime.datetime.now().astimezone().isoformat(),
            signal_groups=5,captures=10,frequency_records=sum(r['frequency_records'] for r in report['cases']),
            burst_records=sum(r['burst_records'] for r in report['cases']),
            snapshot_values=sum(r['exact_snapshot_values'] for r in report['cases']),
            maximum_analysis_us=max(r['maximum_analysis_us'] for r in report['cases']))
    except Exception as error:
        report.update(status='FAIL',error=str(error));raise
    finally: save(out/'validation.json',report)
    print('FIVE_SIGNALS_COMPLETE',out,flush=True)


if __name__=='__main__': main()
