"""Offline, separately seeded DC/window feasibility study; never changes RTL."""
import argparse
import collections
import hashlib
import itertools
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'tests'), str(ROOT/'scripts')]
import numpy as np
from generate_qualification_vectors import waveform_details
from make_phase2_specs import case, qpsk
from detection_metrics import evaluate
from phase3_tune_detector import intervals

FRAMES = [[2048+i*8192, 6144+i*8192] for i in range(4)]
FIELDS = ('known_bursts','matched','normal_matches','missed','false_alarms','split_truths','merged_detections')


def features(iq, window, remove_dc=False):
    x = iq.astype(np.float64)
    if remove_dc:
        x -= np.rint(x[:1024].mean(axis=0))
    x = x.astype(np.int64)
    power = x[:,0]**2+x[:,1]**2
    prefix = np.r_[0, np.cumsum(power)]
    sliding = prefix[1:]-prefix[np.maximum(0,np.arange(len(power))+1-window)]
    return sliding, float(power[:1024].mean())


def signal(seed, snr, amplitude=4096, offset=(0,0), frames=FRAMES):
    c = case('study', qpsk(amplitude), intervals=frames, seed=seed, snr=snr,
             offset=offset, policy='quiet-prefix', windows=['hann'])
    return waveform_details(c)[1]


def dataset(seeds, noise_seeds, window):
    result=[]
    for snr in (10,5,0):
        for seed in seeds:
            s,p=features(signal(seed,snr),window)
            result.append((str(snr),s,p,FRAMES))
    for seed in noise_seeds:
        x=np.rint(np.random.default_rng(seed).normal(0,1024,(32768,2))).astype('<i2')
        s,p=features(x,window);result.append(('noise',s,p,[]))
    return result


def assess(items, window, params):
    on,off,kon,koff=params;groups=collections.defaultdict(collections.Counter)
    for group,s,p,truth in items:
        ton=max(1,int(np.ceil(window*p*on)));toff=min(ton-1,int(np.ceil(window*p*off)))
        got=intervals(s,ton,toff,kon,koff)
        metric=evaluate(truth,got,len(s))
        for key in FIELDS:groups[group][key]+=metric[key]
        for match in metric['matches']:
            groups[group]['max_abs_boundary_samples']=max(groups[group]['max_abs_boundary_samples'],
                abs(match['start_error_samples']),abs(match['end_error_samples']))
    return dict(window=window,parameters=dict(on_multiple=on,off_multiple=off,kon=kon,koff=koff),groups=dict(groups))


def score(row):
    g=row['groups']
    return (sum(x['false_alarms'] for x in g.values()),
            g['10']['known_bursts']-g['10']['normal_matches'],
            -g['5']['normal_matches'],-g['0']['normal_matches'],-g['0']['matched'])


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);a=parser.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    windows=[]
    grid=[p for p in itertools.product((1.5,1.75,2,2.25,2.5,3),(1.125,1.25,1.5,1.75),(8,16),(8,16)) if p[1]<p[0]]
    for window in (16,32,64):
        train=dataset(range(130000,130008),range(131000,131064),window)
        rows=sorted((assess(train,window,p) for p in grid),key=score)
        chosen=tuple(rows[0]['parameters'].values())
        validation=dataset(range(132000,132032),range(133000,133128),window)
        heldout=assess(validation,window,chosen)
        short=[]
        for length in (32,64,128,512):
            truth=[[8176,8176+length]];items=[]
            for seed in range(134000,134032):
                s,p=features(signal(seed,5,frames=truth),window);items.append((str(length),s,p,truth))
            short.append(assess(items,window,chosen))
        row=dict(training=rows[0],heldout=heldout,short_bursts=short)
        windows.append(row);print('WINDOW_STUDY',json.dumps(row),flush=True)
    dc=[]
    for offset in ((0,0),(512,-512),(2048,-1024),(4096,2048)):
        for remove_dc in (False,True):
            items=[];raw_hashes=[]
            for seed in range(135000,135032):
                x=signal(seed,5,amplitude=1024,offset=offset)
                raw_hashes.append(hashlib.sha256(x.tobytes()).hexdigest())
                s,p=features(x,16,remove_dc);items.append(('5',s,p,FRAMES))
            row=assess(items,16,(3,1.75,16,8));row.update(offset=list(offset),offline_remove_dc=remove_dc,raw_sha256=raw_hashes)
            dc.append(row);print('DC_STUDY',offset,remove_dc,row['groups'],flush=True)
    report=dict(scope='OFFLINE_FEASIBILITY_ONLY; no FPGA DC cancellation or variable window implemented',
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        boundary_tolerance_samples=32,quiet_prefix_assumption='first 1024 samples are known noise-only',
        training_signal_seeds=[130000,130007],training_noise_seeds=[131000,131063],
        heldout_signal_seeds=[132000,132031],heldout_noise_seeds=[133000,133127],
        short_burst_seeds=[134000,134031],dc_seeds=[135000,135031],windows=windows,dc=dc)
    (a.out/'study.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('DETECTOR_STUDY_COMPLETE',flush=True)


if __name__=='__main__':main()
