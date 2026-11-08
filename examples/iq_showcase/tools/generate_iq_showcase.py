"""Generate deterministic GUI demonstration IQ and finite software references.

No board connections, acquisition records, firmware changes or GUI changes.
NumPy FFT is used only to synthesize OFDM. Spectral reference uses AMD C model.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import numpy as np
from portable import binding_name, discover_project, portable_oracle

FS = 160_000_000
N = 16384
COUNT = 32768
DEFAULT_PROJECT = discover_project()
DEFAULT_DEMOS = None
OUT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    def native(obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.generic):
            return obj.item()
        raise TypeError(type(obj).__name__)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=native) + "\n", encoding="utf-8")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def config(label, window="hann", detector="digital-zero", **kw):
    values = dict(label=label, window=window, detector=detector,
                  gap_min=32, threshold_profile="legacy", threshold_policy="fixed",
                  quiet_samples=1024, ton=None, toff=None, kon=None, koff=None,
                  cyclic=False, seconds=10)
    values.update(kw)
    return values


def quantize(z):
    values = np.rint(np.column_stack((z.real, z.imag)))
    if not np.isfinite(values).all() or values.min() < -32768 or values.max() > 32767:
        raise ValueError("IQ would require clipping")
    return values.astype("<i2")


def tone(freq, amplitude, length=COUNT):
    n = np.arange(length)
    return amplitude * np.exp(2j * np.pi * freq * n / FS)


def build_cases(demos=None):
    cases = []
    def add(case_id, filename, title, iq, intent, pages, configs, **extra):
        iq = np.asarray(iq)
        if iq.shape not in ((N, 2), (COUNT, 2)) or iq.dtype.kind not in "iu":
            raise ValueError("Only 16384/32768 integer I16/Q16 pairs are supported")
        if iq.min() < -32768 or iq.max() > 32767:
            raise ValueError("Out-of-range IQ")
        cases.append(dict(id=case_id, file=filename, title=title, iq=iq.astype("<i2"),
                          intent=intent, ppt_pages=pages, configs=configs, **extra))
    def archived(case_id, filename, source, title, intent, pages, configs, **extra):
        # The eight historical seeds are shipped under their canonical names.
        # --source-demos remains available for an explicitly supplied archive.
        original = (Path(demos) / "vectors" / (source + ".bin")
                    if demos is not None else OUT / filename)
        iq = np.frombuffer(original.read_bytes(), dtype="<i2").reshape(-1, 2).copy()
        add(case_id, filename, title, iq, intent, pages, configs,
            provenance="unchanged historical PPT input",
            source_file=filename, source_sha256=digest(original), historical_source_name=source + ".bin", **extra)

    n = np.arange(COUNT)
    mixed = tone(-30_000_000, 8192) + tone(20_000_000, 4096)
    envelope = np.zeros(COUNT)
    envelope[8192:16384] = .5
    envelope[16384:28672] = 1.5
    add("overview", "01_综合_跨窗双音幅度阶梯.bin", "跨窗双音与幅度阶梯综合展示",
        quantize(mixed * envelope),
        "一份文件同时展示可见幅度阶梯、正负双峰、谱峰与中心区别、跨窗完整测长、窗口RMS与突发RMS区别。",
        [6, 18, 19, 25],
        [config("Hann＋数字零：综合主演示"),
         config("矩形＋数字零：保持128us测长，频谱变化", window="rect"),
         config("矩形＋默认门限：对比滑动功率边界", window="rect", detector="threshold")],
        provenance="new deterministic software-validated input",
        input_definition=dict(active_interval=[8192, 28672], active_samples=20480,
                              active_length_us=128, first_scale=.5, second_scale=1.5,
                              tones_hz=[-30_000_000, 20_000_000]),
        notes=["两个FFT窗的活动占比不同，窗口RMS比值不是3；PPT约1:3用02号文件及其低高幅对照。",
               "默认顶部显示窗1，频谱快照可能属于窗0；本文件两窗都有相同两主频，但功率及谱形不完全相同。"])
    archived("amp_steps", "02_PPT_20MHz幅度阶跃1比3.bin", "amp_steps", "PPT二十兆赫幅度阶跃",
             "上图显示4096到12288的1:3阶跃；两窗精确幅度可看frequency.csv，卡片稳定对比请用补充02A/02B。",
             [9, 18], [config("Hann：PPT设置"), config("矩形：时域幅度不变", window="rect")])
    archived("dual", "03_PPT_正负双音_负30与正20MHz.bin", "dual_wide", "PPT正负双音",
             "显示两座相距50MHz的谱峰；较强峰在-30MHz，带宽中心约-5MHz，展示谱峰与中心不同。",
             [18], [config("Hann：PPT设置"), config("矩形：带宽50MHz对比", window="rect")])
    archived("chirp", "04_PPT_线性扫频_负50到正50MHz.bin", "chirp", "PPT线性扫频",
             "最醒目的rect/hann对比：同一恒包络输入，99%带宽约98.77MHz与67.77MHz，时域RMS保持。",
             [9, 19], [config("矩形：讲稿98.769531MHz", window="rect"), config("Hann：对比频谱加权")],
             notes=["FFT频谱显示该窗的功率分布，不显示扫频先后顺序。"])
    archived("cross", "05_PPT_跨窗突发_8192点51.2us.bin", "cross_burst", "PPT跨窗8192点突发",
             "数字零检测完整[12288,20480)，一条51.2us；窗口RMS4096，突发RMS8192，峰8192。",
             [12, 19, 25],
             [config("矩形＋数字零：PPT设置", window="rect"),
              config("Hann＋数字零：长度不变、频谱变"),
              config("矩形＋默认门限：边界响应对比", window="rect", detector="threshold")])
    archived("ofdm_narrow", "06_PPT_窄带OFDM_约40MHz.bin", "ofdm_narrow", "PPT窄带OFDM",
             "与07号比较同级RMS约6000但频带宽度明显不同；与08号比较频移前后。",
             [20, 21], [config("Hann：PPT设置"), config("矩形：窗函数对照", window="rect")])
    archived("ofdm_wide", "07_PPT_宽带OFDM_约140MHz.bin", "ofdm_wide", "PPT宽带OFDM",
             "Hann参考99%带宽138.330078MHz；与06号比较频谱平台展宽、峰值与RMS差异。",
             [20], [config("Hann：PPT设置"), config("矩形：窗函数对照", window="rect")])
    archived("ofdm_shift", "08_PPT_OFDM整体移频正25MHz.bin", "shifted_ofdm", "PPT窄OFDM整体移频",
             "与06号对比：包络近似保持、带宽保持，中心与谱峰均平移约25MHz。",
             [21], [config("Hann：PPT设置"), config("矩形：窗函数对照", window="rect")])

    rng = np.random.default_rng(20261107)
    bins = np.r_[np.arange(-8191, 0), np.arange(1, 8192)]
    bits = rng.integers(0, 2, (len(bins), 2))
    symbol = (2 * bits[:, 0] - 1 + 1j * (2 * bits[:, 1] - 1)) / np.sqrt(2)
    spectrum = np.zeros(N, dtype=np.complex128)
    spectrum[bins % N] = symbol
    full = np.fft.ifft(spectrum)
    full *= 6000 / np.sqrt(np.mean(np.abs(full) ** 2))
    add("fullband", "09_满带OFDM_展示约158MHz带宽.bin", "接近全频带的OFDM",
        quantize(np.tile(full, 2)),
        "配合赛题指标页展示接近160MHz复IQ频谱跨度的输入；RMS约6000。",
        [4, 17], [config("Hann：接近满屏频谱"), config("矩形：满带对照", window="rect")],
        provenance="new deterministic software-validated input",
        input_definition=dict(seed=20261107, modulation="QPSK OFDM", active_subcarriers=len(bins),
                              subcarrier_bounds_hz=[float(bins.min()*FS/N),float(bins.max()*FS/N)],
                              dc_and_nyquist_excluded=True, target_rms=6000))
    archived("noise_10db", "10_PPT_10dB含噪双突发.bin", "noise_10db", "PPT十dB含噪双突发",
             "原PPT固定门限下2条突发，末条8202点51.2625us，比8192点真值多10点。",
             [21, 27],
             [config("PPT原门限：两条突发", detector="threshold", ton=415107548, toff=207553774, kon=8, koff=32),
              config("legacy＋quiet-prefix：重新估计", detector="threshold", threshold_policy="quiet-prefix"),
              config("robust＋quiet-prefix：带噪预设", detector="threshold", threshold_profile="robust", threshold_policy="quiet-prefix"),
              config("数字零反例：非零背景无法分段")],
             notes=["PPT顶部特意显示窗0：RMS6333.691、99%带宽145.595703MHz；普通GUI最后窗1为RMS6348.014、150.742188MHz。",
                    "两者是同一输入的不同窗口。原PPT第二段长度51.2625us仍由末条突发给出。",
                    "希望卡片重现PPT窗0，可选补充10A单窗文件；该文件只包含第一段突发。"])

    designed = load_module("settings_cases", Path(__file__).with_name("settings_cases.py")).build_cases()
    names = {
        "settings_zero_gaps": ("11_设置切换_零间隔与幅度频率阶梯.bin", [12, 15, 18, 19, 25]),
        "settings_background": ("12_设置切换_背景中的强弱双突发.bin", [18, 21, 27]),
        "settings_confirmation": ("13_设置切换_kon拒短与koff合并.bin", [12, 15, 25]),
        "boundary_gap31": ("对照补充/15A_精细边界_内部31点零.bin", [15]),
        "boundary_gap32": ("对照补充/15B_精细边界_内部32点零.bin", [15]),
    }
    for c in designed:
        filename, pages = names[c["id"]]
        configs = list(c["configs"])
        if c["id"] == "settings_zero_gaps":
            configs.append(config("Hann＋数字零gap32：对比时域不变"))
        extra = {k:v for k,v in c.items() if k not in ("id","file","title","iq","intent","configs")}
        add(c["id"], filename, c["title"], c["iq"], c["intent"], pages, configs,
            provenance="new deterministic software-validated input", **extra)
    axes = np.array([1, 1j, -1, -1j])
    add("continuous", "14_连续40MHz单音_窗函数与截断标志.bin", "连续单音与状态标志",
        quantize(8192*axes[n%4]), "矩形窗单bin带宽0与Hann约19.531kHz；单次起点未确认/停止截断；循环可展示停止与长度上限分段。",
        [12, 25], [config("矩形：单bin与截断", window="rect"), config("Hann：主瓣展宽与截断")],
        provenance="new deterministic software-validated input",
        notes=["循环测试只有完整性检查；本包独立数值参考限定单次有限回放。最后一条通常显示停止截断，长度上限分段记录可在burst.csv查看。"])
    add("zero", "15_全零_无功率标志与空突发.bin", "全零输入",
        np.zeros((COUNT,2),dtype="<i2"), "RMS/峰值为0、NO_POWER、没有突发，长度显示横线。",
        [15], [config("矩形：无功率", window="rect"), config("Hann：无功率")],
        provenance="new deterministic software-validated input")

    amp = next(c for c in cases if c["id"]=="amp_steps")["iq"]
    for case_id,filename,title,iq in [
        ("amp_low","对照补充/02A_20MHz低幅4096_单窗口.bin","幅度阶跃低平台单窗",amp[:N]),
        ("amp_high","对照补充/02B_20MHz高幅12288_单窗口.bin","幅度阶跃高平台单窗",amp[N:]),
        ("tone_coherent","对照补充/02C_相干20MHz单音_幅度8192.bin","相干20MHz单音",quantize(tone(20_000_000,8192,N))),
        ("tone_fractional","对照补充/02D_非整数频点单音_窗函数泄漏对比.bin","非整数bin单音",quantize(tone(20_000_000+.37*FS/N,8192,N))),
        ("noise_first","对照补充/10A_含噪PPT窗口0_单窗口.bin","含噪PPT窗0单窗",next(c for c in cases if c["id"]=="noise_10db")["iq"][:N])
    ]:
        recipes = ([config("PPT原门限，单窗0",detector="threshold",ton=415107548,toff=207553774,kon=8,koff=32)]
                   if case_id=="noise_first" else [config("Hann：稳定卡片对照"),config("矩形：窗函数对照",window="rect")])
        add(case_id,filename,title,iq,"辅助稳定卡片对照，避免两窗变化快于GUI刷新。", [18,21] if case_id=="noise_first" else [9,18],
            recipes,provenance="new single-window companion; software reference only")
    return cases


def flags_for_frequency(row):
    flags = []
    if not row["total"]:
        return ["NO_POWER"]
    if row["q_low"]==row["q_high"]:
        flags.append("RESOLUTION_LIMITED")
    if row["q_low"]==0 or row["q_high"]==N-1:
        flags.append("EDGE_RISK")
    return flags


def gui_metrics(row):
    return dict(window_id=row["window_id"], rms_codes=row["rms_uq16_16"]/65536,
                peak_codes=row["peak_uq16_16"]/65536, peak_mhz=row["f_peak_hz"]/1e6,
                bandwidth_mhz=row["bandwidth_hz"]/1e6, center_mhz=row["center_hz"]/1e6,
                flags=flags_for_frequency(row))


def burst_summary(r):
    flags = [name for bit,name in [(12,"DIGITAL_ZERO"),(13,"START_UNCONFIRMED"),(8,"CAPTURE_TRUNCATED"),(10,"DETECTOR_TIMEOUT")] if r["flags"]&(1<<bit)]
    return dict(start=r["start_sample"],end=r["end_sample"],length_samples=r["length_samples"],
                length_us=r["length_samples"]*1e6/FS,rms_codes=r["rms_q16"]/65536,
                peak_codes=r["peak_q16"]/65536,flags=flags,flags_raw=r["flags"])


def make_previews(output, cases, cache):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    import os
    font_path=Path(os.environ.get("WINDIR", "/nonexistent"))/"Fonts/msyh.ttc"
    if font_path.exists():
        font=FontProperties(fname=str(font_path))
        plt.rcParams["font.family"]=font.get_name()
    plt.rcParams["axes.unicode_minus"]=False
    plt.rcParams["font.size"]=10
    dest=output/"预览图";dest.mkdir(exist_ok=True)
    byid={c["id"]:c for c in cases}
    def envelope(ax, case):
        iq=case["iq"].astype(np.int64);amplitude=np.sqrt((iq*iq).sum(axis=1))
        stride=max(1,len(iq)//1000);idx=np.arange(0,len(iq),stride)
        maximum=np.maximum.reduceat(amplitude,idx)
        ax.plot(idx/160,maximum,color="#167a8a",lw=1)
        ax.axvline(102.4,color="#999999",lw=.8,ls="--")
        ax.set(xlim=(0,len(iq)/160),xlabel="时间 / μs",ylabel="包络 / 数字码值",title=case["title"])
        ax.grid(alpha=.15)
    def spectral(ax,case_id,mode):
        row,shot=cache[case_id][mode][-1]
        power=np.asarray(shot,dtype=float);peak=max(float(power.max()),1.)
        db=10*np.log10(np.maximum(power/peak,1e-10))
        ax.plot(np.linspace(-80,80,1024,endpoint=False),db,lw=.9,label=f"{mode}  B99={row['bandwidth_hz']/1e6:.6f} MHz")
        ax.set(xlim=(-80,80),ylim=(-100,3),xlabel="数字基带频率 / MHz",ylabel="相对快照峰值 / dB")
        ax.grid(alpha=.15);ax.legend(loc="lower center",fontsize=8)
    fig,axes=plt.subplots(3,2,figsize=(14,10),constrained_layout=True)
    for axrow,case_id in zip(axes,["overview","amp_steps","cross"]):
        envelope(axrow[0],byid[case_id]);spectral(axrow[1],case_id,"hann")
    fig.suptitle("输入包络与频谱软件参考预览（未重新上板）")
    fig.savefig(dest/"01_综合与跨窗_软件参考.png",dpi=150);plt.close(fig)
    fig,axes=plt.subplots(3,2,figsize=(14,10),constrained_layout=True)
    for ax,(case_id,mode) in zip(axes.flat,[("chirp","rect"),("chirp","hann"),("ofdm_narrow","hann"),("ofdm_wide","hann"),("ofdm_shift","hann"),("fullband","hann")]):
        spectral(ax,case_id,mode);ax.set_title(byid[case_id]["title"])
    fig.suptitle("频谱切换软件参考预览（未重新上板）")
    fig.savefig(dest/"02_扫频与OFDM_软件参考.png",dpi=150);plt.close(fig)
    fig,axes=plt.subplots(3,2,figsize=(16,12),constrained_layout=True)
    short_labels={
        "settings_zero_gaps":["零模式 gap32","零模式 gap2048","默认门限","Hann 零模式"],
        "settings_background":["fixed 默认","legacy 估计","robust 估计","手动门限","错误前导8192","数字零反例"],
        "settings_confirmation":["默认确认","kon=1024","koff=2048","kon1024+koff2048"]}
    for axrow,case_id in zip(axes,short_labels):
        case=byid[case_id];envelope(axrow[0],case);ax=axrow[1]
        scenarios=case["scenarios"]
        for y,scene in enumerate(scenarios):
            for b in scene["bursts"]:
                ax.broken_barh([(b["start"]/160,b["length_us"])],(y-.28,.56),facecolors="#167a8a")
            ax.text(205,y,f"{scene['burst_count']}条",va="center",fontsize=9)
        ax.set(yticks=range(len(scenarios)),yticklabels=short_labels[case_id],
               xlim=(0,220),ylim=(-.7,len(scenarios)-.3),xlabel="检测区间 / μs",
               title="同一文件，不同设置的独立参考结果")
        ax.invert_yaxis();ax.grid(axis="x",alpha=.15)
    fig.suptitle("采集设置切换效果（软件参考，条数为单次回放）")
    fig.savefig(dest/"03_门限与确认参数_软件参考.png",dpi=150);plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project",type=Path,default=DEFAULT_PROJECT)
    parser.add_argument("--source-demos",type=Path,default=DEFAULT_DEMOS)
    parser.add_argument("--out",type=Path,default=OUT)
    parser.add_argument("--cache-dir",type=Path,default=Path(tempfile.gettempdir())/"fft_showcase_amd_reference")
    parser.add_argument("--inputs-only", action="store_true",
                        help="Verify/regenerate all deterministic IQ inputs without AMD or Matplotlib; retain existing references")
    args=parser.parse_args()
    project=args.project.resolve();output=args.out.resolve();output.mkdir(parents=True,exist_ok=True)
    binding_name(output, project)  # References own paths inside their repository.
    source_manifest=json.loads((OUT/"manifest.json").read_text(encoding="utf-8-sig"))
    source_provenance=json.loads((OUT/"publication_provenance.json").read_text(encoding="utf-8-sig"))
    cases=build_cases(args.source_demos)
    byid={case["id"]:case for case in source_manifest["cases"]}
    for case in cases:
        payload=case["iq"].astype("<i2").tobytes()
        if hashlib.sha256(payload).hexdigest()!=byid[case["id"]]["sha256"]:
            raise ValueError(f"Generated IQ differs from the reviewed input: {case['file']}")
    if args.inputs_only:
        for case in cases:
            target=output/case["file"];target.parent.mkdir(parents=True,exist_ok=True)
            payload=case["iq"].astype("<i2").tobytes()
            if target.exists() and target.read_bytes()!=payload:
                raise FileExistsError(f"Refusing to overwrite a different existing input: {target}")
            target.write_bytes(payload)
        print(json.dumps(dict(status="PASS",iq_files=len(cases),input_hashes_match_reviewed_pack=True,
                              amd_fft_recomputed=False,board_access=False)))
        return
    sys.path[:0]=[str(project/"host"),str(project/"tests")]
    from fft_reference import FFTReference
    from threshold_config import resolve
    from threshold_reference import reference_threshold
    from frame_length_reference import reference_digital_zero
    cache={};manifest_cases=[]
    bind_files=[Path(__file__),Path(__file__).with_name("settings_cases.py"),
                project/"tests/fft_reference.py",project/"tests/threshold_reference.py",
                project/"tests/frame_length_reference.py",project/"host/threshold_config.py",
                project/"config/build_profile.json",project/"data/vectors/hann_u18_f17.mem"]
    bind_files.append(Path(__file__).with_name("portable.py"))
    bindings={binding_name(p, project):digest(p) for p in bind_files}
    total_windows=0;total_snapshots=0
    with FFTReference(model_dir=args.cache_dir) as oracle:
        identity=portable_oracle(oracle.identity)
        for number,case in enumerate(cases,1):
            iq=case["iq"];path=output/case["file"];path.parent.mkdir(parents=True,exist_ok=True)
            payload=iq.astype("<i2").tobytes()
            if path.exists() and path.read_bytes()!=payload:
                raise FileExistsError(f"Refusing to overwrite a different existing input: {path}")
            path.write_bytes(payload)
            input_hash=digest(path)
            if case.get("source_sha256") and input_hash!=case["source_sha256"]:
                raise AssertionError("Historical input copy changed")
            power=(iq.astype(np.int64)**2).sum(axis=1)
            window_power=[power[k:k+N] for k in range(0,len(iq),N)]
            cache[case["id"]]={}
            bymode={}
            for mode in ("rect","hann"):
                windows=[];snapshots=[]
                for k in range(len(iq)//N):
                    row,packed,shot=oracle.window(iq[k*N:(k+1)*N],mode,window_id=k)
                    windows.append(row);snapshots.append(shot.tolist())
                    total_windows+=1;total_snapshots+=len(shot)
                bymode[mode]=(windows,snapshots)
                cache[case["id"]][mode]=list(zip(windows,snapshots))
            result={k:v for k,v in case.items() if k not in ("iq","configs")}
            result.update(sha256=input_hash,samples=len(iq),bytes=len(payload),
                          source_status="historical input byte-identical" if case.get("source_sha256") else "new input; no new board capture",
                          input_statistics=dict(component_min=int(iq.min()),component_max=int(iq.max()),
                                                input_nonzero_samples=int(np.count_nonzero(power)),
                                                clipping_applied=False,
                                                window_rms=[float(np.sqrt(p.mean())) for p in window_power],
                                                window_peaks=[float(np.sqrt(p.max())) for p in window_power]),
                          spectral_by_mode={mode:[gui_metrics(r) for r in rows[0]] for mode,rows in bymode.items()},
                          scenarios=[])
            for scene_no,request in enumerate(case["configs"],1):
                actual,estimate=resolve(SimpleNamespace(**request),payload)
                records=(reference_digital_zero(iq[:,0],iq[:,1],gap_min=actual["gap_min"])
                         if actual["mode"]=="digital-zero" else reference_threshold(iq,actual))
                bursts=[burst_summary(r) for r in records]
                ref_rel=f"参考结果/{case['id']}__{scene_no:02d}.json"
                windows,snapshots=bymode[request["window"]]
                ref=dict(schema="iq-qualification-reference-v1",replay="finite",mode=request["window"],
                         input_sha256=input_hash,sample_rate_hz=FS,detector=actual,
                         windows=windows,snapshots=snapshots,oracle=identity,
                         bindings=dict(bindings,**{binding_name(path, project):input_hash}),
                         binding_base="repository",
                         software_reference_only=True)
                # Retain the original reviewed numeric identity across packaging.
                keys=("schema","replay","mode","input_sha256","sample_rate_hz","detector","windows","snapshots","software_reference_only")
                numeric_hash=hashlib.sha256(json.dumps({k:ref[k] for k in keys},sort_keys=True,
                            separators=(",",":"),ensure_ascii=False).encode("utf-8")).hexdigest()
                origin=source_provenance["references"][ref_rel]
                if numeric_hash!=origin["numerical_payload_sha256"]:
                    raise ValueError(f"Regenerated AMD result differs from the reviewed reference: {ref_rel}")
                ref["source_reference_sha256"]=origin["source_sha256"]
                dump(output/ref_rel,ref)
                result["scenarios"].append(dict(label=request["label"],request=request,
                                                applied_detector=actual,threshold_estimate=estimate,
                                                reference_file=ref_rel,burst_count=len(bursts),bursts=bursts,
                                                last_burst=bursts[-1] if bursts else None,
                                                last_window=gui_metrics(windows[-1])))
            case["scenarios"]=result["scenarios"]
            manifest_cases.append(result)
            print(f"[{number}/{len(cases)}] {case['file']} : {len(iq)} pairs, {len(result['scenarios'])} scenarios",flush=True)
    manifest=dict(schema="iq-gui-showcase-pack-v1",sample_rate_hz=FS,fft_length=N,
                  format="little-endian interleaved signed I16/Q16, 4 bytes per pair",
                  project=Path(__import__("os").path.relpath(project, output)).as_posix(),cases=manifest_cases,
                  source_materials=source_manifest["source_materials"],
                  oracle=identity,
                  binding_base="repository", publication=source_manifest["publication"],
                  validation=dict(status="PASS",scope="Input format/range/source hashes, AMD spectral references, independent finite interval references",
                                  iq_files=len(cases),scenarios=sum(len(c["scenarios"]) for c in manifest_cases),
                                  fft_windows_evaluated=total_windows,snapshot_reference_values=total_snapshots,
                                  new_board_test_performed=False))
    dump(output/"manifest.json",manifest)
    dump(output/"publication_provenance.json",source_provenance)
    if output!=OUT:
        for name in ("favorites.json","README.md","先看我_现场演示路线.txt"):
            shutil.copy2(OUT/name,output/name)
        shutil.copytree(OUT/"tools",output/"tools",dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__","*.pyc"))
    dump(output/"离线验证报告.json",manifest["validation"])
    make_previews(output,cases,cache)
    lines=["IQ演示文件与设置对照","",
           "本演示包均为160 MSPS、小端交错I16/Q16；只选择根目录或“对照补充”内的IQ .bin。",
           "所有预期均已离线计算；本次未连接板卡。八份PPT输入逐字节沿用历史文件，新文件不能写成已重新实板验收。",
           "计数/区间对比请取消循环；持续秒数仍填10。digital-zero保持legacy/fixed，四手动项留空。",
           "普通GUI只显示最后一个FFT窗口、最近一条突发；快照另有窗口号。各卡不一定统计同一区间。",
           "不要在循环采集时期待总突发数固定为1/2/3；需要稳定看图时可循环2秒，再按窗口边界停止。",
           ""]
    for case in manifest_cases:
        lines.extend(["="*68,case["file"],case["title"],f"对应PPT/讲稿页：{case['ppt_pages']}",case["intent"],
                      f"输入：{case['samples']}对IQ，{case['bytes']}字节，SHA256 {case['sha256']}"])
        lines.extend(case.get("notes",[]))
        for i,scene in enumerate(case["scenarios"],1):
            q=scene["request"];d=scene["applied_detector"];f=scene["last_window"];b=scene["last_burst"]
            lines.extend(["",f"方案{i}：{scene['label']}",
                          f"单次；分析窗={q['window']}；长度模式={q['detector']}；零间隔={q['gap_min']}；档位={q['threshold_profile']}；策略={q['threshold_policy']}；前导={q['quiet_samples']}",
                          "四个手动框："+"，".join(f"{k}={'留空' if q.get(k) is None else q[k]}" for k in ("ton","toff","kon","koff")),
                          f"实际参数：ton={d['ton']}，toff={d['toff']}，kon={d['kon']}，koff={d['koff']}（数字零模式不使用门限判断）。",
                          f"单次预期：{case['samples']//N}条频域结果，{scene['burst_count']}条突发结果。",
                          f"最后窗口：RMS={f['rms_codes']:.6f}，峰值={f['peak_codes']:.6f}，谱峰={f['peak_mhz']:.6f}MHz，99%带宽={f['bandwidth_mhz']:.6f}MHz，中心={f['center_mhz']:.6f}MHz；频域标志={','.join(f['flags']) or '无'}。"])
            if b:
                lines.append(f"最后突发：[{b['start']},{b['end']})，{b['length_samples']}点={b['length_us']:.6f}us，RMS={b['rms_codes']:.6f}，峰值={b['peak_codes']:.6f}；标志={','.join(b['flags']) or '正常确认'}。")
            else:
                lines.append("没有突发记录，长度卡应显示横线。")
            lines.append("全部突发区间："+("；".join(f"[{r['start']},{r['end']})={r['length_us']:.6f}us" for r in scene["bursts"]) or "无"))
    (output/"文件说明与参数对照.txt").write_text("\n".join(lines)+"\n",encoding="utf-8-sig")
    hashes=[f"{digest(output/c['file'])}  {c['file']}" for c in manifest_cases]
    (output/"IQ_SHA256SUMS.txt").write_text("\n".join(hashes)+"\n",encoding="utf-8")
    print(json.dumps(manifest["validation"],ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
