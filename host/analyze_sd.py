"""Decode and verify all 16 actual SD captures against the AMD integer oracle."""
from pathlib import Path
import argparse,json,struct,math,shutil
from iq_client import export,decode_record
ROOT=Path(__file__).resolve().parents[1]

def analyze(run,out,*,simulation_fixture=False):
    gold=json.loads((ROOT/'data/golden_results.json').read_text())['cases']
    expected_source='RTL simulation parser fixture' if simulation_fixture else 'Zybo SD board capture'
    reports=[]
    for c,g in enumerate(gold):
        d=run/f'C{c:02d}';meta=json.loads((d/'META.JSON').read_text())
        freq=(d/'FREQ.BIN').read_bytes();burst=(d/'BURST.BIN').read_bytes()
        assert len(freq)==512 and len(burst)%64==0,(c,'record file length')
        assert meta['source']==expected_source and meta['capture_complete'],(c,'capture did not complete')
        assert not meta['error_status'] and meta['input_samples']==32768,(c,'hardware counters')
        fr=[freq[i:i+128] for i in range(0,len(freq),128)];br=[burst[i:i+64] for i in range(0,len(burst),64)]
        assert len(br)==len(g['bursts']),(c,'burst count')
        for n,r in enumerate(fr):
            a=decode_record(r,'frequency');e=g['windows'][n]
            assert a['epoch']==meta['epoch'] and a['config_id']==meta['config_id'],(c,n,'record association')
            assert a['sample_rate_hz']==100000000 and a['fft_length']==8192 and a['window']==g['mode']
            assert a['sequence']==n
            mapping={'id':'window_id','total_spectrum_power':'total','peak_spectrum_power':'peak_power',
              'q_peak':'q_peak','q_low':'q_low','q_high':'q_high','peak_hz':'f_peak_hz','low_hz':'f_low_hz',
              'high_hz':'f_high_hz','bandwidth_hz':'bandwidth_hz','bandcenter_hz':'center_hz','raw_energy':'energy'}
            for target,source in mapping.items():assert a[target]==e[source],(c,n,target,a[target],e[source])
            assert a['peak_codes']*65536==e['peak_uq16_16'] and a['rms_codes']*65536==e['rms_uq16_16']
            flags=(1 if e['total']==0 else 0)|(32 if e['total'] and e['q_low']==e['q_high'] else 0)|(16 if e['total'] and (e['q_low']==0 or e['q_high']==8191) else 0)
            assert a['flags_raw']==flags and a['first_sample']==8192*n
            assert 0<a['latency_cycles']<=200000 and a['done_tick']-a['start_tick']==a['latency_cycles']
        iq=list(struct.iter_unpack('<hh',(ROOT/'data/vectors'/(g['name']+'.bin')).read_bytes()))
        for n,r in enumerate(br):
            a=decode_record(r,'burst');e=g['bursts'][n];start=e['start'];end=e['end_exclusive'] if e['complete'] else len(iq)
            assert a['epoch']==meta['epoch'] and a['config_id']==meta['config_id'] and a['sample_rate_hz']==100000000
            assert a['id']==n and a['sequence']==n
            p=[i*i+q*q for i,q in iq[start:end]];energy=sum(p)
            assert (a['start_sample'],a['end_sample_exclusive'],a['length_samples'])==(start,end,end-start)
            assert a['raw_energy']==energy and a['peak_codes']*65536==math.isqrt(max(p)<<32)
            assert a['rms_codes']*65536==math.isqrt((energy<<32)//len(p))
            assert a['flags_raw']==(0 if e['complete'] else 256)
        dest=out/f'C{c:02d}';export(dest,fr,br,meta)
        if (d/'SNAP.BIN').exists():
            raw=(d/'SNAP.BIN').read_bytes();assert len(raw)==8192
            shutil.copyfile(d/'SNAP.BIN',dest/'snapshot.bin')
            (dest/'snapshot.json').write_text(json.dumps(dict(window_id=meta['snapshot_window'],power=list(struct.unpack('<1024Q',raw))))+'\n')
        reports.append(dict(case=c,signal=g['name'],window=g['mode'],status='PASS',
            maximum_latency_us=max(decode_record(r,'frequency')['latency_us'] for r in fr)))
    report=dict(source=expected_source,board_tested=not simulation_fixture,run=str(run.resolve()),status='PASS',
        cases=reports,numerical_reference='AMD bit-accurate FFT and integer time-domain model')
    (out/'board_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(('SD_PARSER_SIMULATION_PASS' if simulation_fixture else 'SD_BOARD_COMPARISON_PASS')+': 16 cases / 64 frequency windows')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();analyze(a.run,a.out)
