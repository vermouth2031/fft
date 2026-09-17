"""Independent integer oracles for FFT-independent RTL regression."""
from pathlib import Path
import json, numpy as np
R=Path(__file__).resolve().parents[1]; D=R/'data'
gold=json.loads((D/'golden_results.json').read_text())['cases'][:8]
bursts=[]; ends=[]
for g in gold:
    iq=np.fromfile(D/'vectors'/(g['name']+'.bin'),dtype='<i2').reshape(-1,2).astype(np.int64)
    for n,b in enumerate(g['bursts']):
        start=b['start'];end=b['end_exclusive'] if b['complete'] else len(iq)
        p=np.sum(iq[start:end]**2,axis=1);energy=int(p.sum());peak=int(p.max())
        fields=[(0 if b['complete'] else 256,32),(n,32),(start,64),(end,64),(energy,64),(peak,32)]
        packed=0
        for value,bits in fields:packed=(packed<<bits)|value
        bursts.append(packed)
    ends.append(len(bursts))
(D/'time_expected.mem').write_text(''.join(f'{v:072x}\n' for v in bursts),encoding='ascii')
(D/'time_counts.mem').write_text(''.join(f'{v:08x}\n' for v in ends),encoding='ascii')
rng=np.random.default_rng(7020);N=8192
inputs=[];expected=[];snap=[]
for f in range(12):
    re=rng.integers(-8388608,8388608,N,dtype=np.int64)
    im=rng.integers(-8388608,8388608,N,dtype=np.int64)
    if f==0:re[:]=0;im[:]=0
    if f==1:re[:]=0;im[:]=0;re[0]=1
    if f==2:re[:]=-8388608;im[:]=-8388608
    if f==3:re[:]=0;im[:]=0;re[4096]=200
    if f==4:re[:]=1;im[:]=0
    p=np.roll(re*re+im*im,4096);t=int(p.sum());pk=int(p.max());q=int(np.argmax(p))
    c=np.cumsum(p);lo=int(np.searchsorted(c,(t+199)//200)) if t else 0
    hi=int(np.searchsorted(c,t-t//200)) if t else 0
    flags=(1 if not t else 0)|(32 if t and lo==hi else 0)|(16 if t and (lo==0 or hi==8191) else 0)
    packed=0
    for value,bits in [(flags,32),(f,32),(t,64),(pk,48),(q,16),(lo,16),(hi,16),(0,32)]:packed=(packed<<bits)|value
    expected.append(packed)
    for n in range(N):
        k=int(f'{n:013b}'[::-1],2)
        inputs.append((k<<48)|((int(im[k])&0xffffff)<<24)|(int(re[k])&0xffffff))
    if f==0:snap=list(p.reshape(1024,8).max(axis=1))
(D/'spectrum_input.mem').write_text(''.join(f'{x:016x}\n' for x in inputs),encoding='ascii')
(D/'spectrum_expected.mem').write_text(''.join(f'{x:064x}\n' for x in expected),encoding='ascii')
print('MEASUREMENT_VECTORS_PASS: eight time cases, twelve continuous spectra')
