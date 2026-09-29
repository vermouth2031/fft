"""Offline sensitivity to drifting noise and violated quiet-prefix assumptions."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
import numpy as np
from make_phase2_specs import case,qpsk
from generate_qualification_vectors import waveform_details
from phase3_tune_detector import features,intervals
from detection_metrics import evaluate


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    truth=[[2048+i*8192,6144+i*8192] for i in range(4)]
    results=[];totals=collections.defaultdict(collections.Counter)
    for condition in ('stationary','noise_std_ramp_1_to_2','prefix_64_contaminated','prefix_256_contaminated'):
        for seed in range(136000,136032):
            clean=waveform_details(case('background',qpsk(4096),intervals=truth,seed=seed,windows=['hann']))[1]
            rng=np.random.default_rng(seed+1000)
            scale=np.ones(32768)
            if condition=='noise_std_ramp_1_to_2':scale[1024:]=np.linspace(1,2,32768-1024)
            floating=clean+rng.normal(0,4096/np.sqrt(2*10**.5),(32768,2))*scale[:,None]
            if condition.startswith('prefix_'):
                count=int(condition.split('_')[1]);floating[:count]+=[10000,-10000]
            iq=np.rint(floating).astype(np.int64)
            assert iq.min()>=-32768 and iq.max()<=32767
            iq=iq.astype('<i2');sliding,mean=features(iq)
            power=(iq[:1024].astype(np.int64)**2).sum(axis=1)
            estimates={'mean':mean,'median_8_block_means':float(np.median(power.reshape(8,128).mean(axis=1)))}
            raw=a.out/f'{condition}_{seed}.bin';raw.write_bytes(iq.tobytes())
            for estimator,background in estimates.items():
                detected=intervals(sliding,int(np.ceil(16*3*background)),int(np.ceil(16*1.75*background)),16,8)
                m=evaluate(truth,detected,32768)
                row=dict(condition=condition,seed=seed,estimator=estimator,estimated_power=background,
                    raw=raw.name,raw_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),metrics=m)
                results.append(row)
                group=totals[condition+'/'+estimator]
                for k in ('known_bursts','matched','normal_matches','missed','false_alarms','split_truths','merged_detections'):group[k]+=m[k]
    result=dict(scope='Offline sensitivity only; median estimator is NOT exposed or selected as a production profile',
        assumption='Contamination cases deliberately violate the user-declared quiet-prefix condition; no automatic silence detector is claimed',
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),seeds=[136000,136031],summary=dict(totals),cases=results)
    (a.out/'study.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result['summary'],indent=2));print('BACKGROUND_STUDY_COMPLETE')


if __name__=='__main__':main()
