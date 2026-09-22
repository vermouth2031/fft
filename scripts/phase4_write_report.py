"""Write technical completion only after matching SD and physical cold-start proof."""
import datetime
import json
from pathlib import Path
import re
from record_build_stage import ROOT,sha
from phase4_summarize_final import verify_report
from package_validated import supplementary_evidence,check_board
from record_boot_stage import verify_boot

def read(name):return json.loads((ROOT/name).read_text(encoding='utf-8'))
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    measured=verify_report(ROOT/'reports/phase4_final_measurements.json');board=check_board();verify_boot()
    imported=read('reports/phase4_candidate_import.json')['isolated_board']
    assert imported['status']=='PASS' and imported['hardware']==board['hardware']
    extra,boot_verified=supplementary_evidence()
    cold=read('reports/current_cold_boot_validation.json');sd=read('reports/current_sd_validation.json')
    assert boot_verified and cold['status']=='PASS' and sd['status']=='PASS'
    assert cold['hardware_before']==board['hardware'] and cold['epoch_before']==0
    demo=read('captures/phase4_final_20260922/demo/gui_validation.json');assert demo['status']=='PASS'
    hardware=read('reports/hardware_validation.json');assert hardware['setup_slack_ns']>=.10 and hardware['hold_slack_ns']>=0
    utilization=(ROOT/'reports/utilization_flat.rpt').read_text()
    resources={}
    for key,label in (('lut','Slice LUTs'),('ff','Slice Registers'),('bram36','Block RAM Tile'),('dsp','DSPs')):
        match=re.search(r'^\|\s*'+re.escape(label)+r'\s*\|\s*([0-9.]+)\s*\|',utilization,re.M)
        assert match,'Missing utilization '+label
        resources[key]=float(match.group(1))
    assert resources['bram36']/140<=.75
    rtl=read('reports/core_validation.json');assert rtl['exact_fft_points']==524288
    report=dict(schema='iq-phase4-complete-v1',status='PASS',created_at=datetime.datetime.now().astimezone().isoformat(),
        hardware=board['hardware'],hardware_timing=hardware,resources=resources,measurements_sha256=sha(ROOT/'reports/phase4_final_measurements.json'),
        physical_cold_boot_verified=True,sd_readback_and_reset_verified=True,sd_finite_cases=16,
        physical_cold_boot_cases=len(cold['cases']),demo_presets=4,
        maximum_analysis_us=max(measured['maximum_analysis_us'],imported['maximum_analysis_us'],cold['maximum_analysis_us'],sd['maximum_analysis_us']),
        maximum_publish_us=max(measured['maximum_publish_us'],imported['maximum_publish_us'],cold['maximum_publish_us']),
        maximum_scope='Current network matrix, byte-identical imported combined-build basic suite, SD and physical cold start; excludes intentional overload/loss injection',
        minimum_internal_obw_hz=measured['minimum_widest_internal_obw_hz'],
        actual_board_photo_provided=False,actual_board_video_provided=False,actual_gui_screenshots=True,
        unpromoted=['125 MSPS timing experiment: 0.029 ns setup margin',
            'Single-tone log-power interpolation remains offline',
            'Generic carrier/DC compensation/protocol parsing/external real-time input not enabled without defined requirements'],
        artifacts={n:sha(ROOT/'artifacts'/n) for n in ('iq_analyzer.bit','iq_analyzer.xsa','iq_udp.elf','iq_sd.elf','BOOT_udp.BIN','BOOT_sd.BIN')},
        evidence={p.relative_to(ROOT).as_posix():sha(p) for p in extra})
    for name in ('reports/phase4_final_measurements.json','reports/current_board_validation.json',
                 'reports/current_deployment.json','reports/phase4_candidate_import.json',
                 'reports/phase4_candidate_decisions.json','reports/phase4_requirements.json',
                 'reports/phase4_startup_validation.json',
                 'captures/phase4_final_20260922/demo/gui_validation.json'):
        report['evidence'][name]=sha(ROOT/name)
    for name in ('scripts/program_board.tcl','scripts/maintenance/sd_export.tcl',
                 'scripts/maintenance/run_sd_application.tcl','scripts/maintenance/sd_boot_writer.tcl'):
        report['evidence'][name]=sha(ROOT/name)
    for folder in ('build/phase4_jtag_startup_fix','captures/phase4_sd_20260922','captures/phase4_sd_20260922_retry'):
        for path in (ROOT/folder).rglob('*'):
            if path.is_file():report['evidence'][path.relative_to(ROOT).as_posix()]=sha(path)
    assert report['maximum_analysis_us']<=178
    save(ROOT/'reports/phase4_complete_validation.json',report)
    width=report['minimum_internal_obw_hz']/1e6
    delta=183.41-report['maximum_analysis_us']
    lines=['# 第四阶段完整验收报告','',
        f"完成时间：{report['created_at']}。正式实现为 I/Q 各 16bit、100 MSPS 板内回放、125 MHz FFT、8192 点 AMD FFT、八路谱扫描。",
        f"硬件接口 `0x00010002`，构建 ID `{board['hardware']['build_id']}`。本文所有正式性能数字来自该组合版本；隔离候选和旧版本仅作对比。",'',
        '## 1. 本轮结果','',
        '| 项目 | 实测或验收结果 |', '|---|---|',
        f"| 正常最大 PL 分析延迟 | {report['maximum_analysis_us']:.2f} µs，比原 183.41 µs 降低 {delta:.2f} µs |",
        f"| 正常最大发布延迟 | {report['maximum_publish_us']:.2f} µs |",
        f"| 指定最宽 OFDM 内部窗最小 99% 占用带宽 | {width:.6f} MHz |",
        f"| 建立 / 保持时间裕量 | {hardware['setup_slack_ns']:.3f} / {hardware['hold_slack_ns']:.3f} ns |",
        '| CDC 严重问题 / 未约束内部端点 | 0 / 0 |',
        f"| LUT / FF / BRAM36 / DSP | {resources['lut']:g} / {resources['ff']:g} / {resources['bram36']:g} / {resources['dsp']:g}；BRAM 占 {resources['bram36']/140*100:.2f}% |",
        f"| 原矩阵与新增矩阵 | 1653 + 367 = {measured['matrix_cases']} 组，另有 {measured['legacy_check_cases']} 组矩阵前兼容检查 |",
        f"| 基础板测 | {measured['basic_board_cases']} 项，有限与持续、两种检测模式 |",
        f"| 吞吐守恒检查 | {measured['throughput_checks']} 次全部通过，单次最多 {measured['maximum_samples_in_one_capture']} 对 IQ |",
        f"| 输入 FIFO 写侧高水位 | 最大 {measured['maximum_input_fifo_high_water']} / 4096 |",
        '| 启动 | 16 项 SD 应用测试、完整 BOOT 读回校验、SD 复位启动、此次用户断电重启后纯网口验收 |','',
        f"当前主工程完整网络矩阵最大分析/发布为 {measured['maximum_analysis_us']:.2f}/{measured['maximum_publish_us']:.2f} µs；上表保守纳入相同构建先行组合板测及 SD/冷启动的全部已验收最大值，不选择重复测试中较低的成绩。",'',
        '## 2. 优化实现','',
        '八路扫描采用 2/4/8 bin 平衡前缀流水，每拍处理八个频率升序 bin，保留完整 8192 点 CDF、等峰取较低 bin、ROI 和 1024 点显示快照语义。',
        '组合首次实现的 setup 裕量为 0.078 ns，最差路径是同步复位到宽数据流水寄存器。保留该结果后，仅去掉由有效标志保护的宽数据寄存器复位，继续复位控制、状态和有效标志；增加扫描中复位清除旧输出的测试，再重新完成完整仿真、实现和板测。',
        '新增只读构建 ID、采样/FFT/时间戳频率和记录格式字段。各时钟域独立计数，经握手快照读回。停止并排空后检查发出、接受、FFT 输入和输出计数相等，以及每窗 8192 点；持续运行中不把不同时刻的快照差当作丢样。',
        '网络与 SD 元数据保存身份和计数。未知格式、身份不符或计数不守恒会被验收拒绝。频率整数换算保持半单位远离零的舍入，与原 100 MSPS 数值逐项一致。','',
        '## 3. 宽带输入与统计口径','',
        '新矩阵含 240 组初始 OFDM、24 组频移边界、80 组次级最宽 OFDM、14 项合计 920 秒持续回放及 9 组预选噪声样本。每个矩阵前跑 16 组原有限输入。',
        f"最宽档设计跨度为 98.14453125 MHz，每端保护带约 0.927734 MHz。实际内部窗最小值为 {width:.6f} MHz，超过 95 MHz 的本轮工程目标。设计跨度不代替实际占用带宽；跨 Nyquist 输入不计入未折返带宽成绩。",
        '输入采用 4096 点 IFFT、256 点 CP、6 个完整符号、DC 空置、QPSK/16QAM 数据和随机 BPSK 导频。统一增益从独立训练 seed 冻结，正式用例保留全部 seed 和边沿窗。最终回归复用这些已冻结输入，不把再次采集当作新的独立随机样本。','',
        '## 4. 离线研究与未晋升分支','',
        '3153 个不重复噪声块共 1.03317504 秒，扣除静默估计前缀后 1.00088832 秒。三个幅度层分别观察到 0 个虚警；每层的条件性 Poisson 95% 上界约 8.98 次/秒，不能称虚警率为零。块间复位，不覆盖连续拼接或背景漂移。',
        '900 例频点研究及 280 例单音半 bin 测试形成离线证据。高 SNR 单音 log-power 插值有收益，但未接入生产测量；宽带谱峰与带宽中心不保证等于调制载频。',
        '合并版本首次 JTAG 部署后网络查询超时；SD 维护首次挂载未就绪，重试又出现导出程序在进入主函数前停于未定义指令异常。全部失败记录保留。JTAG 下载流程增加 ELF 下载前处理器复位，随后重新验证完整 SD 应用和网络矩阵。该修正针对观测到的启动状态，未将其称为所有间歇异常的唯一原因；SD 镜像启动与物理冷启动另有独立证据。',
        '125/125 MHz 时钟实验完成布局布线，setup 仅 0.029 ns，未达到 0.10 ns 门槛而未晋升；102–104 MHz 请求在当前预设下仍生成 100 MHz。正式版本没有宣称 125 MSPS。',
        '外部实时输入、自研 FFT、通用协议帧、DC 补偿及特定带宽/载频定义没有新的赛方说明，本轮不自行扩大这些术语的适用范围。','',
        '## 5. 比赛要求对照','',
        '| 要求 | 状态与证据边界 |','|---|---|',
        '| I/Q 位宽 ≥12bit | 各 16bit 数字输入；不声明模拟 ENOB |',
        '| IQ 速率 ≥100MSPS | 100 MSPS 板内连续回放；不是以太网上传或外部 ADC 链路 |',
        '| FFT ≥8192 点 | 8192 点 AMD FFT，完整频谱测量 |',
        f"| IQ 至频域信息 ≤2ms | 正常最大 PL 分析 {report['maximum_analysis_us']:.2f} µs；不包括电脑上传和绘图 |",
        '| 幅度与帧长 | 原始码值峰值/RMS、包络样本区间；不解析任意通信协议 |',
        f"| 频点与带宽 | 谱峰、99% 占用带宽；指定 OFDM 最小 {width:.6f} MHz，载频含义仍待赛方确认 |",'',
        '## 6. 交付与复现','',
        '- [电路说明](最终电路设计说明.md)、[寄存器与吞吐定义](../docs/phase4_registers.md)。',
        '- [完整测量汇总](phase4_final_measurements.json)、[完成状态和镜像散列](phase4_complete_validation.json)。',
        '- [冷启动报告](冷启动验证报告.md)、[时钟实验取舍](第四阶段时钟可行性结论.md)。',
        '- [答辩讲稿与预计提问](答辩材料/讲稿与预计提问.md)。答辩 PPT、真实 GUI 截图与校验回执随最终包交付。',
        '', '当前有真实 GUI 板测截图，未收到板卡实拍照片或现场视频；没有用生成图片冒充实物。团队个人资料未提供，材料不编造姓名或分工。',
        '物理冷启动依据本次安装之后用户明确确认的断电上电，再以纯网口查询和原始数值采集核验。旧第三阶段完整 ZIP 保留不变。','']
    detection=['### 带噪测长复测结果','',
        '每档为 125 个冻结 seed、500 个已知突发。这里统计算法检出，区别于逐条定点数值一致性。','',
        '| SNR | 已知突发 | 正常匹配 | 漏检 | 虚警 |','|---|---:|---:|---:|---:|']
    for snr in (30,20,10,5,0):
        group=next(g for g in measured['regression']['detection_groups']
                   if g['stage']=='validation' and g['group']==f'robust_snr{snr}')
        detection.append(f"| {snr} dB | {group['known_bursts']} | {group['normal_matches']} | {group['missed']} | {group['false_alarms']} |")
    detection+=['','正常匹配不计带异常标志的检测；0 dB 的失败输入完整保留，不能用数值核验 PASS 代替算法精度达标。','']
    insert=lines.index('## 4. 离线研究与未晋升分支')
    lines[insert:insert]=detection
    (ROOT/'reports/第四阶段完整验收报告.md').write_text('\n'.join(lines),encoding='utf-8')
    print('PHASE4_COMPLETE_TECHNICAL_ACCEPTANCE_PASS')

if __name__=='__main__':main()
