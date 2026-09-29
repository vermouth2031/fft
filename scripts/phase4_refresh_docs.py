"""Refresh current-version documentation from completed, matching acceptance reports."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    r=json.loads((ROOT/'reports/phase4_complete_validation.json').read_text())
    m=json.loads((ROOT/'reports/phase4_final_measurements.json').read_text())
    assert r['status']=='PASS' and r['physical_cold_boot_verified']
    analysis=r['maximum_analysis_us'];publish=r['maximum_publish_us'];width=r['minimum_internal_obw_hz']/1e6
    h=r['hardware_timing'];resources=r['resources'];identity=r['hardware']['build_id']
    p=ROOT/'reports/最终电路设计说明.md';text=p.read_text(encoding='utf-8')
    replacements={
        '本文以当前已验收的 100 MSPS 四路扫描硬件为准。第四阶段新增 OFDM 输入与测量研究已经形成独立证据；八路扫描、构建 ID 和提频仍按候选单独验证。后续若晋升新硬件，需同时更新本文、构建来源、实板报告和启动镜像，不能只改成绩数字。':
            f'本文对应已完成真板、SD 和此次物理冷启动验收的第四阶段组合版本：100 MSPS、八路谱扫描、构建 ID `{identity}`。bit/XSA/ELF/BOOT 与原始记录均在同一验收链中绑定。125 MSPS 实验未晋升。',
        '正常最大分析 183.41µs':f'正常最大分析 {analysis:.2f}µs',
        '四路扫描 CDF 与快照':'八路扫描 CDF 与快照',
        '第四阶段参数化候选会显式区分这些字段；新字段尚未通过整套板测前，不能将它们描述为已部署能力。':
            '接口现已显式区分采样、FFT 和时间戳频率，并提供只读构建 ID 与安全跨域计数快照。RTL、通用向量/参考、主机和 SD 分析使用当前构建配置；固定 100 MSPS 的历史黄金夹具保留作为兼容参考。构建工具拒绝未验证的其他物理时钟组合。',
        '当前双 bank 每个 bank 分为四组，扫描每拍读取四个 bin，流水计算前缀和和 CDF。':
            '当前双 bank 每个 bank 分为八组，扫描每拍读取八个 bin，以 2/4/8 点平衡前缀流水计算 CDF。宽数据寄存器由有效标志保护，无需数据复位；控制、状态与有效标志仍复位。扫描中断复位后不得输出旧结果，已有专门测试。',
        '当前正常最大分析/发布为 183.41/183.75µs':f'当前正常最大分析/发布为 {analysis:.2f}/{publish:.2f}µs',
        '当前四路扫描实现：setup=0.542ns、hold=0.016ns，LUT12866、FF20685、BRAM92.5/140、DSP53。历史双路扫描、当前四路扫描和第四阶段八路扫描候选分别保留报告。八路理论只减少扫描段约 8.192µs，必须重新测量系统总延迟。':
            f"当前八路组合实现：setup={h['setup_slack_ns']:.3f}ns、hold={h['hold_slack_ns']:.3f}ns，LUT{resources['lut']:g}、FF{resources['ff']:g}、BRAM{resources['bram36']:g}/140、DSP{resources['dsp']:g}。原四路为 183.41µs、LUT12866、FF20685、BRAM92.5、DSP53；系统最大分析延迟实测改善 {183.41-analysis:.2f}µs。没有将扫描段加速称为整体延迟减半。",
        '持续验收完成状态以原始报告为准。':'该组另完成 460 秒持续回放，最终组合版本对同一冻结输入复测通过。',
        '所有新宽带结果是对同一 100 MSPS 电路的输入覆盖扩展，未通过改元数据或频轴缩放制造提升。详见[已完成实验报告](第四阶段已完成实验报告.md)、[初始持续矩阵](../captures/phase4_ofdm_20260922/continuous/measurement_validation.json)与[次级有限矩阵](../captures/phase4_ofdm_widest_20260922/finite/measurement_validation.json)。':
            f'最终组合版本完成 {m["matrix_cases"]} 组矩阵、{m["legacy_check_cases"]} 组矩阵前兼容检查和 36 项基础板测，OFDM 持续测试共 920 秒。全部正式性能来自同一构建，未改元数据或频轴缩放制造提升。详见[完整验收报告](第四阶段完整验收报告.md)、[测量汇总](phase4_final_measurements.json)与[次级有限矩阵](../captures/phase4_final_20260922/widest_finite/measurement_validation.json)。'
    }
    for old,new in replacements.items():
        assert text.count(old)==1,'Unexpected design document text: '+old[:35]
        text=text.replace(old,new)
    p.write_text(text,encoding='utf-8')
    readme=f'''# Zybo Z7 数字 I/Q 频谱分析仪

I/Q 各 16bit，100 MSPS 板内回放，8192 点 AMD FFT，八路完整功率谱扫描。

第四阶段组合版本已完成完整仿真、真板矩阵、实际 GUI、匹配 SD 镜像和此次物理冷启动验收。最大 PL 分析/发布延迟为 **{analysis:.2f}/{publish:.2f} µs**；指定 OFDM 的有效内部窗最小 99% 占用带宽为 **{width:.6f} MHz**。接口版本 `0x00010002`，构建 ID `{identity}`。

电脑先装载 IQ 文件，PL 随后按每拍一对 IQ 连续处理；该速率不代表网络持续上传速率。项目没有外部 ADC 或任意通信协议帧解析，谱峰不等同于宽带调制载频。

## 从这里开始

- [完整验收报告](reports/第四阶段完整验收报告.md)：结果、未晋升实验和比赛要求对照。
- [电路设计说明](reports/最终电路设计说明.md)：架构、定点表示、跨域和测量语义。
- [完整测量清单](reports/phase4_final_measurements.json)：{m['matrix_cases']} 组矩阵及原始证据散列。
- [冷启动验证](reports/冷启动验证报告.md)：本次安装后的实际断电重启验收。
- [答辩稿](reports/答辩材料/数字IQ分析器_答辩稿.pptx)、[讲稿与预计提问](reports/答辩材料/讲稿与预计提问.md)。
- [寄存器和吞吐计数](docs/phase4_registers.md)、[帧长度误差分析](reports/帧长度定义与误差分析.md)。
- [第四阶段方案](第四阶段优化实施方案.md)、[时钟可行性结论](reports/第四阶段时钟可行性结论.md)、[第三方声明](THIRD_PARTY_NOTICES.md)。

## 运行

已有 Python 环境可安装 `requirements.txt` 中依赖。板卡启动网络固件后，从工程根目录运行：

```powershell
python scripts/phase4_demo.py
```

菜单提供零背景测长、5 dB robust、单音峰频和最宽 OFDM 四个冻结预设。普通监视器仍可双击 `Open_IQ_Monitor.cmd` 打开。每次采集使用新目录，GUI 与命令行只保留一个控制端。

```powershell
python host/iq_client.py capture --board 192.168.1.10 --vector data/vectors/burst_fs4.bin --window hann --detector digital-zero --out captures/example_run
```

默认板卡 IP 为 `192.168.1.10`，电脑直连网卡为 `192.168.1.20/24`。程序不擅自修改电脑网络配置。IQ 文件按小端交错 I16/Q16 保存；最多 32768 对，每次处理完整 8192 点窗口。

带噪输入的前 1024 点确认为静默背景时，才可使用 robust 档：

```powershell
python host/iq_client.py capture --vector data/phase4_demo/robust_snr5_120000.bin --out captures/robust_example --window hann --threshold-profile robust
```

该档位以 16 点能量、ton=ceil(16×3×背景均方功率)、toff=ceil(16×1.75×背景均方功率)、kon/koff=16/8 工作，门限下限为 2/1。默认命令保留 legacy 固定门限。0 dB、显著变化的背景和大 DC 偏置不属于通用保证。

## 启动与重建

完整交付包中 `boot_packages/ethernet_sd_card/` 用于网络交互，`boot_packages/sd_card/` 用于 16 项自动 SD 测试；每次只选一套 BOOT.BIN。当前已安装正确网络镜像时无需重新写卡。USB/JTAG、网线与供电保持连接，SD 启动跳线按板上标注设置。

重建使用 Vivado/Vitis 2026.1，默认安装路径在 `scripts/run.ps1` 参数中，可显式覆盖。运行构建前会生成并校验构建配置；当前仅允许已验证的 100/125 MHz 时钟组合。

```powershell
.\\scripts\\run.ps1 -Action All
```

新构建不会自动获得旧实板或冷启动的验收资格。每次修改硬件/固件须重新建立部署与原始采集证据，再考虑 SD 安装。[板上 SD 维护说明](scripts/maintenance/操作说明.md)给出操作入口。

## 交付核验与历史证据

解压最终包后可运行 `python scripts/verify_delivery.py .` 核验所有文件 SHA-256。原始记录为 `frequency.bin`、`burst.bin` 和元数据；重复的逐条 JSON/CSV 可重新导出。

历史报告保留当时本机绝对路径，包内文件清单给出可移植相对路径。旧四路实测与未晋升实验在独立归档中保留；它们不替代当前组合版本证据。第三阶段完整 ZIP 保持不变。本轮生成新的本地第四阶段完整包，未发布新的远端版本。

建立/保持时间裕量为 {h['setup_slack_ns']:.3f}/{h['hold_slack_ns']:.3f} ns，BRAM 占用 {resources['bram36']/140*100:.2f}%。125 MSPS 实验未晋升，当前正式输入为 100 MSPS。
'''
    (ROOT/'README.md').write_text(readme,encoding='utf-8')
    version=json.loads((ROOT/'VERSION.json').read_text())
    version.update(name='phase4-20260922-local',published=False,git_tag=None,hardware_version='0x00010002',
        build_id=identity,development_branch='optimization/phase4-competition-performance',
        validation_status_document='reports/第四阶段完整验收报告.md',optimization_plan='第四阶段优化实施方案.md')
    (ROOT/'VERSION.json').write_text(json.dumps(version,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    p=ROOT/'CHANGELOG.md';old=p.read_text(encoding='utf-8')
    p.write_text(f'# 第四阶段（2026-09-22，本地验收）\n\n八路谱扫描与构建身份/跨域吞吐计数完成组合验收。最大分析 {analysis:.2f} µs，指定 OFDM 最小内部窗带宽 {width:.6f} MHz。原 1653 组与新增 367 组矩阵、SD 及物理冷启动通过；125 MSPS 实验未晋升。\n\n'+old,encoding='utf-8')
    p=ROOT/'docs/phase4_registers.md';t=p.read_text(encoding='utf-8')
    t=t.replace('本文描述接口版本 `0x00010002` 的候选及后续已验收组合实现。是否已经晋升，以 `reports/current_board_validation.json` 和最终交付报告为准。',
                '本文描述已验收第四阶段组合版本的 `0x00010002` 接口，当前为八路谱扫描。对应构建与原始记录见完整验收报告。')
    t=t.replace('谱扫描并行 bin 数，隔离兼容候选为 4、组合候选为 8','谱扫描并行 bin 数，当前为 8；历史隔离兼容候选为 4')
    p.write_text(t,encoding='utf-8')
    p=ROOT/'reports/答辩材料/讲稿与预计提问.md';t=p.read_text(encoding='utf-8')
    t=t.replace('次级 98.14453125 MHz 设计跨度档，在原四路版本的内部窗最小实测为 96.997070 MHz。正式交付应引用组合版本复测结果。',
                f'次级 98.14453125 MHz 设计跨度档，在本次组合版本完整回归中，内部窗最小实测为 {width:.6f} MHz。')
    t=t.replace('原四路版本最大分析为 183.41 微秒，隔离八路候选基础板测为 175.23 微秒，节省主要来自频谱扫描段。最终声明要用组合版本完整矩阵的最大值，不能混用不同镜像的最优成绩。',
                f'原四路版本最大分析为 183.41 微秒，本次八路组合版本完整验收最大分析为 {analysis:.2f} 微秒、最大发布为 {publish:.2f} 微秒，改善 {183.41-analysis:.2f} 微秒，主要来自频谱扫描段。全部正式成绩对应同一个构建 ID。')
    t=t.replace('最终正式镜像要求 SD 写入读回、复位启动以及用户实际断电上电后纯网口验收。是否已完成以当前版本冷启动报告为准。',
                '本次镜像已完成 SD 写入读回、复位启动，以及用户实际断电上电后的纯网口验收。启动不需要电脑重新下载；证据见冷启动报告。')
    t += '\n当前依据：[完整验收报告](../第四阶段完整验收报告.md)、[逐项测量与原始证据](../phase4_final_measurements.json)、[冷启动报告](../冷启动验证报告.md)。\n'
    p.write_text(t,encoding='utf-8')
    print('PHASE4_CURRENT_DOCUMENTS_UPDATED')

if __name__=='__main__':main()
