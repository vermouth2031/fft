"""Wideband OFDM stimulus with an FFT-independent 8192-sample symbol size."""
import numpy as np


def symbols(signal,seed,count):
    size=signal['ifft_length'];cp=signal['cyclic_prefix'];half=signal['active_half']
    if size!=8192 or cp!=512 or not 1<=half<size//2 or signal['modulation'] not in ('qpsk','qam16'):
        raise ValueError('Unsupported Phase 9 OFDM waveform')
    if not 0<signal['gain']<=32767:raise ValueError('Invalid OFDM gain')
    rng=np.random.default_rng(np.random.SeedSequence([seed,0x4f46444d]))
    active=np.r_[np.arange(-half,0),np.arange(1,half+1)]
    result=[]
    for _ in range(count):
        levels=2 if signal['modulation']=='qpsk' else 4
        norm=np.sqrt(2 if levels==2 else 10)
        data=((2*rng.integers(levels,size=len(active))-(levels-1))+
              1j*(2*rng.integers(levels,size=len(active))-(levels-1)))/norm
        data[::32]=2*rng.integers(2,size=len(data[::32]))-1
        bins=np.zeros(size,dtype=complex);bins[active%size]=data
        time=np.fft.ifft(bins,norm='ortho')
        result.append((bins,np.r_[time[-cp:],time]*signal['gain']))
    return active,result


def waveform(signal,seed,length):
    period=signal['ifft_length']+signal['cyclic_prefix']
    if length%period:raise ValueError('OFDM intervals must contain complete CP-bearing symbols')
    _,parts=symbols(signal,seed,length//period)
    return np.concatenate([x for _,x in parts])
