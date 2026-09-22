"""Summarize completed experiments without promoting unfinished hardware candidates."""
from pathlib import Path
import collections
import hashlib
import json
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads((ROOT/p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
def main():
    paths=[f'captures/phase4_ofdm_20260922/{k}/measurement_validation.json' for k in ('finite','boundary','continuous')]
    paths += ['captures/phase4_noise_20260922/measurement_validation.json','build/phase4_noise_20260922/study.json',
        'build/phase4_frequency_20260922_v2/study.json','reports/phase4_baseline.json','reports/phase4_requirements.json']
    finite,boundary,continuous,noise_board,noise,frequency,baseline,rules=map(read,paths)
    assert all(r['status']=='PASS' for r in (finite,boundary,continuous,noise_board))
    assert [len(r['cases']) for r in (finite,boundary,continuous,noise_board)]==[240,24,7,9]
    groups=collections.defaultdict(list)
    for c in finite['cases']:
        key='_'.join(c['label'].split('_')[1:3])+'_'+c['label'].split('_')[-1]
        groups[key].extend(w['bandwidth_min_hz'] for w in c['bandwidth']['windows'] if w['region']=='internal')
    bw={k:dict(internal_windows=len(v),min_hz=min(v),median_hz=float(np.median(v)),p95_hz=float(np.percentile(v,95)),max_hz=max(v)) for k,v in groups.items()}
    captures=[c for r in (finite,boundary,continuous,noise_board) for c in r['cases']+r['legacy_cases']]
    report=dict(schema='iq-phase4-existing-hardware-experiments-v1',status='PASS',
        scope='Completed Q2 board experiments and Q6 offline baseline; Q3/Q4/Q5 hardware candidates are NOT promoted by this report',
        baseline_commit=baseline['commit'],hardware=baseline['hardware']['hardware'],
        evidence={p:sha(p) for p in paths},bandwidth=bw,
        finite_cases=240,boundary_cases=24,continuous_cases=7,continuous_replay_seconds=460,noise_board_cases=9,
        legacy_check_cases=64,maximum_analysis_us=max(r['maximum_analysis_us'] for r in captures),
        maximum_publish_us=max(r['maximum_publish_us'] for r in captures),
        unique_noise_seconds=noise['unique_seconds'],post_calibration_noise_seconds=noise['post_calibration_seconds'],
        noise_strata=noise['summary'],frequency_study_cases=frequency['primary_cases'],
        frequency_half_bin_cases=frequency['half_bin_cases'],tone_offline_candidate=frequency['tone_candidate'],
        official_additional_definitions_confirmed=rules['official_confirmation_received'])
    p=ROOT/'reports/phase4_existing_hardware_validation.json';p.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# 第四阶段已完成实验报告','',
        '本报告仅汇总已完成的现有硬件宽带板测和离线测量研究。八路扫描、构建身份/计数及提频候选另行验收，不能将候选数字写成当前板卡成绩。','',
        '## 1. 当前板卡与赛事口径','',
        f"硬件仍为第三阶段提交 `{baseline['commit']}` 对应的 100 MSPS / 125 MHz FFT / 8192 点版本。输入 I/Q 各 16bit，采用预装载后 PL 连续回放。",
        '用户确认没有新的赛方说明；帧长按包络样本区间，频点按谱峰，带宽按完整 8192 点功率谱的 99% 占用带宽，延迟按 PL 首 IQ 至结果解释。赛方确认状态仍为未确认。','',
        '## 2. OFDM 宽带真板结果','',
        'OFDM IFFT=4096，CP=256，6 个完整符号，静默前缀 1024、后缀 5632 点。DC 空置，活跃子载波中每 32 个位置设置一个单位功率 BPSK 导频，其余为 QPSK/16QAM 数据。600 组训练输入冻结统一增益 6000。独立 seed 为 211000–211019，跨条件同 seed 按成组样本处理。','',
        '| 设计档 / 调制 / 分析窗 | 内部窗数 | 最小 MHz | 中位 MHz | P95 MHz | 最大 MHz |',
        '|---|---:|---:|---:|---:|---:|']
    for k,v in bw.items():lines.append(f"| {k} | {v['internal_windows']} | {v['min_hz']/1e6:.6f} | {v['median_hz']/1e6:.6f} | {v['p95_hz']/1e6:.6f} | {v['max_hz']/1e6:.6f} |")
    lines += ['', '95 MHz 设计跨度档的全部有效内部窗均超过 90 MHz，整体最小值 93.786621 MHz。设计跨度不是实测带宽，本轮没有宣称已经达到 95 MHz 的实际占用带宽。',
        '240 组有限输入共 960 个 FFT 窗，其中内部 480 个、边沿 480 个，全部数值逐位核验。边沿保留单列，不进入内部窗门槛分母。追加 24 组频移边界用例，跨 Nyquist 的输入只作数值/限制测试，不计入新带宽成绩。',
        '两个通信演示档各完成矩形/Hann 10 秒和 Hann 60 秒，QPSK Hann 另完成 300 秒，共 460 秒循环回放。均通过原始结果、序号、时戳、配置和数值核验。重复回放不增加独立输入时长。',
        f"正常最大分析/发布延迟 {report['maximum_analysis_us']:.2f}/{report['maximum_publish_us']:.2f} µs。这是扩展已验证输入带宽范围，硬件时钟和处理架构没有变化。",'',
        '## 3. 噪声和频点的适用范围','',
        f"3153 个不重复噪声块，共 {noise['unique_seconds']:.8f} 秒；除去每块 1024 点估计前缀后共 {noise['post_calibration_seconds']:.8f} 秒。I/Q 分量标准差 256、1024、4096，各 1051 块，每层观察到 0 个虚警。预先固定每层前三个 seed，共 9 块板测，全部位精确通过。",
        '这些是有限独立块，块间检测器复位，不覆盖连续拼接边界或背景漂移。三个噪声层分别统计，每层扣除前缀后的观察时间 0.33362944 秒。若 Poisson 事件模型适用，零事件的单层 95% 上界约 8.98 次/秒；不能宣传虚警率为零。',
        '900 例频点研究覆盖单音、RRC-QPSK、OFDM，5 个频移、3 档 SNR、20 个独立 seed；另加 280 例单音半 bin 边界测试。采用完整 8192 点浮点谱，未使用降采样快照。',
        f"单音 log-power 三点插值在 SNR≥20dB 时 P95 误差 {frequency['tone_candidate']['p95_error_bins']:.5f} bin，达到离线 0.1 bin 目标。该结果未接入生产 GUI/RTL，不能算作 PL 延迟以内的硬件估计。",
        '宽带谱峰可偏离真实载频数 MHz，不能改名为载频。OFDM 在 20/30dB 时带宽中心满足本实验探索容差，但 RRC-QPSK 在 30dB 仅 94/100 满足；10dB 的噪声使 99% CDF 带宽中心明显失真。没有晋升通用载频估计器。','',
        '## 4. 证据与复现','',
        '- [机器可读汇总](phase4_existing_hardware_validation.json)',
        '- [正式矩阵](../captures/phase4_ofdm_20260922/finite/measurement_validation.json)',
        '- [频移边界](../captures/phase4_ofdm_20260922/boundary/measurement_validation.json)',
        '- [持续矩阵](../captures/phase4_ofdm_20260922/continuous/measurement_validation.json)',
        '- [噪声原始与统计](../build/phase4_noise_20260922/study.json)',
        '- [频点原始与统计](../build/phase4_frequency_20260922_v2/study.json)',
        '- [噪声抽样板测](../captures/phase4_noise_20260922/measurement_validation.json)',
        '', '每个矩阵前另跑 16 个原有限用例，本轮共 64 个兼容检查。所有目录保留原始记录和 SHA-256；生成器、配置、参考和当前构建证据均绑定。频点初次运行在输出 JSON 时遇到 NumPy 布尔序列化错误，保留原目录，修复后在 v2 新目录重新运行，未替换 seed 或调整算法。','']
    (ROOT/'reports/第四阶段已完成实验报告.md').write_text('\n'.join(lines),encoding='utf-8')
    print('PHASE4_EXISTING_HARDWARE_SUMMARY_PASS')
if __name__=='__main__':main()
