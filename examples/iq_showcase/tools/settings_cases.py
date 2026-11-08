"""Deterministic, board-free IQ design cases for GUI acquisition settings."""
from pathlib import Path
import importlib.util
import json
from types import SimpleNamespace
import numpy as np

FS = 160_000_000
N = 32768
SEED = 20261107
from portable import discover_project
PROJECT = discover_project()


def tone(amplitude, frequency_hz):
    n = np.arange(N, dtype=np.int64)
    # Exact Fs/4 axes avoid unnecessary floating quantization in settings tests.
    if frequency_hz in (40_000_000, -40_000_000):
        axes = np.array([1, 1j, -1, -1j])
        return amplitude * axes[(n * (1 if frequency_hz > 0 else -1)) % 4]
    return amplitude * np.exp(2j * np.pi * frequency_hz * n / FS)


def quantize(z):
    iq = np.column_stack((np.rint(z.real), np.rint(z.imag)))
    if np.max(iq) > 32767 or np.min(iq) < -32768:
        raise ValueError('Signal requires clipping')
    return iq.astype('<i2')


def config(label, detector='threshold', profile='legacy', policy='fixed', gap=32,
           quiet=1024, ton=None, toff=None, kon=None, koff=None, note=''):
    return dict(label=label, detector=detector, threshold_profile=profile,
                threshold_policy=policy, gap_min=gap, quiet_samples=quiet,
                ton=ton, toff=toff, kon=kon, koff=koff, window='rect',
                cyclic=False, seconds=10, note=note)


def build_cases():
    result = []
    z = np.zeros(N, dtype=np.complex128)
    intervals = [(3072, 8192, 4096, -20_000_000),
                 (9216, 14336, 8192, 20_000_000),
                 (15360, 28672, 12288, 40_000_000)]
    for start, end, amp, freq in intervals:
        z[start:end] = tone(amp, freq)[start:end]
    result.append(dict(
        id='settings_zero_gaps', file='10_zero_gaps_amplitude_steps.bin',
        title='零背景三段阶梯与1024点间隙', iq=quantize(z),
        intent='同一文件展示数字零模式、gap分段与合并、幅度阶梯、跨FFT窗活动、矩形/Hann切换。',
        input_intervals=[dict(start=a, end=b, amplitude=c, frequency_hz=d) for a,b,c,d in intervals],
        configs=[
            config('数字零gap32：分为3段，末段83.2us', detector='digital-zero'),
            config('数字零gap2048：合为1段，总长160us', detector='digital-zero', gap=2048),
            config('门限默认：与数字零边界对比，计入滑动响应',
                   note='门限结果通常比非零支撑区间多15点；不是koff直接加32点。'),
        ]))

    # Background is random sign in the quadrature direction of an exact 40 MHz
    # carrier. Every background sample has power 1024^2, and every sample is
    # nonzero. It is a controlled nonzero background, not circular Gaussian AWGN.
    rng = np.random.default_rng(SEED)
    signs = rng.choice(np.array([-1, 1]), size=N)
    axes = tone(1, 40_000_000)
    amplitude = np.zeros(N, dtype=np.int64)
    amplitude[4096:12288] = 6000
    amplitude[18432:28672] = 1600
    z = axes * (amplitude + 1j * 1024 * signs)
    result.append(dict(
        id='settings_background', file='11_background_strong_weak.bin',
        title='恒功率随机背景中的强弱两段', iq=quantize(z),
        intent='同一文件切换fixed、legacy+quiet-prefix、robust+quiet-prefix、手动门限、错误前导长度与digital-zero，观察计数/末条长度/标志变化。',
        input_intervals=[dict(start=4096,end=12288,coherent_amplitude=6000),
                         dict(start=18432,end=28672,coherent_amplitude=1600)],
        background=dict(kind='random-sign orthogonal constant-power background; not circular Gaussian AWGN',
                        amplitude=1024, sample_power=1048576, seed=SEED,
                        valid_quiet_prefix=[0,4096], frequency_hz=40_000_000),
        configs=[
            config('legacy+fixed默认：背景被误作连续活动'),
            config('legacy+quiet：只检出强段', policy='quiet-prefix'),
            config('robust+quiet：强弱两段都检出', profile='robust',policy='quiet-prefix'),
            config('手动fixed恢复两段：ton50331648/toff29360128/kon16/koff8',
                   ton=50331648,toff=29360128,kon=16,koff=8),
            config('错误前导8192：把强信号当背景，可能全部漏检',policy='quiet-prefix',quiet=8192,
                   note='这是有意演示错误配置；前8192点包含强信号，不是有效背景声明。'),
            config('digital-zero：背景不为零，无法分出两段',detector='digital-zero'),
        ]))

    z = np.zeros(N, dtype=np.complex128)
    intervals = [(3072,3584,14000),(8192,14336,6144),(15360,27648,10000)]
    for start,end,amp in intervals:
        z[start:end] = tone(amp,40_000_000)[start:end]
    result.append(dict(
        id='settings_confirmation', file='12_confirmation_short_and_gap.bin',
        title='512点短脉冲与1024点长段间隙', iq=quantize(z),
        intent='把确认参数放大到可见尺度：kon1024拒绝短脉冲，koff2048合并两个长段；通过记录计数与最后长度观察。',
        input_intervals=[dict(start=a,end=b,amplitude=c,frequency_hz=40_000_000) for a,b,c in intervals],
        configs=[
            config('默认kon8/koff32：3条突发'),
            config('kon1024：短脉冲被拒，剩2条',kon=1024),
            config('koff2048：长段合并，末条约121.69us',koff=2048),
            config('kon1024+koff2048：拒短且合长，剩1条',kon=1024,koff=2048),
        ]))

    for gap in (31,32):
        z=np.zeros(N,dtype=np.complex128)
        a,b,c,d=12288,16384,16384+gap,24576+gap
        carrier=tone(8192,40_000_000)
        z[a:b]=carrier[a:b];z[c:d]=carrier[c:d]
        result.append(dict(
            id=f'boundary_gap{gap}',file=f'13_boundary_gap{gap}.bin',
            title=f'数字零{gap}点间隙边界补充',iq=quantize(z),
            intent=f'固定gap_min32，比较{gap}点内部零间隔。约0.2us间隙只用于数字结果精细边界展示，不承诺包络图肉眼分辨。',
            input_intervals=[dict(start=a,end=b,amplitude=8192),dict(start=c,end=d,amplitude=8192)],
            configs=[config(f'数字零gap32：内部{gap}零',detector='digital-zero')]))
    return result


def _load(name, relative):
    spec=importlib.util.spec_from_file_location(name,PROJECT/relative)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m


def verify():
    thresholds=_load('design_threshold_config','host/threshold_config.py')
    th=_load('design_threshold_ref','tests/threshold_reference.py')
    dz=_load('design_zero_ref','tests/frame_length_reference.py')
    rows=[]
    for case in build_cases():
        iq=case['iq'];row={k:v for k,v in case.items() if k not in ('iq','configs')}
        row['sample_count']=len(iq);row['byte_count']=iq.nbytes
        row['input_peak']=float(np.sqrt((iq.astype(np.int64)**2).sum(axis=1)).max())
        row['nonzero_samples']=int(np.count_nonzero(np.any(iq!=0,axis=1)))
        row['scenarios']=[]
        for cfg in case['configs']:
            detector,meta=thresholds.resolve(SimpleNamespace(**cfg),iq.tobytes())
            records=(dz.reference_digital_zero(iq[:,0],iq[:,1],gap_min=cfg['gap_min'])
                     if cfg['detector']=='digital-zero' else th.reference_threshold(iq,detector))
            summary=[]
            for r in records:
                summary.append(dict(start=r['start_sample'],end=r['end_sample'],length=r['length_samples'],
                                    length_us=r['length_samples']/160,flags=r['flags'],
                                    rms=r['rms_q16']/65536,peak=r['peak_q16']/65536))
            row['scenarios'].append(dict(config=cfg,resolved=detector,
                                         estimated_background_power=meta.get('estimated_background_power'),
                                         burst_count=len(records),bursts=summary))
        rows.append(row)
    output=Path(__file__).with_name('settings_validation.json')
    output.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for row in rows:
        print(row['file'],row['sample_count'],row['byte_count'])
        for sc in row['scenarios']:
            print(' ',sc['config']['label'],'count=',sc['burst_count'],
                  [(r['start'],r['end'],r['length_us'],r['flags']) for r in sc['bursts']])
    print(output)

if __name__=='__main__':
    verify()
