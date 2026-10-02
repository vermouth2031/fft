> 当前正式版本为 Phase 7：电脑通过 UDP 动态更新非活动 IQ Bank，FPGA 同时以 125 MSPS 处理活动 Bank，并在 8192 点 FFT 边界切换。Phase 6 A2 正式版本和全部历史证据保持不变。

# Zybo Z7 数字 I/Q 频谱分析仪

I/Q 各 16bit，双 Bank 数字回放，板端 125 MSPS，8192 点 AMD FFT，八路完整功率谱扫描。

Phase 7 已完成完整仿真、真板数值矩阵、1000 次动态切换、10/60/300 秒流式稳定性、匹配 SD 镜像和物理冷启动验收。最大 PL 分析/发布延迟为 **141.976/142.256 us**；接口版本 `0x00010003`，构建 ID `326086439b6ef3b8e85d1980b6744969`，实现后 setup/hold 裕量为 **+0.057/+0.015 ns**。

Phase 7 允许电脑在 PL 处理 Bank A 时上传 Bank B。上传完成且 CRC32 正确后，PL 只在 FFT 窗口边界切换 Bank，因此一个 FFT 窗口不会混入两组信号。125 MSPS 是板内处理速率；I/Q 各 16 bit 对应 4 Gbit/s 原始数据，千兆网口不承载持续 125 MSPS 的不重复原始流。项目没有外部 ADC 或任意通信协议帧解析。

## 从这里开始

- [第七阶段完整验收报告](reports/第七阶段完整验收报告.md)：双 Bank 流式输入、构建、真板、稳定性、SD 和物理冷启动结论。
- [第七阶段冷启动验证报告](reports/第七阶段冷启动验证报告.md)：最终 SD 镜像断电再上电后的网络与数值验证。
- [第六阶段完整验收报告](reports/第六阶段完整验收报告.md)：125 MSPS A2 的构建、矩阵、GUI、带宽、SD 和冷启动结论。
- [第六阶段优化方案](reports/第六阶段优化方案.md)：本阶段目标、门槛和执行方案。
- [项目工程总结](项目工程总结.md)：从整体流程、单音例子到正式指标、操作方法和能力边界。
- [9月28日收尾验收](reports/closeout_20260928/收尾验收说明.md)：新版界面18项复测、4项实板数值核验及新版完整包的验证范围。
- [新版上位机使用说明](docs/新版上位机使用说明.md)：赛题四项测量卡片、指标对照、完整参数与数据入口，以及本次界面实板验证。
- [五组新信号测试与图解](reports/five_signals_20260923/测试报告.md)：单音、双音、扫频、QPSK、OFDM的10次真板结果及原始数据。
- [GitHub版本与证据维护](docs/GitHub维护说明.md)：开发分支、正式Release、自动检查和完整交付包的区别。
- [完整验收报告](reports/第四阶段完整验收报告.md)：结果、未晋升实验和比赛要求对照。
- [电路设计说明](reports/最终电路设计说明.md)：架构、定点表示、跨域和测量语义。
- [完整测量清单](reports/phase4_final_measurements.json)：2020 组矩阵及原始证据散列。
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

当前工作区上位机已改为四项结果卡片与四个标签页。2026-09-25 的独立界面回归通过 10 组历史记录显示、4 项真板采集及状态/兼容性检查；对应 [界面回归记录](reports/gui_redesign_20260925/gui_validation.json)。页首第四阶段完整验收描述的是冻结版本，原报告及发布包保留原状；本次界面回归不替代完整系统重新验收。

Phase 7 实时双 Bank 命令会轮换生成单音、双音、扫频、QPSK、OFDM 和噪声，并在上传下一块时接收当前块的分析记录：

```powershell
python host/streaming.py --board 192.168.1.10 --blocks 12 --samples 32768 --progress --out captures/streaming_demo
```

可用 `--signal single|dual|chirp|qpsk|ofdm|noise` 固定信号，或用 `--custom file.bin` 上传小端交错 I16/Q16 文件。每个 UDP 数据包和完整 Bank 都检查 CRC32；缺包、乱序、重复 offset 或 CRC 错误不会提交 Bank。

2026-09-28 对当前界面再次完成18项回归，4项真板采集全部通过独立数值核验、UDP缺包为0，结束后板卡空闲。新本地交付包 `release/phase4-closeout-20260928.zip` 包含冻结硬件证据、五类信号、新版界面及本次记录；具体源码提交和验证范围以包内 `manifest.json` 为准。

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
.\scripts\run.ps1 -Action All
```

新构建不会自动获得旧实板或冷启动的验收资格。每次修改硬件/固件须重新建立部署与原始采集证据，再考虑 SD 安装。[板上 SD 维护说明](scripts/maintenance/操作说明.md)给出操作入口。

## 交付核验与历史证据

GitHub源码仓库包含五组信号的小型完整证据，可运行 `python scripts/check_five_signals_archive.py` 离线核验。完整硬件回归中的 `captures/`、`build/` 及启动镜像随本地完整交付包保存；源码下载不包含这些全部产物。Phase 7 使用独立分支 `phase7/streaming-ping-pong` 和标签 `phase7-streaming-final-20261002`；Phase 6 A2 仍保留在 `phase6/125m-a2` 和 `phase6-a2-125m-final-20261002`，旧 Release 与标签均不改写。

解压最终包后可运行 `python scripts/verify_delivery.py .` 核验所有文件 SHA-256。原始记录为 `frequency.bin`、`burst.bin` 和元数据；重复的逐条 JSON/CSV 可重新导出。

历史报告保留当时本机绝对路径，包内文件清单给出可移植相对路径。旧四路实测与未晋升实验在独立归档中保留；它们不替代当前组合版本证据。第三阶段完整 ZIP 保持不变。本轮生成新的本地第四阶段完整包，未发布新的远端版本。

Phase 7 的建立/保持时间裕量为 0.057/0.015 ns。当前正式输入是电脑动态更新的双 Bank I16/Q16 回放，FPGA 以 125 MSPS 消费活动 Bank；外部 ADC 和通过千兆以太网持续传输 4 Gbit/s 不重复原始 IQ 仍不在本版本范围内。
