"""One predeclared secondary OFDM design after the 90MHz target was met."""
from pathlib import Path
import argparse
import hashlib
import json
import numpy as np
from phase4_ofdm import make_case,waveform,ROOT,FS,SIZE
from phase4_prepare_bandwidth import prepare

def spec(seed,modulation,gain,seconds=0,windows=('rect','hann')):
    c=make_case(95,modulation,seed,gain=gain,seconds=seconds,windows=windows)
    c['id']=c['id'].replace('b95','b98p14')
    c['signal']['active_half']=2010
    c['design_span_mhz']=4020*FS/SIZE/1e6
    return c

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=False)
    rule=dict(active_half=2010,guard_each_side_hz=FS/2-2010*FS/SIZE,
        rationale='One fixed secondary span; no frequency shift and no validation tuning',
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        training_seeds=[212000,212099],validation_seeds=[212100,212119])
    (a.out/'specification.json').write_text(json.dumps(rule,indent=2)+'\n')
    rows=[]
    for seed in range(212000,212100):
        for modulation in ('qpsk','qam16'):
            x,_,_=waveform(spec(seed,modulation,1));rows.append(dict(seed=seed,modulation=modulation,
                component_peak=float(max(abs(x.real).max(),abs(x.imag).max()))))
    gain=min(6000,int(.70*32767/max(r['component_peak'] for r in rows)))
    training=dict(rule,gain=gain,status='FROZEN',policy='Common gain <=6000 and <=70% training component peak',rows=rows)
    train=a.out/'training.json';train.write_text(json.dumps(training,indent=2)+'\n')
    cases=[spec(seed,m,gain) for m in ('qpsk','qam16') for seed in range(212100,212120)]
    prepare(cases,a.out/'finite',train)

if __name__=='__main__':main()
