"""Explicit OFDM source for Phase 4; unchanged production measurement path."""
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'host')]
from fft_reference import FS,N
from generate_qualification_vectors import DEFAULT_DETECTOR

SIZE=4096
CP=256
SYMBOLS=6
START=1024
END=START+SYMBOLS*(SIZE+CP)
HALVES={85:1740,90:1843,95:1945}


def make_case(band,modulation,seed,*,gain,carrier_hz=0,windows=('rect','hann'),seconds=0,boundary=False):
    return dict(id=f'ofdm_b{band}_{modulation}_s{seed}_f{int(carrier_hz)}'+(f'_t{seconds}' if seconds else ''),
        signal=dict(kind='ofdm',ifft_length=SIZE,cyclic_prefix=CP,symbols=SYMBOLS,
            active_half=HALVES[band],modulation=modulation,gain=gain,carrier_hz=carrier_hz,
            pilot_period=32,dc_null=True),seed=seed,samples=32768,sample_rate_hz=FS,fft_length=N,
        design_intervals=[[START,END]],windows=list(windows),replay='cyclic' if seconds else 'finite',
        seconds=seconds or 1,detector=dict(DEFAULT_DETECTOR),
        design_span_mhz=band,boundary_test=boundary,
        crosses_nyquist=HALVES[band]*FS/SIZE+abs(carrier_hz)>=FS/2)


def symbols(case):
    s=case['signal'];half=s['active_half']
    if not (case['sample_rate_hz']==FS and case['fft_length']==N and case['samples']==32768):
        raise ValueError('OFDM experiment requires actual 100MSPS/8192 configuration')
    if s['ifft_length']!=SIZE or s['cyclic_prefix']!=CP or s['symbols']!=SYMBOLS or not 1<=half<SIZE//2:
        raise ValueError('Unsupported OFDM dimensions')
    if s['modulation'] not in ('qpsk','qam16') or not 0<s['gain']<=32767:
        raise ValueError('Invalid constellation or gain')
    rng=np.random.default_rng(np.random.SeedSequence([case['seed'],0x4f46444d]))
    active=np.r_[np.arange(-half,0),np.arange(1,half+1)]
    pilots=np.arange(0,len(active),32)
    result=[]
    for _ in range(SYMBOLS):
        if s['modulation']=='qpsk':
            data=((2*rng.integers(0,2,len(active))-1)+1j*(2*rng.integers(0,2,len(active))-1))/np.sqrt(2)
        else:
            data=((2*rng.integers(0,4,len(active))-3)+1j*(2*rng.integers(0,4,len(active))-3))/np.sqrt(10)
        # Known pilot sequence, not a coherent comb of identical large tones.
        data[pilots]=2*rng.integers(0,2,len(pilots))-1
        bins=np.zeros(SIZE,dtype=complex);bins[active%SIZE]=data
        x=np.fft.ifft(bins,norm='ortho')
        result.append((bins,x))
    return active,pilots,result


def waveform(case):
    active,pilots,parts=symbols(case)
    value=np.zeros(case['samples'],dtype=complex)
    value[START:END]=np.concatenate([np.r_[x[-CP:],x] for _,x in parts])*case['signal']['gain']
    value*=np.exp(2j*np.pi*case['signal']['carrier_hz']*np.arange(len(value))/FS)
    iq=np.rint(np.c_[value.real,value.imag])
    if not np.isfinite(iq).all() or iq.min()<-32768 or iq.max()>32767:
        raise ValueError('OFDM int16 overflow; no clipping or seed replacement')
    iq=iq.astype('<i2')
    power=np.abs(value[START:END])**2
    details=dict(active_subcarriers=len(active),pilot_subcarriers_per_symbol=len(pilots),
        data_subcarriers_per_symbol=len(active)-len(pilots),
        active_extreme_hz=[float(active[0]*FS/SIZE),float(active[-1]*FS/SIZE)],
        subcarrier_spacing_hz=FS/SIZE,active_span_hz=float((active[-1]-active[0])*FS/SIZE),
        symbol_length_samples=SIZE+CP,complete_symbols=SYMBOLS,cropped_symbols=0,
        signal_interval=[START,END],quiet_prefix=START,quiet_suffix=len(value)-END,
        papr_db=float(10*np.log10(power.max()/power.mean())),
        rms_codes=float(np.sqrt(power.mean())),component_peak_codes=int(np.abs(iq.astype(np.int64)).max()),
        component_headroom_codes=int(min(32767-int(iq.max()),int(iq.min())+32768)),
        windows=[dict(window_id=i,region='internal' if START<=i*N and (i+1)*N<=END else 'edge',
            symbol_boundaries=[START+j*(SIZE+CP) for j in range(SYMBOLS+1) if i*N<=START+j*(SIZE+CP)<(i+1)*N]) for i in range(4)])
    return value,iq,details


def float_spectrum(iq,coeff):
    p=np.abs(np.fft.fftshift(np.fft.fft((iq[:,0]+1j*iq[:,1])*coeff)))**2
    c=np.cumsum(p);total=float(c[-1])
    lo=int(np.searchsorted(c,total*.005));hi=int(np.searchsorted(c,total*.995))
    return dict(low_bin=lo,high_bin=hi,bandwidth_hz=(hi-lo)*FS/N,
        peak_hz=(int(np.argmax(p))-N//2)*FS/N,center_hz=((lo+hi)/2-N//2)*FS/N)
