"""Render Phase 3 acceptance from verified data; preserve pending boot status."""
import json
from pathlib import Path
from record_build_stage import ROOT,sha
from summarize_phase3 import verify_suite
from package_validated import require
from write_acceptance_report import resources


def read(name):return json.loads((ROOT/'reports'/name).read_text(encoding='utf-8'))


def main():
    suite_path=ROOT/'reports/phase3_complete_validation.json';suite=verify_suite(suite_path)
    hw=read('hardware_validation.json');board=read('current_board_validation.json');core=read('core_validation.json')
    for kind in ('gui','extended'):
        ancillary=read(f'current_{kind}_validation.json')
        require(ancillary['status']=='PASS' and ancillary['current_board_validation_sha256']==sha(ROOT/'reports/current_board_validation.json'),
                f'Current {kind} acceptance is missing')
    sd_app=read('current_sd_validation.json')
    require(sd_app['status']=='PASS' and all(sha(ROOT/'artifacts'/n)==v for n,v in sd_app['artifacts'].items()),
            'Current SD application acceptance is missing')
    usage=resources(ROOT/'reports/utilization_flat.rpt')
    cold=read('current_cold_boot_validation.json')
    cold_current=(cold['status']=='PASS' and cold['previous_board_validation_sha256']==sha(ROOT/'reports/current_board_validation.json'))
    sd=read('sd_boot_update.json')
    sd_current=(sd['status']=='PASS' and sd['jtag_board_validation_sha256']==sha(ROOT/'reports/current_board_validation.json'))
    groups={(r['stage'],r['group']):r for r in suite['detection_groups']}
    maximum=max(board['maximum_analysis_us'],*(s['maximum_analysis_us'] for s in suite['stages']))
    publish=max(board['maximum_publish_us'],*(s['maximum_publish_us'] for s in suite['stages']))
    cases=sum(s['cases'] for s in suite['stages']);freq=sum(s['frequency_records'] for s in suite['stages']);bursts=sum(s['burst_records'] for s in suite['stages'])
    lines=['# 第三阶段完整验收报告','',
        '本轮实施四路频谱扫描、FFT高扇出控制驱动复制和正式robust门限档位。输入仍为I/Q各16位、100MSPS板内回放、8192点FFT，FFT时钟125MHz，接口版本0x00010001。','',
        f"当前启动状态：实体SD{'写入/读回及复位启动通过' if sd_current else '尚未完成当前镜像验证'}；物理断电上电{'后网络验收通过' if cold_current else '待用户实际操作及网络验收'}。",'',
        '## 1. 主要结果','',
        '| 指标 | 第二阶段基线 | 本轮结果 |','|---|---:|---:|',
        f'| 最大分析延迟 | 199.79µs | {maximum:.2f}µs |',
        f'| 最大发布延迟 | 200.12µs | {publish:.2f}µs |',
        f"| Setup / Hold | 0.030 / 0.004ns | {hw['setup_slack_ns']:.3f} / {hw['hold_slack_ns']:.3f}ns |",
        f"| LUT / FF | 12359 / 20030 | {usage['Slice LUTs'][0]} / {usage['Slice Registers'][0]} |",
        f"| BRAM / DSP | 90.5 / 53 | {usage['Block RAM Tile'][0]} / {usage['DSPs'][0]} |",'',
        f'最大分析延迟较基线下降约{(199.79-maximum)/199.79*100:.2f}%。这是板内分析及发布指标，不包括电脑装载和网络往返。',
        '时钟约束没有放宽；CDC Critical=0、无未约束内部端点、DRC和总线偏斜检查通过。','',
        '## 2. 门限训练与独立验证','',
        '仅用训练seed选择参数，冻结后用125个独立输入seed×每输入4个突发，得到每SNR500个已知突发。正式robust参数为M=16、ton倍数3、toff倍数1.75、kon16、koff8，背景由明确静默的前1024点估计。',
        '主验证波形为未成形QPSK（每符号2点），每个32768点输入含4个4096点突发，并加入AWGN。同一组125个seed用于五档SNR，因此625组不是625个互相独立的seed；每档统计和bootstrap分别按输入seed分组。',
        '主训练和独立验收幅度为4096码，以保留0dB下int16余量；历史8192码数据另外作为已知回归，不能直接混为相同幅度的独立前后对照。','',
        '| SNR | 匹配 / 已知 | 正常 / 已知 | 虚警 | 拆分真值 | 长度绝对误差P95（点） |',
        '|---|---:|---:|---:|---:|---:|']
    for snr in (30,20,10,5,0):
        g=groups[('validation',f'robust_snr{snr}')];p95=g['length_absolute_error_samples'].get('p95')
        lines.append(f"| {snr}dB | {g['matched']}/{g['known_bursts']} | {g['normal_matches']}/{g['known_bursts']} | {g['false_alarms']} | {g['split_truths']} | {p95 if p95 is not None else '无匹配，非0误差'} |")
    g=groups[('validation','robust_snr5')];ci=g['seed_block_bootstrap95_normal_rate']
    noise=groups[('noise_only','noise_only')]
    lines += ['',
        f"5dB正常率为{g['normal_detection_rate']*100:.2f}%；以独立输入seed为重采样单位的95% bootstrap区间为{ci[0]*100:.2f}%～{ci[1]*100:.2f}%，没有将同一输入的4个突发当作4个完全独立seed。",
        '正常匹配要求一对一、至少50%真值重叠、起止误差各≤32点且无误合并/拆分。0dB结果完整保留，未达标不从分母剔除。','',
        f"独立纯噪声256块，共{noise['background_observation_us']/1e6:.8f}秒，观测虚警{noise['false_alarms']}。零观测不等于长期虚警率为零；Poisson独立事件假设下的95%上限约{noise.get('poisson_zero_event_upper95_per_second',0):.2f}次/秒，短观测时间限制了该结论。",'',
        '同一历史8192码验证集的前后对照：','',
        '| SNR | 原静默估计参数正常数 | robust正常数 | 已知突发 |','|---|---:|---:|---:|']
    for snr in (30,20,10,5,0):
        old=groups[('legacy_regression',f'validation_snr{snr}')]
        new=groups[('robust_regression',f'robust_regression_validation_snr{snr}')]
        lines.append(f"| {snr}dB | {old['normal_matches']} | {new['normal_matches']} | {old['known_bursts']} |")
    lines += ['', '## 3. 实际验收范围','',
        f'新增及回归矩阵共{cases}组，另含96组每轮启动前的旧用例检查。矩阵内{freq}条频域记录、{bursts}条突发记录逐条符合独立定点参考。','',
        '| 阶段 | 组数 | 频域记录 | 突发记录 | 最大分析延迟µs |','|---|---:|---:|---:|---:|']
    for s in suite['stages']:
        lines.append(f"| {s['stage']} | {s['cases']} | {s['frequency_records']} | {s['burst_records']} | {s['maximum_analysis_us']:.2f} |")
    lines += ['',
        f"完整核心仿真{core['exact_fft_points']}个FFT复数点逐位一致，{core['frequency_records']}个频域结果通过。另有20组四路CDF/ROI/峰值边界及6144个快照值。",
        f"基础双模式板测{len(board['cases'])}组通过，涵盖有限输入和10/60秒连续采集；GUI实机、过载、接收故障及恢复、SD应用16组均另有当前构建证据。",
        '17组宽带连续测试保留最宽α=1.0档的60秒运行。连续测试循环同一输入块，用于证明持续计算/传输稳定，不增加独立噪声样本。','',
        '## 4. 正式入口和兼容性','',
        'CLI/GUI支持legacy、robust及人工ton/toff/kon/koff。资格采集复用同一正式配置路径；不再临时替换Client。START前读回回放、窗、ROI、门限和检测模式；参数冲突、非法范围或读回不一致均拒绝启动。',
        '元数据保存用户请求、静默区、背景估计、实际参数及硬件读回。旧命令默认值及13/15字协议兼容性保留。robust只改善声明模型下的测量，不识别通信协议帧。','',
        '自动估计的最小ton/toff为2/1，修复全零静默区算出toff=0后无法满足严格关断条件的问题。15项资格工具测试包含该边界；全部原始验收IQ输入保持不变，仅9组零背景回归的自动门限参考随此修正更新。','',
        '## 5. 条件性研究的实际结论','',
        '较长能量窗、DC离线补偿、噪声漂移/污染、Realtime供数及125MSPS预算均已评估，详见[第三阶段条件性优化决策](第三阶段条件性优化决策.md)。较长窗未满足边界标准，板内DC新模式未晋升；Realtime供数条件和125MSPS时序预算不满足，保持原IP模式及实际时钟。',
        '没有外部ADC、没有真实125MSPS档位、没有板内DC补偿或在线CFAR。较大偏置、未知前导、非平稳背景和0dB不属于通用保证。','',
        '## 6. 构建、部署与复现','',
        '硬件及完整仿真在隔离工作树完成，按逐文件SHA校验导入主工程，保留实际原始日志和来源清单。新bit、XSA、匹配固件及BOOT一并验证；原第二阶段冻结包保持不变。',
        '同版本接口没有运行时bitstream散列寄存器，当前身份由构建清单、JTAG部署、SD读回及冷启动流程绑定，不仅凭版本号判断。','',
        f"- bit SHA-256：`{sha(ROOT/'artifacts/iq_analyzer.bit')}`",
        f"- BOOT_udp.BIN SHA-256：`{sha(ROOT/'artifacts/BOOT_udp.BIN')}`",
        '- 详细统计：`reports/phase3_complete_validation.json`。',
        '- 原始矩阵：`captures/phase3_complete_20260921/`。',
        '- 本地完整包：`release/phase3-complete-20260921.zip`；只有当前物理冷启动验收完成后才生成正式完整包。',
        '- 解压后运行 `python scripts/verify_delivery.py .` 验证文件；需要重新进行数值验收时重建对应参考和板测，不修改历史PASS。','']
    path=ROOT/'reports/第三阶段完整验收报告.md';path.write_text('\n'.join(lines),encoding='utf-8')
    suite['evidence'][path.relative_to(ROOT).as_posix()]=sha(path)
    suite_path.write_text(json.dumps(suite,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('PHASE3_REPORT_WRITTEN',path)


if __name__=='__main__':main()
