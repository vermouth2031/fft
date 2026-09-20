"""Summarize the current verified build and real-board results, without rerunning tests."""
from __future__ import annotations
import datetime
import json
import re
from pathlib import Path
from package_release import check
from package_validated import check_board, supplementary_evidence

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT / 'reports' / name).read_text(encoding='utf-8'))


def resources(path):
    text = path.read_text(encoding='utf-8')
    rows = {}
    for label in ('Slice LUTs', 'Slice Registers', 'Block RAM Tile', 'DSPs'):
        match = re.search(r'\|\s*' + label + r'\s*\|\s*([\d.]+)\s*\|\s*0\s*\|\s*0\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)', text)
        if not match:
            raise ValueError(f'Missing resource {label} in {path}')
        rows[label] = match.groups()
    return rows


def main():
    hw, sw, core = check()
    board = check_board()
    _, boot_verified = supplementary_evidence()
    old = read('baseline_20260917/hardware_validation.json')
    extended, gui = read('current_extended_validation.json'), read('current_gui_validation.json')
    frame = read('frame_length_validation.json')
    sd_test = read('current_sd_validation.json')
    roi = read('roi_timing.json')
    golden = json.loads((ROOT / 'data/golden_results.json').read_text(encoding='utf-8'))['cases']
    wide = next(case for case in golden if case['name'] == 'qpsk_sps2' and case['mode'] == 'hann')
    bandwidths = [window['bandwidth_hz'] / 1e6 for window in wide['windows']]
    lines = ['# 本轮优化验收报告', '',
             f"生成时间：{datetime.datetime.now().astimezone().isoformat(timespec='seconds')}。",
             '', '本轮维持 Zybo Z7-20、I/Q各16位、100MSPS板内回放、125MHz FFT核和8192点AMD FFT。硬件接口版本为 `0x00010001`。', '',
             '## 实施结果', '',
             '- 增加数字零背景波形测长，同时保留原门限检测。模式、零间隔和边界标志贯通RTL、ARM协议、客户端及GUI。',
             '- 在ROI屏蔽功率后增加一拍流水，保持频谱数值及每拍吞吐。该阶段增加8ns，收益按下表的布线后裕量评价。',
             '- 根README统一入口；核心电路、软件、测试、脚本和文档职责明确；历史报告和日志归档，清除过时状态文件与一次性探测脚本。',
             '- 仿真、实际FFT配置、硬件、软件、BOOT、部署日志和板测原始数据均关联SHA-256，打包时重新检查。', '',
             '## 新旧实现对照', '', '| 项目 | 2026-09-17基线 | 本轮 |', '|---|---:|---:|',
             f"| Setup裕量/ns | {old['setup_slack_ns']} | {hw['setup_slack_ns']} |",
             f"| Hold裕量/ns | {old['hold_slack_ns']} | {hw['hold_slack_ns']} |",
             f"| CDC Critical | {old['cdc_critical']} | {hw['cdc_critical']} |",
             f"| 未约束内部端点 | {old['unconstrained_internal_endpoints']} | {hw['unconstrained_internal_endpoints']} |"]
    before = resources(ROOT / 'reports/baseline_20260917/utilization_flat.rpt')
    after = resources(ROOT / 'reports/utilization_flat.rpt')
    for label in before:
        lines.append(f"| {label} | {before[label][0]} / {before[label][1]} | {after[label][0]} / {after[label][1]} ({after[label][2]}%) |")
    lines += [f"| 完整网络数值套件最大分析延迟/µs | 199.78 | {board['maximum_analysis_us']} |",
              f"| 完整网络数值套件最大发布延迟/µs | 200.12 | {board['maximum_publish_us']} |", '',
              f"局部频谱路径复查：ROI寄存器端点裕量{roi['roi_register_slack_ns']}ns，峰值寄存器端点裕量{roi['peak_register_slack_ns']}ns；原基线最差ROI/峰值路径为0.109ns。全局瓶颈现位于FFT IP内部高扇出布线，整体裕量反而缩小。因此保留局部流水用于分离长组合路径，但不宣称全局时序提升，不提高时钟。", '',
              '时延以首样本进入至结果相应时刻定义，按100MHz标称计数换算，不含电脑绘图延迟。增加流水与新检测功能后的系统延迟按实测列出，不将局部时序裕量改善描述成延迟下降。', '',
              '## 仿真与软件', '',
              f"- 原16组合、{core['frequency_records']}条频域记录、{core['exact_fft_points']}个复数FFT输出与位精确参考一致。",
              f"- 核心仿真最大分析延迟 {core['maximum_analysis_latency_us']}µs。",
              '- 新数字零检测覆盖有效气泡、极短帧、满幅、间隔边界、跨窗、结束及强制分段；频谱测试覆盖ROI、同峰、帧尾、双bank、溢出和快照。']
    for name in ('sim_digital_burst', 'sim_spectrum_edges'):
        log = (ROOT / 'build/logs' / (name + '.log')).read_text(encoding='utf-8', errors='replace')
        marker = re.search(r'(?m)^' + ('DIGITAL_BURST_PASS' if name == 'sim_digital_burst' else 'SPECTRUM_EDGES_PASS') + r'[^\r\n]*', log)
        if marker:
            lines.append('- `' + marker.group(0) + '`。')
    lines += [f"- 软件状态 {sw['status']}；FSBL、SD、UDP应用由本轮XSA生成。",
              '- 原门限黄金结果、13字UDP配置兼容、15字扩展配置、模式/采样率元数据、SD解析和主机参考测试通过。', '',
              '## 实板数值与帧长', '',
              f"完整套件：32组有限采集，加两种模式各10秒/60秒的4组连续采集。共精确核验 **{board['frequency_records']}条频域、{board['burst_records']}条突发**。",
              f"同时精确核对 {sum(row['exact_snapshot_values'] for row in board['cases'])} 个可用硬件快照点。所有正常采集完整，错误/硬件丢弃/UDP缺包均为0。", '',
              f"QPSK sps=2、Hann窗的4个窗口：99%占用带宽 {min(bandwidths):.6f}～{max(bandwidths):.6f}MHz，与本轮板测逐点引用的位精确结果一致。该数值不是RRC理想支撑宽度，也不是100MSPS频轴全宽。", '',
              '| 波形 | 数字支撑真值/点 | 门限测长/点 | 数字零测长/点 |', '|---|---:|---:|---:|']
    for name in ('burst_fs4', 'short512_boundary', 'qpsk_sps4', 'qpsk_sps2'):
        cases = {r['detector']: r for r in frame['cases'] if r['vector'] == name and r['window'] == 'hann'}
        lines.append(f"| {name} | {cases['digital-zero']['reference_length']} | {cases['threshold']['measured_length']} | {cases['digital-zero']['measured_length']} |")
    lines += ['', '数字零模式所选8组完整零背景波形，起点、终点和长度误差均为0点。门限模式仍按其原算法正确工作；不能对全部输入固定减15点。详见[帧长度定义与误差分析](帧长度定义与误差分析.md)。', '',
              '## 压力、故障恢复与GUI', '', '| 场景 | 结果 |', '|---|---|']
    for row in extended['cases']:
        suffix = ''
        if 'exact_burst_records' in row:
            suffix = f"；{row['exact_burst_records']}条突发"
            suffix += (f"；{row['burst_rate_per_nominal_second']:.3f}次/秒" if 'pressure' in row['name'] else '（有限采集）')
        lines.append(f"| {row['name']} | {row['status']}{suffix} |")
    lines += ['', '过载和接收故障是有意注入的不完整采集，独立标记，不能作为无损性能成绩。随后正常采集必须恢复通过；本轮没有人工拔网线或物理断电测试。', '',
              f"GUI实测 {len(gui['tests'])}项通过，包括定时门限、数字零有限采集、主动停止与离线显示。截图及线程退出/板卡停止结果保存在当前GUI报告对应目录。", '',
              '## 启动与交付', '',
              f"新版SD自动测试应用通过16组有限采集和全部数值核验，精确核对{sd_test['exact_snapshot_values']}个快照点；最大分析延迟{sd_test['maximum_analysis_us']}µs。这是实际SD文件读写及新版SD ELF测试，通过JTAG装载应用；启动来源另行核验。", '',
              f"实体SD启动验证：{'通过；全量写入读回与SD模式系统复位后数值采集均通过' if boot_verified else '未完成，不能将JTAG装载当作SD启动'}。",
              'SD系统复位不等同手动断电冷启动。网络启动包与SD自动测试启动包每次选择一套BOOT.BIN。', '',
              '使用 `python scripts/package_validated.py` 生成含源码、启动包、原始记录、截图和散列清单的已验证交付包。只通过构建的包与经过实板验证的包明确分开。', '',
              '## 证据与适用范围', '',
              '- [工程入口](../README.md)、[冷启动验证报告](冷启动验证报告.md)。',
              '- `core_validation.json`、`hardware_validation.json`、`software_validation.json`、三份provenance记录。',
              '- `current_deployment.json`、`current_board_validation.json`、`current_extended_validation.json`、`current_gui_validation.json`。',
              '- `frame_length_validation.json`、`current_sd_validation.json`、`sd_boot_update.json`及每条报告指向的原始采集。', '',
              '当前100MSPS指电脑装载后板内连续回放，不是1G网口实时输入400MB/s的新数据；FFT使用AMD IP。零背景长度不是协议帧解码，带噪/偏置场景应使用门限检测并解释误差。',
              '更宽信号验证、进一步降低延迟和125MSPS属于后续探索；本轮没有把未实现性能写入成果。参赛仍需补队伍信息、真实硬件照片与赛方要求的视频/模板。', '']
    (ROOT / 'reports/本轮优化验收报告.md').write_text('\n'.join(lines), encoding='utf-8')
    print('ACCEPTANCE_REPORT_PASS')


if __name__ == '__main__':
    main()
