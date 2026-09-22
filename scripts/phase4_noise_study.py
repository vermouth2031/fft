"""Over one second of unique AWGN data against the unchanged robust detector."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'scripts')]
from make_phase2_specs import case
from generate_qualification_vectors import waveform_details,generate
from threshold_reference import reference_threshold
from validate_measurements import prepare

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=False);(a.out/'vectors').mkdir()
    sources={str(p):sha(p) for p in (Path(__file__),ROOT/'tests/generate_qualification_vectors.py',ROOT/'tests/threshold_reference.py',ROOT/'tests/make_phase2_specs.py')}
    spec=dict(scope='Offline finite independent blocks; not one uninterrupted hardware acquisition',blocks_per_stratum=1051,
        component_std_codes=[256,1024,4096],seeds=[230000,233152],sample_rate_hz=100000000,samples_per_block=32768,
        quiet_prefix=1024,detector=dict(mode='threshold',on_multiple=3,off_multiple=1.75,kon=16,koff=8),
        source_sha256=sources,board_sample_rule='First three seeds of each noise stratum, selected before evaluation')
    save(a.out/'specification.json',spec);rows=[];board=[];seen=set();summary=[]
    for layer,std in enumerate(spec['component_std_codes']):
        group=[]
        for index in range(1051):
            seed=230000+layer*1051+index
            c=case(f'phase4_noise_std{std}_s{seed}',{'kind':'zero'},intervals=[],seed=seed,
                policy='quiet-prefix',windows=['hann'],category='noise-only',group=f'phase4_noise_std{std}')
            c['noise']=dict(kind='awgn',power_codes2=2*std**2)
            c['detector'].update(kon=16,koff=8)
            c['threshold_policy']=dict(kind='quiet-prefix',samples=1024,on_multiple=3,off_multiple=1.75)
            _,iq,details=waveform_details(c)
            records=reference_threshold(iq,details['applied_detector'])
            raw=a.out/'vectors'/(c['id']+'.bin');raw.write_bytes(iq.tobytes());digest=sha(raw)
            if digest in seen:raise ValueError('Duplicate independent input')
            seen.add(digest)
            row=dict(seed=seed,std=std,raw=raw.name,sha256=digest,detector=details['applied_detector'],
                events=len(records),post_prefix_events=sum(r['start_sample']>=1024 for r in records),records=records)
            rows.append(row);group.append(row)
            if index<3:board.append(c)
        seconds=1051*32768/100000000;post=1051*(32768-1024)/100000000
        events=sum(r['events'] for r in group);post_events=sum(r['post_prefix_events'] for r in group)
        summary.append(dict(component_std_codes=std,unique_blocks=len(group),unique_seconds=seconds,
            post_calibration_seconds=post,false_events=events,post_calibration_false_events=post_events,
            poisson_95_upper_per_second_if_model_applicable=(-np.log(.05)/post if post_events==0 else None)))
        print('NOISE_STRATUM_COMPLETE',std,events,flush=True)
    result=dict(status='COMPLETE',scope=spec['scope'],specification_sha256=sha(a.out/'specification.json'),
        unique_blocks=len(seen),unique_seconds=len(seen)*32768/100000000,
        post_calibration_seconds=len(seen)*(32768-1024)/100000000,summary=summary,cases=rows,
        caveats=['Overlapping 16-sample windows are correlated','Each block resets detector; seams are not observed',
            'Noise strata have separate rates; no universal stationary-noise false-alarm guarantee'])
    assert sources=={p:sha(p) for p in sources}
    save(a.out/'study.json',result)
    board_spec=a.out/'board_sample_spec.json';save(board_spec,dict(schema='iq-qualification-spec-v1',cases=board))
    manifest=generate(board_spec,a.out/'board_vectors')
    index=prepare(manifest,a.out/'board_references')
    print('NOISE_STUDY_COMPLETE',result['unique_seconds'],index,flush=True)

if __name__=='__main__':main()
