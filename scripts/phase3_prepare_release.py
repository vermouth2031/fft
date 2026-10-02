"""Generate all frozen Phase 3 specifications, vectors and exact references."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'host'),str(ROOT/'scripts')]
from make_phase2_specs import case,qpsk
from generate_qualification_vectors import generate
from threshold_config import PROFILES
from phase3_prepare_supplementary import specifications
from validate_measurements import prepare


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    profile=PROFILES['robust']
    assert profile==dict(on_multiple=3,off_multiple=1.75,kon=16,koff=8),'Frozen selected profile changed'
    frames=[[2048+i*8192,6144+i*8192] for i in range(4)]
    validation=[];noise=[]
    for snr in (30,20,10,5,0):
        for seed in range(120000,120125):
            validation.append(case(f'robust_snr{snr}_{seed}',qpsk(4096),intervals=frames,seed=seed,
                category='noise-validation',windows=['hann'],snr=snr,policy='quiet-prefix',group=f'robust_snr{snr}'))
    for seed in range(121000,121256):
        c=case(f'noise_{seed}',{'kind':'zero'},intervals=[],seed=seed,category='noise-only',
               windows=['hann'],policy='quiet-prefix',group='noise_only')
        c['noise']=dict(kind='awgn',power_codes2=2*1024**2);noise.append(c)
    for c in validation+noise:
        c['detector'].update(kon=16,koff=8)
        c['threshold_policy'].update(on_multiple=3,off_multiple=1.75)
    stages=dict(validation=validation,noise_only=noise,**specifications())
    for stage,cases in stages.items():
        spec=a.out/(stage+'_spec.json')
        spec.write_text(json.dumps(dict(schema='iq-qualification-spec-v1',cases=cases),indent=2)+'\n',encoding='utf-8')
        manifest=generate(spec,a.out/stage/'vectors')
        index=prepare(manifest,a.out/stage/'references')
        print('PHASE3_RELEASE_REFERENCE_READY',stage,len(json.loads(index.read_text())['cases']),flush=True)


if __name__=='__main__':main()
