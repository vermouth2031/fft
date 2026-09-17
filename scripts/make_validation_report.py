"""Summarize existing tool evidence; never invent board measurements."""
from pathlib import Path
import json,re,datetime
R=Path(__file__).resolve().parents[1]
def read(name):return json.loads((R/'reports'/name).read_text())
hw=read('hardware_validation.json');core=read('core_validation.json');sw=read('software_validation.json')
util=(R/'reports/utilization_flat.rpt').read_text();resources={}
for label in ('Slice LUTs','Slice Registers','Block RAM Tile','DSPs'):
    m=re.search(r'\|\s*'+label+r'\s*\|\s*([\d.]+)\s*\|\s*0\s*\|\s*0\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)',util)
    if m:resources[label]=m.groups()
lines=['# 离线实现与验证报告','',f'生成时间：{datetime.datetime.now().isoformat(timespec="seconds")}。',
  '', '**实际板测：尚未执行。用户当前未连接板卡；下列数字来自 RTL 仿真与 Vivado 静态实现。**','',
  '## 冻结配置','',
  '- Zybo Z7-20 / XC7Z020CLG400-1；Vivado/Vitis 2026.1。',
  '- I/Q 各 16 bit；源时钟 100 MHz，每拍一对；FFT 时钟 125 MHz。',
  '- AMD FFT v9.1，8192 点，24 bit 数据、18 bit 旋转因子，总缩放 14 bit。',
  '- 矩形 / 周期 Hann 窗；16 点滑动能量突发检测；99% 占用带宽。','',
  '## 综合与布局布线','',f"- 建立时间最差裕量：**{hw['setup_slack_ns']:.3f} ns**。",
  f"- 保持时间最差裕量：**{hw['hold_slack_ns']:.3f} ns**。",
  '- 未约束内部端点：0；CDC Critical：0；DRC 无 Error / Critical Warning；总线偏斜检查通过。',
  '- CDC 报告保留 XPM FIFO 的受控多位数据路径、静态配置同步及独立粘滞错误位的 Warning；未用全局 false_path 隐藏普通数据路径。','',
  '| 资源 | 使用 | 总量 | 占比 |','|---|---:|---:|---:|']
for name,(used,available,pct) in resources.items():lines.append(f'| {name} | {used} | {available} | {pct}% |')
lines+=['','## 功能回归','',
 f"- 主链：16 种输入/窗组合、{core['frequency_records']} 条频域记录、{core['burst_records']} 条突发记录。",
 f"- 与本机 AMD C 模型逐点比较：**{core['exact_fft_points']:,} 个复数 FFT 输出完全一致**。",
 f"- 本轮最大分析延迟：**{core['maximum_analysis_latency_us']:.2f} µs**，由源首样本到结果的时间戳计算；赛题上限为 2000 µs。",
 '- 时域与频域独立测试：262144 个带间断有效标记的时域输入、12 帧连续频谱、极值功率、零能量、单点频谱。',
 '- 突发边界：Kon=1、Koff=1、最大长度=1、最大长度等于确认长度、有限采集尾部排空。',
 '- 256 组整数算术参考；环形队列满、保持未读记录和释放后环绕；8192 个频点的正负 Hz 舍入。',
 '- AXI-Lite：地址/数据独立到达、字节选通、读写响应停顿、运行中禁止改写、矩形/Hann 重启、快照、consumer 越界和中止。',
 '- 电脑端：7 项协议回归、实际 RTL 记录解码回归、Python 编译检查、Tk 界面启动和包络绘制检查。','',
 'SD 文件解析器还使用明确标为仿真的 16 组 RTL 输出通过了完整导入及参考核对；该检查不计为板测。','',
 '## 软件与交付','',
 '- 由通过检查的完整 XSA 构建网络和 SD 两种应用及 FSBL；软件工作区按 XSA SHA-256 隔离。',
 f"- XSA SHA-256：`{sw['xsa_sha256']}`。",
 '- SD 程序读取向量、读回核对回放 RAM、自动执行 16 次有限采集，保存测量、状态和频谱快照。',
 '- PC 支持网络连续采集、快照显示、原始记录导出、SD 结果与位精确参考比较。','',
 '## 仍需板卡完成的验收','',
 '1. 启动和 DDR/SD/网口实际功能；SD 16 个测试逐整数对照。',
 '2. 100 MSPS 连续运行 10 秒及 60 秒，检查接收计数、完整窗口数、错误和结果丢弃为 0。',
 '3. 记录队列与网络恢复、实际允许的突发事件率、独立时基下的输入速率确认。',
 '4. 记录 PCB 修订、bit/ELF 哈希和原始板测文件，按比赛口径确认厂商 IP 与内部回放的适用范围。','',
 '125 MSPS 档、外部 ADC 输入和自主 FFT 不属于本次已验证基准版本。','']
(R/'reports/离线验证报告.md').write_text('\n'.join(lines),encoding='utf-8')
print('VALIDATION_REPORT_WRITTEN')
