"""16K acceptance matrix: retain physical frequencies and waveform durations."""
import json
from pathlib import Path
from fft_reference import FS, N
from make_phase2_specs import case, tone, qpsk


def build():
    cases=[case('zero',{'kind':'zero'},intervals=[]),
           case('negative_fullscale',{'kind':'constant','iq':[-32768,-32768]})]
    for label,hz in [('dc',0),('p_fs4',FS/4),('m_fs4',-FS/4),
                     ('p_49mhz',49e6),('m_49mhz',-49e6),
                     ('fractional',997.25*FS/8192)]:
        cases.append(case(label,tone(hz*N/FS)))
    for a in (1,2,16,256,4096,30000):
        cases.append(case(f'amplitude_{a}',tone(N/4,a),category='amplitude'))
    for gap in (1,2,8):
        cases.append(case(f'two_tones_{gap}_bins',{'kind':'two-tone','tones':[
            {'bin':N/8,'amplitude':4096},{'bin':N/8+gap,'amplitude':4096}]},category='two-tone'))
    for sps in (2,4):
        cases.append(case(f'qpsk_sps{sps}',qpsk(sps=sps),seed=91001,
                          intervals=[[2048,26624]],category='modulation'))
    for alpha in (.25,.6,1.):
        cases.append(case(f'rrc_alpha{int(alpha*100)}',qpsk(24000,shaped=True,alpha=alpha),
                          seed=91001,intervals=[[4096,28672]],category='wideband'))
    for boundary in (8192,N):
        for detector in ('threshold','digital-zero'):
            cases.append(case(f'boundary_{boundary}_{detector.replace("-","_")}',tone(N/4),
                              intervals=[[boundary-256,boundary+256]],detector=detector,category='boundary'))
    for gap in (31,32,33):
        cases.append(case(f'digital_gap_{gap}',tone(N/4),detector='digital-zero',
                          intervals=[[4096,4608],[4608+gap,5120+gap]],category='gap'))
    for snr in (0,10,20):
        for seed in (91001,91002,91003):
            cases.append(case(f'noise_{snr}_{seed}',qpsk(),seed=seed,snr=snr,policy='quiet-prefix',
                              intervals=[[4096,12288],[16384,24576]],windows=['hann'],category='noise'))
    for modulation in ('qpsk','qam16'):
        for seed in (212100,212101,212102):
            cases.append(case(f'ofdm_{modulation}_{seed}',dict(kind='ofdm',ifft_length=8192,cyclic_prefix=512,
                active_half=4095,modulation=modulation,gain=6000),seed=seed,intervals=[[1024,27136]],category='wideband'))
    return {'schema':'iq-qualification-spec-v1','cases':cases}


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(build(),indent=2)+'\n',encoding='utf-8')
    print('PHASE9_SPEC',len(build()['cases']))
