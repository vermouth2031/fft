"""Training-only threshold search; independent validation is a separate step."""
import argparse
import collections
import itertools
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
import numpy as np
from generate_qualification_vectors import waveform_details
from make_phase2_specs import case,qpsk
from threshold_reference import runs
from detection_metrics import evaluate


def features(iq):
    x=iq.astype(np.int64);p=x[:,0]**2+x[:,1]**2
    prefix=np.r_[0,np.cumsum(p)]
    return prefix[1:]-prefix[np.maximum(0,np.arange(len(p))-15)],float(p[:1024].mean())


def intervals(sliding, ton, toff, kon, koff):
    on=[(a,b) for a,b in runs(sliding>ton) if b-a>=kon]
    off=[(a,b) for a,b in runs(sliding<toff) if b-a>=koff]
    cursor=0;result=[];j=0
    for a,b in on:
        start=max(a,cursor)
        if b-start<kon:continue
        while j<len(off) and off[j][1]-max(off[j][0],start+kon)<koff:j+=1
        end=max(off[j][0],start+kon) if j<len(off) else len(sliding)
        result.append([start,end])
        if j==len(off):break
        cursor=end+koff
    return result


def training(seeds):
    frames=[[2048+i*8192,6144+i*8192] for i in range(4)]
    items=[]
    for snr in (30,20,10,5,0):
        for seed in seeds:
            # 4096 leaves int16 headroom at 0dB; no clipping or seed rejection.
            c=case(f'train_{snr}_{seed}',qpsk(4096),intervals=frames,seed=seed,
                   snr=snr,policy='quiet-prefix',windows=['hann'])
            _,iq,detail=waveform_details(c)
            s,b=features(iq)
            items.append(dict(snr=snr,seed=seed,sliding=s,background=b,truth=frames))
    return items


def noise(seeds):
    items=[]
    for seed in seeds:
        rng=np.random.default_rng(seed)
        iq=np.rint(rng.normal(0,1024,(32768,2))).astype('<i2')
        s,b=features(iq);items.append(dict(snr=None,seed=seed,sliding=s,background=b,truth=[]))
    return items


def assess(params, items):
    aon,aoff,kon,koff=params;groups=collections.defaultdict(collections.Counter)
    for item in items:
        ton=max(1,int(np.ceil(16*item['background']*aon)))
        toff=min(ton-1,int(np.ceil(16*item['background']*aoff)))
        got=intervals(item['sliding'],ton,toff,kon,koff)
        m=evaluate(item['truth'],got,32768)
        g=groups[str(item['snr'])]
        for k in ('known_bursts','normal_matches','matched','missed','false_alarms','merged_detections','split_truths'):
            g[k]+=m[k]
    return dict(parameters=dict(on_multiple=aon,off_multiple=aoff,kon=kon,koff=koff),groups=dict(groups))


def rank(row):
    g=row['groups'];high=sum(g[str(s)]['known_bursts']-g[str(s)]['normal_matches'] for s in (30,20,10))
    false=sum(v['false_alarms'] for v in g.values())
    splits=sum(v['split_truths'] for v in g.values())
    return (false,high,-g['5']['normal_matches'],splits,-g['0']['normal_matches'],-g['0']['matched'])


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    coarse=training(range(110000,110004))+noise(range(111000,111016))
    grid=[x for x in itertools.product((2,2.5,3,3.5,4),(1.25,1.5,1.75,2),(4,8,12,16),(8,16,24,32)) if x[1]<x[0]]
    rows=[];start=time.monotonic()
    for i,params in enumerate(grid):
        rows.append(assess(params,coarse))
        if i%40==0:print('COARSE',i,len(grid),round(time.monotonic()-start,1),flush=True)
    rows.sort(key=rank)
    full=training(range(110000,110032))+noise(range(111000,111256))
    finalists=[]
    candidates=[tuple(row['parameters'].values()) for row in rows[:12]]
    if (4,2,8,32) not in candidates:candidates.append((4,2,8,32))
    for params in candidates:
        r=assess(params,full);finalists.append(r);print('FULL',r,flush=True)
    finalists.sort(key=rank)
    # Check the interval-only search against the existing independent full oracle.
    from threshold_reference import reference_threshold
    from generate_qualification_vectors import DEFAULT_DETECTOR
    selected=finalists[0]['parameters'];frames=[[2048+i*8192,6144+i*8192] for i in range(4)]
    checked=0
    for snr in (30,20,10,5,0):
        c=case(f'consistency_{snr}',qpsk(4096),intervals=frames,seed=110005,snr=snr,policy='quiet-prefix',windows=['hann'])
        _,iq,_=waveform_details(c);s,b=features(iq)
        d=dict(DEFAULT_DETECTOR,ton=int(np.ceil(16*b*selected['on_multiple'])),toff=int(np.ceil(16*b*selected['off_multiple'])),kon=selected['kon'],koff=selected['koff'])
        ref=reference_threshold(iq,d)
        assert intervals(s,d['ton'],d['toff'],d['kon'],d['koff'])==[[x['start_sample'],x['end_sample']] for x in ref]
        checked+=1
    result=dict(scope='OFFLINE_TRAINING_ONLY_NOT_PHYSICAL_BOARD_OR_INDEPENDENT_ACCEPTANCE',
        amplitude_codes=4096,training_seeds=list(range(110000,110032)),noise_seeds=list(range(111000,111256)),
        pure_noise_observation_seconds=256*32768/1e8,ranking='background false alarms, high-SNR normal failures, 5dB normal matches, splits, 0dB normal/matched',
        selected=selected,finalists=finalists,coarse=rows,interval_oracle_consistency_cases=checked)
    (a.out/'training.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('TRAINING_COMPLETE',selected,flush=True)


if __name__=='__main__':main()
