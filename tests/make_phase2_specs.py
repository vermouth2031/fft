"""Deterministic S1/S2/S3 coverage, separated by decision stage and seed set."""
import argparse
import copy
import json
from pathlib import Path
from generate_qualification_vectors import DEFAULT_DETECTOR


def case(label, signal, *, intervals=None, seed=None, category='integer-tone', windows=None,
         snr=None, offset=(0,0), policy='fixed', detector='threshold', seconds=None, group=None):
    result=dict(id=label,category=category,sample_rate_hz=100000000,fft_length=8192,samples=32768,
        replay='cyclic' if seconds else 'finite',windows=windows or ['rect','hann'],
        detector=dict(DEFAULT_DETECTOR,mode=detector),seed=seed,noise={'kind':'none'} if snr is None else {'kind':'awgn','snr_db':snr},
        offset_iq=list(offset),design_intervals=intervals if intervals is not None else [[0,32768]],signal=signal,
        threshold_policy={'kind':'fixed'} if policy=='fixed' else dict(kind='quiet-prefix',samples=1024,on_multiple=4,off_multiple=2),
        statistics_group=group or category)
    if seconds:result.update(seconds=seconds,seam='quiet')
    if signal['kind']=='rrc-qpsk':result['truth_basis']='shaped'
    return result


def tone(k=2048, amplitude=8192):
    return dict(kind='tone',tones=[dict(bin=k,amplitude=amplitude)])


def qpsk(amplitude=8192, *, shaped=False,sps=2,alpha=.25):
    value=dict(kind='rrc-qpsk' if shaped else 'qpsk',sps=sps,amplitude=amplitude,normalization='peak' if shaped else 'rms')
    if shaped:value.update(rolloff=alpha,span_symbols=10,carrier_hz=0)
    return value


def build():
    stages={}
    s1=[]
    for k in (-3686,-2048,-410,0,410,2048,3686):
        s1.append(case('integer_'+str(k).replace('-','m'),tone(k)))
    for base in (410,2048,3686):
        for sign in (-1,1):
            for delta in (.1,.25,.49):
                k=sign*(base+delta)
                s1.append(case('fraction_'+str(k).replace('-','m').replace('.','_'),tone(k),category='fractional-tone'))
    for f in (-49e6,-47e6,47e6,49e6):
        s1.append(case('edge_'+str(int(f/1e6)).replace('-','m'),tone(f*8192/1e8),category='edge-tone'))
    for gap in (1,2,8,64):
        for ratio in (1,.5):
            signal=dict(kind='two-tone',tones=[dict(bin=410,amplitude=4096),dict(bin=410+gap,amplitude=int(4096*ratio))])
            s1.append(case(f'pair_{gap}_{int(ratio*100)}',signal,category='two-tone'))
    for a in (1,2,16,64,256,512,1024,4096,8192,16384,30000):
        category='low-amplitude' if a<256 else 'amplitude'
        s1.append(case(f'tone_amp_{a}',tone(amplitude=a),category=category))
        s1.append(case(f'burst_amp_{a}',tone(amplitude=a),intervals=[[4096,28672]],category='burst-amplitude'))
        s1.append(case(f'qpsk_amp_{a}',qpsk(a,shaped=True,sps=4),intervals=[[4096,28672]],seed=73100,
                       category='qpsk-amplitude'))
    for name,iq in [('i_only',[32767,0]),('q_only',[0,32767]),('negative_fullscale',[-32768,-32768])]:
        s1.append(case(name,dict(kind='constant',iq=iq),category='range-boundary'))
    s1.append(case('zero',{'kind':'zero'},intervals=[],category='zero'))
    stages['s1_complete']=s1
    frames=[[2048+i*8192,6144+i*8192] for i in range(4)]
    s2=[]
    for snr in (30,20,10):
        for seed in (81001,81002,81003):
            for policy in ('fixed','quiet-prefix'):
                s2.append(case(f'train_{snr}_{seed}_{policy.replace("-","_")}',qpsk(),intervals=frames,seed=seed,
                    category='noise-training',windows=['hann'],snr=snr,policy=policy,group=f'train_snr{snr}_{policy}'))
    stages['s2_training']=s2
    s2=[]
    # 25 independent input/noise realizations x four known bursts = 100 bursts
    # per condition. Replaying a file is never counted as an independent seed.
    for snr in (30,20,10,5,0):
        for seed in range(82000,82025):
            s2.append(case(f'validation_{snr}_{seed}',qpsk(),intervals=frames,seed=seed,category='noise-validation',
                windows=['hann'],snr=snr,policy='quiet-prefix',group=f'validation_snr{snr}'))
    stages['s2_validation']=s2
    s2=[]
    for length in (64,512,4096,24576):
        start=8176 if length<24576 else 2048
        for seed in (83001,83002,83003):
            for snr in (30,10):
                s2.append(case(f'length_{length}_{snr}_{seed}',qpsk(),intervals=[[start,start+length]],seed=seed,
                    category='noise-length',windows=['hann'],snr=snr,policy='quiet-prefix',group=f'length{length}_snr{snr}'))
        s2.append(case(f'zero_length_{length}',tone(),intervals=[[start,start+length]],category='zero-boundary',
            detector='digital-zero',windows=['hann'],group=f'zero_length{length}'))
    for gap in (7,8,15,31,32,33,64,256):
        intervals=[[4096,4608],[4608+gap,5120+gap]]
        for mode in ('threshold','digital-zero'):
            s2.append(case(f'gap_{gap}_{mode.replace("-","_")}',tone(),intervals=intervals,category='gap-boundary',
                          detector=mode,windows=['hann'],group=f'gap{gap}_{mode}'))
    for offset in ((0,0),(32,0),(128,128),(512,-512)):
        for a in (256,1024,8192):
            for seed in (84001,84002,84003):
                label=f'offset_{offset[0]}_{offset[1]}_{a}_{seed}'.replace('-','m')
                s2.append(case(label,qpsk(a),intervals=frames,seed=seed,category='offset',windows=['hann'],
                    snr=20,offset=offset,policy='quiet-prefix',group=f'offset{offset}_amp{a}'))
    for snr in (30,10):
        s2.append(case(f'digital_zero_noise_{snr}',qpsk(),intervals=frames,seed=85001,snr=snr,
            category='digital-zero-inapplicable',detector='digital-zero',windows=['hann']))
    for a in (256,1024):
        for snr in (30,10,0):
            for seed in (86001,86002,86003):
                s2.append(case(f'low_amplitude_{a}_{snr}_{seed}',qpsk(a),intervals=frames,seed=seed,snr=snr,
                    category='noise-low-amplitude',windows=['hann'],policy='quiet-prefix',group=f'amp{a}_snr{snr}'))
    for mode in ('threshold','digital-zero'):
        s2.append(case(f'shaped_boundaries_{mode.replace("-","_")}',qpsk(shaped=True),intervals=[[8176,12272]],seed=87001,
                      category='shaped-boundaries',detector=mode,windows=['hann']))
    stages['s2_boundaries']=s2
    finite=[];continuous=[]
    for alpha in (.2,.25,.4,.6):
        target=int((1+alpha)*50)
        for seed in (91001,91002,91003):
            finite.append(case(f'wide_a{int(alpha*100)}_{seed}',qpsk(24000,shaped=True,alpha=alpha),
                intervals=[[4096,28672]],seed=seed,category='wideband',group=f'alpha{alpha}_support{target}mhz'))
        for mode in ('rect','hann'):
            continuous.append(case(f'wide_a{int(alpha*100)}_{mode}_10s',qpsk(24000,shaped=True,alpha=alpha),
                intervals=[[4096,28672]],seed=91001,category='wideband-continuous',windows=[mode],seconds=10,
                group=f'alpha{alpha}_support{target}mhz'))
    # Carrier offsets obey the declared ideal-support guard band for normal tests.
    for alpha,offset in ((.2,10e6),(.4,-10e6),(.6,5e6),(.6,25e6)):
        signal=qpsk(24000,shaped=True,alpha=alpha);signal['carrier_hz']=offset
        finite.append(case(f'wide_shift_a{int(alpha*100)}_{int(offset/1e6)}'.replace('-','m'),signal,
            intervals=[[4096,28672]],seed=91004,category='nyquist-wrap' if offset==25e6 else 'wideband-shift',
            group='excluded_wrap' if offset==25e6 else f'shift_alpha{alpha}'))
    stages['s3_finite']=finite
    stages['s3_continuous']=continuous
    refine=[];refine_continuous=[]
    for alpha in (.7,.8,.9,1.0):
        for seed in (91001,91002,91003):
            refine.append(case(f'wide_a{int(alpha*100)}_{seed}',qpsk(24000,shaped=True,alpha=alpha),
                intervals=[[4096,28672]],seed=seed,category='wideband',group=f'alpha{alpha}'))
        for mode in ('rect','hann'):
            refine_continuous.append(case(f'wide_a{int(alpha*100)}_{mode}_10s',qpsk(24000,shaped=True,alpha=alpha),
                intervals=[[4096,28672]],seed=91001,category='wideband-continuous',windows=[mode],seconds=10,group=f'alpha{alpha}'))
    stages['s3_refinement']=refine
    stages['s3_refinement_continuous']=refine_continuous
    # This is a candidate only; execute after finite/10s evidence selects it.
    stages['s3_widest_60s']=[case('wide_a100_hann_60s',qpsk(24000,shaped=True,alpha=1.0),
        intervals=[[4096,28672]],seed=91001,category='wideband-continuous',windows=['hann'],seconds=60,
        group='alpha1.0_support100mhz_candidate_actual80mhz')]
    return stages


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    for name,cases in build().items():
        (args.out/(name+'.json')).write_text(json.dumps(dict(schema='iq-qualification-spec-v1',stage=name,cases=cases),indent=2)+'\n',encoding='utf-8')
        print(name,len(cases),'vectors',sum(len(c['windows']) for c in cases),'captures')


if __name__=='__main__':main()
