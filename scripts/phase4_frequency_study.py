"""Frozen, offline full-spectrum carrier semantics experiment; not a PL result."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
from phase4_ofdm import ROOT,FS,N,make_case,waveform
from generate_iq_vectors import rrc_taps

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

def estimates(iq):
    # Periodic Hann, full 8192 bins. Snapshot maxima are never used.
    w=.5-.5*np.cos(2*np.pi*np.arange(N)/N)
    p=np.abs(np.fft.fftshift(np.fft.fft((iq[:,0]+1j*iq[:,1])*w)))**2
    k=int(np.argmax(p));cdf=np.cumsum(p)
    lo=int(np.searchsorted(cdf,cdf[-1]*.005));hi=int(np.searchsorted(cdf,cdf[-1]*.995))
    f=(np.arange(N)-N/2)*FS/N
    interpolated=None
    if 0<k<N-1 and np.all(p[k-1:k+2]>0):
        y=np.log(p[k-1:k+2]);den=y[0]-2*y[1]+y[2]
        delta=.5*(y[0]-y[2])/den if den<0 else np.nan
        if np.isfinite(delta) and abs(delta)<=.5:interpolated=float(f[k]+delta*FS/N)
    return dict(peak=float(f[k]),bandwidth_center=float((f[lo]+f[hi])/2),
        centroid=float(np.dot(f,p)/p.sum()),tone_log_parabola=interpolated,
        occupied_bandwidth_hz=float(f[hi]-f[lo]))

def clean(kind,seed):
    rng=np.random.default_rng(np.random.SeedSequence([seed,0x46524551]))
    if kind=='tone':return np.full(N,3000,dtype=complex)
    if kind=='rrc_qpsk':
        taps=rrc_taps(.35,4,16)
        count=N//4+64
        d=((2*rng.integers(0,2,count)-1)+1j*(2*rng.integers(0,2,count)-1))/np.sqrt(2)
        u=np.zeros(count*4,complex);u[::4]=d
        return np.convolve(u,taps)[128:128+N]*6000
    c=make_case(85,'qpsk',seed,gain=3000)
    c['signal']['active_half']=700
    return waveform(c)[0][N:2*N]

def measure(kind,seed,shift,snr):
    x=clean(kind,seed)*np.exp(2j*np.pi*shift*np.arange(N)/FS)
    rng=np.random.default_rng(np.random.SeedSequence([seed,0x4e4f4953,int(snr)]))
    noise=np.sqrt(np.mean(abs(x)**2)/10**(snr/10)/2)*(rng.standard_normal(N)+1j*rng.standard_normal(N))
    rounded=np.rint(np.c_[(x+noise).real,(x+noise).imag])
    if rounded.min()<-32768 or rounded.max()>32767:raise ValueError('Overflow; no clipping or seed replacement')
    iq=rounded.astype('<i2');est=estimates(iq)
    truth_bw=estimates(np.c_[x.real,x.imag])['occupied_bandwidth_hz']
    tolerance=FS/N*.1 if kind=='tone' else max(2*FS/N,.005*truth_bw)
    errors={k:None if est[k] is None else abs(est[k]-shift) for k in ('peak','bandwidth_center','centroid','tone_log_parabola')}
    return iq,dict(kind=kind,seed=seed,true_frequency_hz=shift,snr_db=snr,estimates=est,
        noiseless_bandwidth_hz=truth_bw,exploratory_tolerance_hz=tolerance,absolute_errors_hz=errors)

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=False);(a.out/'vectors').mkdir()
    source={str(p):sha(p) for p in (Path(__file__),ROOT/'scripts/phase4_ofdm.py',ROOT/'tests/generate_iq_vectors.py')}
    spec=dict(status='FROZEN_BEFORE_VALIDATION',scope='OFFLINE_ONLY: periodic Hann / full 8192 floating-point spectrum',
        independent_seeds=[221000,221019],grouped_seeds=True,shifts_hz=[-12000000,-6000000,0,6000000,12000000],
        snrs_db=[10,20,30],signals=['tone','rrc_qpsk','ofdm'],source_sha256=source,
        method='Fixed log-power three-bin parabolic interpolation for single tone only; no tuning on validation',
        wide_tolerance='max(2 bins, 0.5% noiseless 99% OBW); internal exploratory criterion, not competition requirement',
        tone_tolerance='P95 <=0.1 bin at SNR>=20dB',additional_tone_offsets_bin=[-.5,-.49,-.25,0,.25,.49,.5])
    save(a.out/'specification.json',spec);rows=[]
    for kind in spec['signals']:
        for shift in spec['shifts_hz']:
            for snr in spec['snrs_db']:
                for seed in range(221000,221020):
                    iq,row=measure(kind,seed,shift,snr)
                    raw=a.out/'vectors'/f'{kind}_{shift}_{snr}_{seed}.bin';raw.write_bytes(iq.tobytes())
                    row.update(raw=raw.name,sha256=sha(raw));rows.append(row)
    extra=[]
    for offset in spec['additional_tone_offsets_bin']:
        for snr in (20,30):
            for seed in range(221100,221120):
                iq,row=measure('tone',seed,(700+offset)*FS/N,snr)
                raw=a.out/'vectors'/f'halfbin_{offset}_{snr}_{seed}.bin';raw.write_bytes(iq.tobytes())
                row.update(raw=raw.name,sha256=sha(raw));extra.append(row)
    summary=[]
    for kind in spec['signals']:
        for snr in spec['snrs_db']:
            group=[r for r in rows if r['kind']==kind and r['snr_db']==snr]
            for method in ('peak','bandwidth_center','centroid','tone_log_parabola'):
                if method=='tone_log_parabola' and kind!='tone':continue
                errors=[r['absolute_errors_hz'][method] for r in group if r['absolute_errors_hz'][method] is not None]
                summary.append(dict(kind=kind,snr_db=snr,method=method,count=len(group),valid=len(errors),
                    p95_error_hz=float(np.percentile(errors,95)),max_error_hz=max(errors),
                    within_exploratory_tolerance=sum(r['absolute_errors_hz'][method] is not None and r['absolute_errors_hz'][method]<=r['exploratory_tolerance_hz'] for r in group)))
    errors=[r['absolute_errors_hz']['tone_log_parabola'] for r in rows+extra if r['kind']=='tone' and r['snr_db']>=20]
    result=dict(status='COMPLETE',scope=spec['scope'],specification_sha256=sha(a.out/'specification.json'),
        primary_cases=len(rows),half_bin_cases=len(extra),summary=summary,
        tone_candidate=dict(valid=all(e is not None for e in errors),p95_error_bins=float(np.percentile(errors,95)/(FS/N)),
            target_met=bool(all(e is not None for e in errors) and np.percentile(errors,95)<=.1*FS/N),production_exposed=False),
        cases=rows,half_bin_cases_detail=extra)
    assert source=={p:sha(p) for p in source}
    save(a.out/'study.json',result);print('FREQUENCY_STUDY_COMPLETE',result['tone_candidate'],flush=True)

if __name__=='__main__':main()
