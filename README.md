# Zybo Z7 数字 I/Q 频谱分析仪

I/Q 各 16bit，100 MSPS 板内回放，8192 点 AMD FFT，八路完整功率谱扫描。

第四阶段组合版本已完成完整仿真、真板矩阵、实际 GUI、匹配 SD 镜像和此次物理冷启动验收。最大 PL 分析/发布延迟为 **175.23/175.57 µs**；指定 OFDM 的有效内部窗最小 99% 占用带宽为 **96.997070 MHz**。接口版本 `0x00010002`，构建 ID `3bc7d0840b0602203141e9ee228e80e3`。

电脑先装载 IQ 文件，PL 随后按每拍一对 IQ 连续处理；该速率不代表网络持续上传速率。项目没有外部 ADC 或任意通信协议帧解析，谱峰不等同于宽带调制载频。

## 从这里开始

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

解压最终包后可运行 `python scripts/verify_delivery.py .` 核验所有文件 SHA-256。原始记录为 `frequency.bin`、`burst.bin` 和元数据；重复的逐条 JSON/CSV 可重新导出。

历史报告保留当时本机绝对路径，包内文件清单给出可移植相对路径。旧四路实测与未晋升实验在独立归档中保留；它们不替代当前组合版本证据。第三阶段完整 ZIP 保持不变。本轮生成新的本地第四阶段完整包，未发布新的远端版本。

建立/保持时间裕量为 0.199/0.016 ns，BRAM 占用 66.07%。125 MSPS 实验未晋升，当前正式输入为 100 MSPS。
