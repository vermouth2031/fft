# Phase 11：分析延迟优化候选

当前候选尚在验证，状态见 [PHASE11_STATUS.md](PHASE11_STATUS.md)。下方 Phase 10 为历史基线说明，不代表本阶段已经验收。

# Phase 10：16K FFT 资源优化及 USB 连续传输修复

当前版本 `b162c5a41c3560519de11c7e90e379a7`：输入 FIFO 恢复 BRAM，保留共享 PSD 与 Hann ROM 优化。LUT 31562→22775，LUTRAM 14667→5740，BRAM 130→128；FFT 16384 点、125 MSPS、精度和容量保持。最终 bit/ELF 已在 USB 供电下通过 1000 次切换、60/300 秒连续测试、1048576 点 RTL 精确回归及 79 项真板数值验收。当前状态和资源取舍见 [PHASE10_STATUS.md](PHASE10_STATUS.md)。修复版已安装到 SD，用户实际断电重启后自动加载成功；冷启动后的 79 项数值检查、1000 次切换和 300 秒连续传输全部通过，以后正常上电即可运行，无需 JTAG 下载。

GitHub 当前版本：[`phase10/resource-opt`](https://github.com/vermouth2031/fft/tree/phase10/resource-opt)。已验证实现固定在提交 `290e7cd`，启动镜像与离线证据见 [Phase 10 下载页面](https://github.com/vermouth2031/fft/releases/tag/v2026.10.09-phase10-resource-opt-usb-sd-validated)。下载方式、标签与分支的关系见 [Phase 10 GitHub 版本说明](docs/Phase10_GitHub版本说明.md)。后续提频方案尚未实现，不属于本版本指标。

下面的 Phase 9 接口与使用说明作为沿用的基线资料保留；当前版本的验收结论以 Phase 10 状态和对应散列报告为准。

# Zybo Z7 数字 I/Q 频谱分析仪 · Phase 9

本目录是 `phase9/fft16k` 分支的 16384 点 FFT 优化工程，基于 Phase 8 r17。当前验收状态见 [PHASE9_STATUS.md](PHASE9_STATUS.md)。历史报告与旧发布包不能证明当前候选已经通过实板或冷启动验收。

I/Q 各 16 bit，板内采样和 FFT 时钟均为 125 MHz，16384 点 AMD FFT，八路完整精度功率谱扫描。FFT 数据/旋转因子为 24/18 bit，PSD 为 48 bit，总功率为 64 bit。频率栅格为 7.62939453125 kHz，单窗采集时间为 131.072 µs。

电脑通过 UDP 把 IQ 写入 PS DDR，AXI DMA 填充非活动 PL Bank；FPGA 同时处理活动 Bank，并在完整 FFT 窗口边界切换。两个 Bank 各保留 32768 对 I16/Q16。125 MSPS 是板内处理速率；千兆网口不能持续提供 4 Gbit/s 的不重复原始 IQ。当前输入为数字回放，未集成外部 ADC。

## 运行

安装 `requirements.txt` 中的 Python 依赖。确认板卡运行与本版本匹配的网络固件后，双击 `Open_IQ_Monitor.cmd`，或运行：

```powershell
python host/iq_client.py capture --board 192.168.1.10 --vector data/replay_vectors/burst_fs4.bin --window hann --detector digital-zero --out captures/phase9_example
python host/streaming.py --board 192.168.1.10 --blocks 12 --samples 32768 --progress --out captures/phase9_streaming
```

默认板卡 IP 为 `192.168.1.10`，直连电脑为 `192.168.1.20/24`。GUI 与命令行同时只保留一个控制端，每次采集使用新输出目录。当前回放文件必须包含 16384 或 32768 对小端交错 I16/Q16。

`data/replay_vectors` 是可直接上板的 32768 对样本；`data/vectors` 包含供核心回归使用的连续四窗（65536 对），不能直接装入一个物理 Bank。旧 Phase 4 冻结演示工具及其固定长度预设属于历史版本，不作为本版本操作入口。

流式信号可选 `single|dual|chirp|qpsk|ofdm|noise`，也可用 `--custom file.bin`。每包、整块及 PL 写入端均检查 CRC；错误长度、TKEEP、TLAST 或 CRC 不会产生可切换的 ready Bank。

数字零检测与门限检测仍按样本连续运行。扩大 FFT 不改变检测算法；0 dB 噪声下的漏检问题不能视为已修复。

## 构建与验证

使用 Vivado/Vitis 2026.1，安装路径可通过脚本参数覆盖：

```powershell
.\scripts\run.ps1 -Action All
```

当前 FFT 工程为 `build/vivado16k`。构建流程生成点数/缩放/容量配置，运行 RTL 和 Python 回归，检查布局布线时序与 CDC，构建固件并生成启动包。核心回归覆盖 64 窗、1048576 个复数点，逐点比对 AMD bit-accurate C model。

Phase 9 实板矩阵入口为 `tests/phase9_specs.py` 和 `scripts/phase9_board_validation.py`。使用当前参考索引运行验收，不能沿用旧 8K 报告。验收范围包括频域、时域、快照、样本守恒、延迟以及 DDR/DMA 连续切换。

生成的 `release/ethernet_sd_card/BOOT.BIN` 用于网络固件，`release/sd_card/` 用于 SD 自动采集。构建脚本不写物理 SD 卡。RAM/JTAG 加载通过 `scripts/program_board.tcl`，不等同于物理断电冷启动验证。当前版本最终安装与冷启动状态以 [PHASE10_STATUS.md](PHASE10_STATUS.md) 为准。

## 历史与接口资料

- [变更记录](CHANGELOG.md)、[版本元数据](VERSION.json)、[GitHub维护说明](docs/GitHub维护说明.md)。
- [第八阶段完整验收报告](reports/第八阶段完整验收报告.md)、[第八阶段冷启动验证](reports/第八阶段冷启动验证报告.md)。
- [第七阶段完整验收报告](reports/第七阶段完整验收报告.md)、[第六阶段完整验收报告](reports/第六阶段完整验收报告.md)。
- [寄存器和吞吐计数](docs/phase4_registers.md)、[帧长度误差分析](reports/帧长度定义与误差分析.md)。Phase 9 新容量寄存器见当前状态文档。
- [电路设计说明](reports/最终电路设计说明.md)、[第三方声明](THIRD_PARTY_NOTICES.md)。

历史报告中的路径、硬件 ID、点数和验收结果仅对当时版本有效。当前构建与验证证据通过 SHA-256 绑定对应源码和产物。
