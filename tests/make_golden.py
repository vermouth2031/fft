"""AMD installed C model oracle. Never substitutes numpy FFT for bit-accurate checks."""
from pathlib import Path
import ctypes as C
import os, sys, json, math, hashlib, zipfile, shutil
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
VIVADO=Path(os.environ.get('VIVADO_ROOT',r'D:\VivadoMM\2026.1\Vivado'))
DATA=ROOT/'data'; DATA.mkdir(exist_ok=True)
CM=ROOT/'build'/'cmodel'; CM.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(VIVADO/'data/ip/xilinx/xfft_v9_1/cmodel/xfft_v9_1_bitacc_cmodel_nt64.zip') as z:z.extractall(CM)
dll_dir=os.add_dll_directory(str(CM))
lib=C.CDLL(str(CM/'libIp_xfft_v9_1_bitacc_cmodel.dll'))
class Generics(C.Structure):
    _fields_=[(k,C.c_int) for k in ['nfft','arch','has_nfft','float','width','twiddle','scaled','bfp','round','ssr','inverse']]
DP=C.POINTER(C.c_double); IP=C.POINTER(C.c_int)
class Inputs(C.Structure):
    _fields_=[('nfft',C.c_int),('re',DP),('re_size',C.c_int),('im',DP),('im_size',C.c_int),('scale',IP),('scale_size',C.c_int),('direction',C.c_int)]
class Outputs(C.Structure):
    _fields_=[('re',DP),('re_size',C.c_int),('im',DP),('im_size',C.c_int),('exponent',C.c_int),('overflow',C.c_int)]
create=lib.xilinx_ip_xfft_v9_1_create_state; create.argtypes=[Generics];create.restype=C.c_void_p
destroy=lib.xilinx_ip_xfft_v9_1_destroy_state;destroy.argtypes=[C.c_void_p]
simulate=lib.xilinx_ip_xfft_v9_1_bitacc_simulate;simulate.argtypes=[C.c_void_p,Inputs,C.POINTER(Outputs)];simulate.restype=C.c_int
N=8192;FS=100_000_000
state=create(Generics(13,3,0,0,24,18,1,0,1,1,0)); assert state
scale=(C.c_int*7)(3,2,2,2,2,2,1)
VECTORS=ROOT/'data/vectors'
manifest=json.loads((VECTORS/'reference_manifest.json').read_text(encoding='utf-8'))
hann=np.array([int(s,16) for s in (VECTORS/'hann_u18_f17.mem').read_text().splitlines()],dtype=np.int64)
shutil.copyfile(VECTORS/'hann_u18_f17.mem',DATA/'hann_u18_f17.mem')
cases=[]; out_fft=[]; input_words=[]
def hz(q):
    x=(q-4096)*FS
    return (1 if x>=0 else -1)*((abs(x)+4096)//8192)
for mode in ('rect','hann'):
 for name,case in manifest['cases'].items():
    iq=np.fromfile(VECTORS/case['binary'],dtype='<i2').reshape(-1,2).astype(np.int64)
    input_words.extend((iq[:,0]&65535)|((iq[:,1]&65535)<<16))
    result={'name':name,'mode':mode,'windows':[],'bursts':case['bursts']}
    for wid in range(4):
        raw=iq[wid*N:(wid+1)*N]
        coeff=hann if mode=='hann' else np.full(N,131072,dtype=np.int64)
        x=np.rint(raw*coeff[:,None]/512).astype(np.int64)
        re=np.ascontiguousarray(x[:,0]/2**23,dtype=np.float64);im=np.ascontiguousarray(x[:,1]/2**23,dtype=np.float64)
        yr=np.zeros(N,dtype=np.float64);yi=np.zeros(N,dtype=np.float64)
        inp=Inputs(13,re.ctypes.data_as(DP),N,im.ctypes.data_as(DP),N,scale,7,1)
        out=Outputs(yr.ctypes.data_as(DP),N,yi.ctypes.data_as(DP),N,0,0)
        assert simulate(state,inp,C.byref(out))==0
        assert out.overflow==0
        ir=np.rint(yr*2**23).astype(np.int64);ii=np.rint(yi*2**23).astype(np.int64)
        out_fft.extend((ir&0xffffff)|((ii&0xffffff)<<24))
        p=np.fft.fftshift(ir*ir+ii*ii);total=int(p.sum());peak=int(np.argmax(p))
        if total:
            c=np.cumsum(p);lo=int(np.searchsorted(c,(total+199)//200));hi=int(np.searchsorted(c,total-total//200))
        else:lo=hi=0
        tpower=raw[:,0]**2+raw[:,1]**2;energy=int(tpower.sum());pp=int(tpower.max())
        result['windows'].append(dict(window_id=wid,total=total,peak_power=int(p.max()),q_peak=peak,q_low=lo,q_high=hi,
            f_peak_hz=hz(peak) if total else 0,f_low_hz=hz(lo) if total else 0,f_high_hz=hz(hi) if total else 0,
            bandwidth_hz=((hi-lo)*FS+4096)//8192 if total else 0,
            center_hz=(1 if lo+hi>=8192 else -1)*((abs(lo+hi-8192)*FS+8192)//16384) if total else 0,
            energy=energy,peak_uq16_16=math.isqrt(pp<<32),rms_uq16_16=math.isqrt(energy<<19)))
    cases.append(result)
destroy(state)
(DATA/'golden_fft.mem').write_text(''.join(f'{int(w):012x}\n' for w in out_fft),encoding='ascii')
(DATA/'test_iq.mem').write_text(''.join(f'{int(w):08x}\n' for w in input_words),encoding='ascii')
(DATA/'golden_results.json').write_text(json.dumps({'oracle':'AMD xfft v9.1 bit-accurate model from Vivado 2026.1','cases':cases},indent=2),encoding='utf-8')
assert cases[1]['windows'][0]['f_peak_hz']==25_000_000
assert cases[2]['windows'][0]['f_peak_hz']==-25_000_000
print(f'Generated {len(cases)} cases, {len(out_fft)} exact complex FFT outputs.')
