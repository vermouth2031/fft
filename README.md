# Zybo Z7-20 数字 I/Q 信号分析仪

版本：**2023\9\17**（Git 标签 `2023-09-17`）。这是用户指定的版本名称；实际板测日期为 2026-09-17。

Git 仓库保存源码、构建脚本、测试向量和验收报告。预编译 BOOT.BIN、位流/XSA/ELF 和原始实板数据通过 GitHub Release 附件提供；下载后按附件说明解压到工程目录。Vivado 构建缓存、完整本地采集目录及电脑设备配置不进入 Git 历史。云端 CI 仅检查 Python 语法及主机协议，不代替 Vivado 或实板验收。

这是赛道 2 项目的可构建源码工程：16 bit I + 16 bit Q、100 MSPS 连续回放、8192 点 FFT、幅度 / 突发长度 / 峰值频率 / 99% 占用带宽测量。

**硬件目标：Zybo Z7-20，XC7Z020-1。工具：Vivado / Vitis 2026.1。2026-09-17 已完成 SD、以太网 60 秒连续采集、突发压力、断网恢复和图形界面实板验证。**

## 先看这些文件

- [使用与设计说明](docs/使用与设计说明.md)：操作步骤、结果含义、接口和限制。
- [项目状态](PROJECT_STATUS.md)：实际完成项及未完成项。
- [最终验收与交付说明](reports/最终验收与交付说明.md)：实测证据、演示入口及验收边界。
- [演示操作卡](docs/演示操作卡.md)：使用当前 SD 卡和图形界面演示。
- `reports/core_validation.json`：FFT 位精确及测量结果检查。
- `reports/timing_summary.rpt`：布局布线后的时序，以最新成功构建为准。
- `artifacts/`：通过构建检查后导出的 bit、XSA、ELF、BOOT.BIN。
- `release/sd_card/`：供现有 32 GB FAT32 SD 卡使用的自动测试包，复制内容到根目录即可。
- `release/ethernet_sd_card/`：以太网交互启动包。
- `release/manifest.json`：软件与 XSA 对应关系、验证结果、交付物和源码散列。
- `host/monitor.py`：电脑图形界面，支持以太网采集及离线读取硬件结果。

## 工程目录

| 目录 | 内容 |
|---|---|
| `rtl` | 可综合 SystemVerilog，不含测试平台 |
| `constraints` | 跨时钟约束 |
| `scripts` | Vivado/Vitis 构建、JTAG 下载与采集 |
| `tests` | 位精确参考、RTL 测试平台、结果验证 |
| `data` | Hann 系数和自动生成的测试 / 参考数据 |
| `firmware` | Cortex-A9 以太网控制和结果发送代码 |
| `host` | 电脑采集、二进制解码、CSV / JSON / Markdown 导出 |
| `vendor/boards` | 保留 MIT 声明的 Digilent 官方板级定义 |
| `build` | 自动生成工程、AMD 模型和本地软件兼容补丁，可重建 |
| `reports` | 验证结果、时序和资源报告 |

## 关键入口

在 PowerShell 中：

```powershell
Set-Location D:\fft\iq_analyzer
# 离线完整构建与回归，实际耗时取决于电脑；FFT 仿真可能需要数十分钟。
.\scripts\run.ps1 -Action All
# 查看 FPGA 工程：
& 'D:\VivadoMM\2026.1\Vivado\bin\vivado.bat' .\build\board\iq_board.xpr
```

板卡接好后，可先用 **JTAG 有限长度回放** 验证，不需要网线或额外 ADC；再用以太网做连续采集。具体命令见使用说明。

也可以优先用已有 SD 卡执行 16 个有限采集测试，然后将 `RUN0000` 目录交给 `host/analyze_sd.py` 自动核对。默认 `artifacts/BOOT.BIN` 是 SD 自动测试程序，网络程序使用 `BOOT_udp.BIN`。

## 验证范围

核心完整回归包含：零输入、正 / 负单音、完整突发、两种 QPSK 带宽、跨窗口短突发、I/Q 同时为负满幅；每类分别用矩形窗和 Hann 窗。FFT 输出与安装包中的 AMD 位精确 C 模型比较，时间测量与独立整数参考比较。

仿真通过不能替代上板测试；生成 bit 文件也不能代替时序通过。工程分别检查这三件事。
