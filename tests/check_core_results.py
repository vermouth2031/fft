from pathlib import Path
import argparse,json,math
import numpy as np
from fft_reference import FS
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--partial',action='store_true');args=parser.parse_args()
gold=json.loads((ROOT/'data/golden_results.json').read_text())['cases']
path=ROOT/'build/vivado/iq_analyzer.sim/sim_1/behav/xsim/core_results.txt'
seen=set();bursts={};latencies=[]
def s32(x):return x if x<2**31 else x-2**32
for line in path.read_text().splitlines():
    f=line.split()
    if len(f) not in (18,34):
        if args.partial:continue
        raise AssertionError('Truncated result line')
    kind,c=f[:2];c=int(c);w=[int(x,16) for x in f[2:]]
    def u64(i):return w[i]|(w[i+1]<<32)
    if kind=='F':
        e=gold[c]['windows'][w[3]]; key=(c,w[3]);assert key not in seen;seen.add(key)
        actual=dict(window_id=w[3],total=u64(23),peak_power=u64(25),q_peak=w[19]&65535,q_low=w[19]>>16,q_high=w[20]&65535,
          f_peak_hz=s32(w[14]),f_low_hz=s32(w[15]),f_high_hz=s32(w[16]),bandwidth_hz=w[17],center_hz=s32(w[18]),
          energy=u64(27),peak_uq16_16=w[21],rms_uq16_16=w[22])
        for field,value in e.items():assert actual[field]==value,(key,field,actual[field],value)
        flags=(1 if e['total']==0 else 0)|(32 if e['total'] and e['q_low']==e['q_high'] else 0)|(16 if e['total'] and (e['q_low']==0 or e['q_high']==8191) else 0)
        assert w[0]==0x46525131 and w[1]==flags and w[5]==FS and w[13]==8192
        assert u64(6)==w[3]*8192 and u64(10)-u64(8)==w[12]
        assert 0<w[12]*1000<=FS*2
        latencies.append(w[12])
    elif kind=='B':
        expected=gold[c]['bursts'][len(bursts.get(c,[]))].copy()
        if not expected['complete']:
            iq=np.fromfile(ROOT/'data/vectors'/(gold[c]['name']+'.bin'),dtype='<i2').reshape(-1,2).astype(np.int64)
            p=(iq[expected['start']:]**2).sum(axis=1);m=len(p);energy=int(p.sum())
            expected.update(end_exclusive=32768,samples=m,energy=energy,peak_uq16_16=math.isqrt(int(p.max())<<32),rms_uq16_16=math.isqrt((energy<<32)//m))
        actual=dict(start=u64(6),end_exclusive=u64(8),samples=w[10],peak_uq16_16=w[11],rms_uq16_16=w[12],energy=u64(13))
        for field,value in actual.items():assert expected[field]==value,(c,field,value,expected[field])
        assert w[0]==0x42525331 and w[1]==(0 if expected['complete'] else 256)
        bursts.setdefault(c,[]).append(actual)
if not args.partial:
    assert len(seen)==64,len(seen)
    for c,g in enumerate(gold):assert len(bursts.get(c,[]))==len(g['bursts']),(c,'burst count')
report=dict(status='PARTIAL' if args.partial else 'PASS',frequency_records=len(seen),burst_records=sum(map(len,bursts.values())),
  exact_fft_points=len(seen)*8192,maximum_analysis_latency_cycles=max(latencies,default=0),
  maximum_analysis_latency_us=max(latencies,default=0)*1e6/FS,oracle='AMD FFT bit-accurate C model + independent integer time/burst reference')
print(json.dumps(report,indent=2))
if not args.partial:
    (ROOT/'reports').mkdir(exist_ok=True)
    (ROOT/'reports/core_validation.json').write_text(json.dumps(report,indent=2)+'\n')
