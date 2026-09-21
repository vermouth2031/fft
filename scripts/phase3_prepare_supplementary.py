"""Reproducible Phase 3 regression/sensitivity specifications and exact references."""
import argparse
import copy
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'scripts')]
from make_phase2_specs import build,case,qpsk
from generate_qualification_vectors import generate
from validate_measurements import prepare


def robust(c):
    c=copy.deepcopy(c)
    c['id']='robust_regression_'+c['id']
    c['detector'].update(kon=16,koff=8)
    c['threshold_policy']=dict(kind='quiet-prefix',samples=1024,on_multiple=3,off_multiple=1.75)
    c['statistics_group']='robust_regression_'+c['statistics_group']
    return c


def specifications():
    old=build();stages={}
    stages['legacy_regression']=sum((old[k] for k in ('s1_complete','s2_validation','s2_boundaries','s3_finite','s3_refinement')),[])
    stages['robust_regression']=[robust(c) for k in ('s2_validation','s2_boundaries') for c in old[k] if c['detector']['mode']=='threshold']
    stages['wide_continuous']=sum((old[k] for k in ('s3_continuous','s3_refinement_continuous','s3_widest_60s')),[])
    sensitivity=[];frames=[[2048+i*8192,6144+i*8192] for i in range(4)]
    for quiet in (256,512,2048):
        for seed in range(122000,122016):
            c=robust(case(f'quiet{quiet}_{seed}',qpsk(4096),intervals=frames,seed=seed,snr=5,
                policy='quiet-prefix',windows=['hann'],group=f'quiet{quiet}_snr5'))
            c['threshold_policy']['samples']=quiet;sensitivity.append(c)
    for std in (256,4096):
        for seed in range(123000,123032):
            c=robust(case(f'noise_std{std}_{seed}',{'kind':'zero'},intervals=[],seed=seed,
                policy='quiet-prefix',windows=['hann'],category='noise-only',group=f'noise_std{std}'))
            c['noise']=dict(kind='awgn',power_codes2=2*std**2);sensitivity.append(c)
    stages['sensitivity']=sensitivity
    return stages


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    for stage,cases in specifications().items():
        spec=a.out/(stage+'_spec.json')
        spec.write_text(json.dumps(dict(schema='iq-qualification-spec-v1',cases=cases),indent=2)+'\n',encoding='utf-8')
        manifest=generate(spec,a.out/stage/'vectors')
        index=prepare(manifest,a.out/stage/'references')
        print('PHASE3_SUPPLEMENTARY_READY',stage,len(json.loads(index.read_text())['cases']),flush=True)


if __name__=='__main__':main()
