"""Render the verified suite's tables and bind delivery evidence; no board access."""
import argparse
import collections
import csv
import json
from pathlib import Path
import statistics

from validate_measurements import ROOT, read, save
from record_build_stage import sha


def flat(row, prefix=''):
    result={}
    for key,value in row.items():
        key=prefix+key
        if isinstance(value,dict):
            result.update(flat(value,key+'_'))
        else:
            result[key]=json.dumps(value,ensure_ascii=False) if isinstance(value,list) else value
    return result


def write_csv(path, rows):
    rows=[flat(row) for row in rows]
    fields=list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields)
        writer.writeheader();writer.writerows(rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('summary',type=Path)
    args=parser.parse_args()
    r=read(args.summary)
    if r['status']!='PASS':raise ValueError('Suite must be verified before reporting')
    report_dir=ROOT/'reports'
    detection=report_dir/'phase2_detection_summary.csv'
    bandwidth=report_dir/'phase2_bandwidth_summary.csv'
    write_csv(detection,r['detection_groups'])
    write_csv(bandwidth,r['bandwidth_groups'])
    groups=collections.defaultdict(list)
    for stage in r['stages']:
        if stage['stage'] in ('s3_finite','s3_refinement'):
            with (Path(stage['folder'])/'errors.csv').open(encoding='utf-8-sig') as stream:
                for row in csv.DictReader(stream):
                    if row['category']=='wideband':
                        groups[(float(row['rolloff']),row['window'])].append(row)
    total_cases=sum(s['cases'] for s in r['stages'])
    freq=sum(s['frequency_records'] for s in r['stages'])
    bursts=sum(s['burst_records'] for s in r['stages'])
    analysis=max(s['maximum_analysis_us'] for s in r['stages'])
    publish=max(s['maximum_publish_us'] for s in r['stages'])
    lines=['# 第二阶段完整验收报告','',
        '日期：2026-09-21。板卡：Zybo Z7-20，硬件接口版本 `0x00010001`。', '',
        '**已完成 S1 完整扫描、S2 噪声/偏置适用范围验证、S3 宽带分档与连续实板验证，以及对应的本地测量交付。** '
        'S4 完成两次无收益时序实验并保留基线；S5 完成延迟分解并决定不实施四点扫描；S6 是本轮未启用的可选档位。','',
        'S0 基线和首批 S1 记录见 `第二阶段测量与性能报告.md`，旧报告与冻结交付包保持原样。'
        '本报告不将新测试范围扩大描述为电路提速。','',
        '## 实板矩阵与证据','',
        f'本轮新增 **{total_cases} 组**，逐条核验 **{freq:,} 条频域记录、{bursts:,} 条突发记录**。'
        '每个矩阵开始前另运行原 16 组有限回归（共 9 轮、144 组，不计入新增计数）。', '',
        '| 阶段 | 新增组数 | 频域记录 | 突发记录 | 数值核验 |',
        '|---|---:|---:|---:|---|']
    for s in r['stages']:
        lines.append(f"| {s['stage']} | {s['cases']} | {s['frequency_records']:,} | {s['burst_records']:,} | {s['status']} |")
    lines += ['',f'本轮最大分析/发布延迟 **{analysis:.2f}/{publish:.2f}µs**。正常采集无丢记录、无 FFT 溢出、无未解释硬件错误，'
        '并核对实际寄存器、epoch/config_id、时戳、序号及可用快照。', '',
        '结构化总表：`phase2_complete_validation.json`；原始目录：`captures/phase2_complete_20260921/`。'
        '每个子目录保存实际输入绑定、参考、寄存器读回、原始二进制、逐窗 `errors.csv` 和逐例报告。'
        '所有原始记录已再次离线核验，交付打包还会重做数值与散列检查。', '',
        '## S1：频率、幅度与定点边界','',
        '74 个波形×矩形/Hann 两窗，共 148 组、592 个窗口；覆盖正负整数/非整数频点、±47/49MHz、'
        '等幅/不等幅双音、11 档单音/突发/QPSK 幅度、I/Q 单路和双路负满幅、零输入。', '',
        f"适用单音窗口 {r['normal_frequency_error_bins']['count']} 个，最大峰频误差 "
        f"**{r['normal_frequency_error_bins']['maximum']:.8f} bin**，全部符合最近 bin 预期。"
        '100MSPS/8192 的 1 bin=12207.03125Hz。适用统计包括合格幅度的单音及单音突发窗口，'
        '低幅、双音、频带边缘、QPSK 和零功率不计入该成绩。', '',
        '峰值、RMS、能量与定点参考逐项一致；每窗同时输出相对量化输入、原浮点输入的绝对/相对误差。'
        '原始幅度单位为复包络数字码值，不宣称物理电压或未定义的 dBFS。', '',
        '592 个窗口中，峰值/RMS 相对量化输入的最大绝对误差为 0.0000151434/0.0000152319 码，'
        '均小于一个 Q16.16 最低位；相对原浮点输入的最大误差为 0.703644/0.092432 码。'
        '各类别的最大值、中位数、P95 保存在 S1 原始汇总报告中。', '',
        '## S2：检出能力与失效范围','',
        '训练使用 seed 81001～81003；独立验收使用 82000～82024。每个 SNR 有 25 个独立输入、'
        '100 个已知突发；同一 seed 跨 SNR 复用基础噪声，不能将跨 SNR 总数当完全独立的噪声实现。', '',
        '固定门限在训练集 30/20/10dB 各将四个突发误合并。选定方案使用主机读取已知前导静默区的前 1024 点，'
        '估计背景功率，ton=ceil(16×背景均方功率×4)、toff=ceil(16×背景均方功率×2)，'
        'kon/koff=8/32。参数在独立验收前冻结；不是逐帧根据真值调参，也不是 FPGA 在线自适应门限。', '',
        '确定性一对一匹配要求至少覆盖真值长度的 50%；“正常”还要求起止各在 ±32 点内且无拆分/合并。'
        '100MSPS 下 1 点=0.01µs，±32 点=±0.32µs。', '',
        '| SNR | 已知突发 | 匹配 | 正常 | 漏检 | 背景虚警 | 最大绝对长度误差（已匹配，点） |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for g in sorted((g for g in r['detection_groups'] if g['stage']=='s2_validation'),
                    key=lambda g:int(g['group'].split('snr')[1]),reverse=True):
        error=g['length_absolute_error_samples'].get('maximum','不适用')
        lines.append(f"| {g['group'].split('snr')[1]}dB | {g['known_bursts']} | {g['matched']} | {g['normal_matches']} | {g['missed']} | {g['false_alarms']} | {error} |")
    lines += ['',
        '30/20/10dB 各有一个已匹配突发的结束偏差为 +46 点，超出正常容差；保留为边界失败。'
        '0dB 有一个短的重叠检测片段，未达到 50% 匹配要求，作为“未匹配重叠检测”统计；'
        '背景虚警为零不等于检出能力良好。每档背景观测约 4.096ms，不能据此宣称长期虚警率为零。', '',
        '其余 102 组覆盖短帧、确认长度附近间隔、直流偏置、低幅、成形尾部与数字零不适用场景：', '',
        '- 零背景 64/512/4096/24576 点数字零突发，起止及长度误差均为 0 点。',
        '- 数字零模式 gap_min=32 时，小于 32 点间隔按规则合并；门限模式还受 16 点滑动能量和 32 点关断确认影响。',
        '- 偏置 (128,128)、幅度 256 有拆分/漏检；偏置 (512,-512)、幅度 256 全部漏检；幅度 1024 虽匹配但边界容差不满足。',
        '- 数字零在带噪背景下明确标为不适用；0dB 低幅输入同样失效。',
        '- QPSK 分别保留符号区间、成形区间、量化非零区间，避免把滤波尾部称为协议帧长度。', '',
        '完整 59 个工况分组的样本数、漏检、虚警、误合并/拆分、背景时间、起止/长度误差 '
        'min/median/P95/max 及量化前后实测 SNR 见 `phase2_detection_summary.csv`。'
        '**本阶段 PASS 表示硬件符合声明算法、失败完整报告，不表示所有 SNR 下均成功检测。**', '',
        '## S3：实际 99% 带宽与稳定性','',
        '波形 Rs=50Msym/s、SPS=2，RRC 长度 21 taps，峰值归一化到 24000 码，'
        '每档三个 seed（91001～91003），矩形/Hann 两窗。每组 32768 点分四个 FFT 窗口，'
        '稳态和突发边沿分别统计；所有输入写 int16 前检查溢出，PAPR/峰值余量保存在清单。', '',
        '| RRC α | 理想支撑 MHz | 窗 | 全部12窗 min/median/max MHz | 稳态6窗 min/max MHz |',
        '|---:|---:|---|---|---|']
    for (alpha,window),rows in sorted(groups.items()):
        values=[float(x['bandwidth_hz'])/1e6 for x in rows]
        steady=[float(x['bandwidth_hz'])/1e6 for x in rows if x['window_region']=='steady']
        lines.append(f'| {alpha:g} | {(1+alpha)*50:g} | {window} | '
            f'{min(values):.6f}/{statistics.median(values):.6f}/{max(values):.6f} | '
            f'{min(steady):.6f}/{max(steady):.6f} |')
    lines += ['',
        '实际 99% 带宽依据完整 8192 点硬件谱，逐条与 AMD 位精确参考一致。'
        '同时以实际量化输入和相同 Hann 系数计算 NumPy 浮点 CDF 带宽，仅作算法误差分析；'
        '差值及分窗 min/median/P95/max 见 `phase2_bandwidth_summary.csv`。', '',
        '8 个滚降档位的矩形/Hann 10 秒连续采集全部通过；基于有限扫描及 10 秒结果选择 α=1.0 的 Hann 档，'
        '再完成 60 秒连续采集。60 秒逐条校验全部结果，不以第一周期代替完整性检查；'
        '带宽分布表只列输入块第一周期，避免把相同重复数据当作独立随机样本。', '',
        'α=0.6、中心频移 +25MHz 的输入跨 Nyquist 边界，列为异常适用范围案例，'
        '不计入扩大带宽成绩。当前线性 CDF 不支持环绕最短占用带宽。', '',
        '## S4～S6 与硬件版本','',
        '详见 `第二阶段性能优化决策.md` 和 `phase2_performance_decision.json`。'
        '两次布线实验最终 setup/hold 都是 0.030/0.004ns，没有取得新裕量；候选未晋升、未烧录。'
        '64 个仿真窗口的延迟分解已通过，四点扫描未实施，125MSPS 未启动。', '',
        '本轮 RTL、约束、固件、主机协议与 bit/XSA/ELF/BOOT 保持默认已验收版本。'
        '未更新实体 SD，因此保留原 SD/用户确认冷启动证据；不宣称本轮再次物理断电。'
        '板上可读版本与配置已核对，但没有运行时 bitstream SHA-256 寄存器。', '',
        '## S7：复现与交付','',
        '完整仿真于 2026-09-20 18:51 通过，其来源与日志散列在本轮开始前重新核对。'
        '本轮采集期间这些输入保持固定。最终资格工具在不含历史 reports/captures 的独立副本中再次运行：'
        '11 项测试通过，原 16 组黄金数据与 524288 个复数 FFT 输出逐字节一致。', '',
        '核心仿真波形保存在 `build/vivado/iq_analyzer.sim/sim_1/behav/xsim/tb_core_behav.wdb`，'
        '可用 Vivado 波形查看器打开；同目录 `latency_events.csv` 提供 64 个窗口的关键事件时间。', '',
        '每次选择新的输出路径，并确保 GUI/脚本只运行一个控制端：', '',
        '```powershell',
        'python scripts/validate_measurements.py capture --references build/qualification/phase2_complete_20260920/s1_complete/references/index.json --out captures/my_s1 --board 192.168.1.10',
        'python scripts/validate_measurements.py verify --run captures/my_s1',
        'python scripts/summarize_phase2.py captures/phase2_complete_20260921 --out reports/phase2_complete_validation.json',
        'python scripts/write_phase2_report.py reports/phase2_complete_validation.json',
        'python scripts/package_validated.py --measurement-suite reports/phase2_complete_validation.json --out release/phase2-complete-20260921',
        'python scripts/verify_delivery.py release/phase2-complete-20260921',
        '```', '',
        '交付包包含源码、启动产物、输入/参考、原始二进制、配置读回、误差表、失败统计和时序实验。'
        '重复的逐记录 JSON/CSV 导出数组可用 `host/iq_client.py decode` 从原始二进制重建。'
        '采集身份保存原机器绝对路径；移机先运行交付散列检查，需重跑时在本机 Vivado 下重新生成参考到新目录。', '',
        '演示硬指标表、适用范围表、原理框图与操作脚本见 `参赛演示提纲.md`。'
        '**实物照片、队伍信息及赛事格式的最终演示视频仍需参赛方补充；S7 参赛材料不计为全部完成。**','']
    report=report_dir/'第二阶段完整验收报告.md'
    report.write_text('\n'.join(lines),encoding='utf-8')
    files=[report,detection,bandwidth,report_dir/'第二阶段性能优化决策.md',
        report_dir/'phase2_performance_decision.json',report_dir/'参赛演示提纲.md',
        report_dir/'phase2_complete_portability.json',report_dir/'phase2_final_board_state.json',
        ROOT/'scripts/write_phase2_report.py',
        ROOT/'scripts/summarize_phase2.py',ROOT/'build/phase2_complete_simulation.log']
    files.append(ROOT/'build/vivado/iq_analyzer.sim/sim_1/behav/xsim/tb_core_behav.wdb')
    portability=read(report_dir/'phase2_complete_portability.json')
    for name,value in portability['files'].items():
        if sha(ROOT/name)!=value:raise ValueError('Portability evidence changed')
        files.append(ROOT/name)
    for experiment in read(report_dir/'phase2_performance_decision.json')['experiments']:
        for name,value in experiment['evidence'].items():
            if sha(ROOT/name)!=value:raise ValueError('Timing evidence changed')
            files.append(ROOT/name)
    for stage in r['stages']:
        files.append(ROOT/'build'/f"phase2_{stage['stage']}_20260921.log")
    r['evidence']={p.relative_to(ROOT).as_posix():sha(p) for p in files}
    save(args.summary,r)
    print('PHASE2_REPORT_WRITTEN',report)


if __name__=='__main__':main()
