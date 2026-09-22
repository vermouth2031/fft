# Zybo Z7 数字 I/Q 频谱分析仪

在 Zybo Z7-20 上完成数字基带信号的幅度、突发长度、频点和 99% 占用带宽测量。

**处理规格：I/Q 各 16 位 · 100 MSPS · 8192 点 FFT · ARM + FPGA + 电脑客户端。**

当前工作分支已实现第三阶段四路频谱扫描、FFT高扇出复制和robust门限档位。完整仿真、时序、SD测试固件、36组基础网络板测和1653组扩展矩阵已通过；扩展矩阵含2690693条频域记录、674991条突发记录。新镜像的实体SD读回、复位启动和用户确认断电上电后的纯网口验收均已通过，见[第三阶段完整验收报告](reports/第三阶段完整验收报告.md)。接口版本沿用 `0x00010001`。

最大分析延迟由199.79µs降至183.41µs，setup/hold裕量为0.542/0.016ns。5dB独立输入的正常测长为496/500（99.2%）；同一历史输入由71/100改善到97/100。robust要求有效静默前导和近似平稳背景，0dB不在合格范围内。

电脑先装载 I/Q 文件，FPGA 从本地 RAM 高速回放并完成分析。FFT 使用 AMD IP；此工程不含外部 ADC。

## 从这里开始

- [第三阶段完整验收报告](reports/第三阶段完整验收报告.md)：当前版本的数值、时序、资源、完整实板测试及启动状态。
- [前阶段双模式验收报告](reports/本轮优化验收报告.md)：历史基线；不能用旧启动证据证明新镜像。
- [冷启动验证报告](reports/冷启动验证报告.md)：用户确认断电上电后的版本与实测结果。
- [帧长度误差分析](reports/帧长度定义与误差分析.md)：两种检测模式的测量定义与误差。
- [第二阶段优化方案](第二阶段优化实施方案.md)：误差、噪声、带宽与性能优化的分阶段要求。
- [第二阶段测量与性能报告](reports/第二阶段测量与性能报告.md)：S0 基线、S1 参考接口与首批有限测量；后续阶段单独验收。
- [第二阶段完整验收报告](reports/第二阶段完整验收报告.md)：S1～S3 共 466 组新增实板测试，约 81～82MHz 最宽档及 60 秒连续验证。
- [性能优化决策](reports/第二阶段性能优化决策.md)：两次时序实验、延迟分解，以及四点扫描和可选 125MSPS 的实施边界。
- [第三阶段优化方案](第三阶段优化实施方案.md)：带噪门限、正式主机配置、高扇出复制、四路扫描及晋升条件。
- [第三阶段条件性优化决策](reports/第三阶段条件性优化决策.md)：DC、能量窗、噪声变化、Realtime FFT和125MSPS的实际研究与适用边界。
- [参赛演示提纲](reports/参赛演示提纲.md)：硬指标、适用范围、原理框图和演示流程。
- [第三方声明](THIRD_PARTY_NOTICES.md)：厂商 IP、驱动及板级定义的使用范围。

## GitHub 版本与下载

GitHub已发布版本：**v2026.09.20**，硬件接口版本 `0x00010001`。该发布包含前阶段双模式优化、完整实板与冷启动后验证。本工作分支为第三阶段本地版本 `phase3-20260922-local`，尚未发布新的GitHub版本。原冻结包 `release/phase2-complete-20260921.zip` 保留；本轮独立完整包使用 `release/phase3-complete-20260922.zip`，只在新镜像物理冷启动验收通过后生成。

- [GitHub 仓库](https://github.com/vermouth2031/fft)
- [本版 Release](https://github.com/vermouth2031/fft/releases/tag/v2026.09.20)：下载完整工程交付包和SHA-256清单。
- 旧标签 `2023-09-17` 保留；其显示名称 `2023\9\17` 是用户指定标识，实际验证日期为2026-09-17。
- 代码、验收报告及第二阶段方案进入Git；bit/XSA/ELF/BOOT、原始采集等由Release附件提供。
- 用户已选择删除旧docs文档；如需查阅，可在旧提交中查看。

## 运行

已连接并启动网络固件的板卡：双击 `Open_IQ_Monitor.cmd`。
命令行示例：

```powershell
python host/iq_client.py capture --board 192.168.1.10 --vector data/vectors/qpsk_sps4.bin --window hann --out captures/example_run
```

每次使用新的采集目录；GUI 与命令行不要同时控制板卡。默认网络为电脑 `192.168.1.20/24`、板卡 `192.168.1.10`。

带噪输入且前1024点**确认为背景静默区**时，可选择 `robust` 档位。完整第三阶段交付包中的实测向量示例：

```powershell
python host/iq_client.py capture --vector build/phase3_final_20260921/validation/vectors/robust_snr5_120000.bin --out captures/robust_example --window hann --threshold-profile robust
```

该档位使用16点能量窗，ton=ceil(16×3×背景均方功率)、toff=ceil(16×1.75×背景均方功率)、kon/koff=16/8。自动估计保留最小ton/toff=2/1，确保全零背景时严格关断条件仍可满足。`--quiet-samples`可指定已知静默前导长度。默认命令仍采用原固定门限；人工配置使用成对的 `--ton`、`--toff`，以及可选 `--kon`、`--koff`。GUI提供相同控件，采集记录保存请求、估计和实际生效值，START前校验硬件读回。

静默前导并非自动识别。没有可靠静默区、较大DC偏置、显著变化的噪声或0dB输入不能直接套用robust的验收结论；数字零模式不接受门限档位选项。新旧参数均不等于通信协议帧识别。

## 首次连接与启动

1. 安装Python依赖：`python -m pip install -r requirements.txt`。已有环境可直接使用。
2. 使用Release完整包中的 `boot_packages/ethernet_sd_card/` 进行电脑交互；把其内容放入FAT32 SD卡根目录。自动SD测试使用另一套 `boot_packages/sd_card/`，两套BOOT.BIN不能混用。
3. 断电插卡，JP5选择板上标注SD的位置，JP6保持与实际供电方式一致；接上USB JTAG/UART、网线和电源后打开SW4。
4. 默认电脑网卡192.168.1.20/24，板卡192.168.1.10。UART可选115200、8N1、无流控；完整结果通过网口传输。
5. 打开上位机，选择 `data/vectors/burst_fs4.bin`、Hann窗、digital-zero模式、gap_min=32，取消循环回放并开始采集。参考结果为24576点/245.76µs。

当前卡已安装网络启动程序时，不需要再次复制文件或启动Vivado。板内波形回放100MSPS不等于电脑经网口持续传入400MB/s新数据。

## 验证与维护

- 原完整板测：`scripts/run_network_validation.ps1 -Suite full`；要求当前部署与构建身份匹配。
- 单次记录数值核验：`python scripts/verify_board_capture.py captures/你的采集目录`；现有校验器支持固定黄金向量，不能对任意输入假定有效。
- 解压完整交付后校验：`python scripts/verify_delivery.py .`。
- [板上SD维护说明](scripts/maintenance/操作说明.md)：在板写入、读回与SD自动测试导出。
- 本轮基础板测及全部扩展矩阵最大分析延迟183.41µs、最大发布延迟183.75µs；setup/hold裕量0.542/0.016ns。数字零模式仅适用于精确零背景，协议帧同步、125MSPS及外部ADC不属于已实现功能。

## 构建

Windows，Vivado/Vitis 2026.1，Python 3.12；本机工具路径在 `scripts/run.ps1` 中配置。

```powershell
.\scripts\run.ps1 -Action All
```

完整构建包含参考、RTL 仿真、布局布线、软件和启动包，可能耗时较长。
工具日志统一放在 `build/logs/`。时钟或FFT IP配置改变时，先显式运行 `scripts/create_fft.tcl`，再重建板级工程及全部参考、仿真、软件和BOOT；不要依赖已有工程的增量构建自动更新IP。

## 目录

| 目录 | 内容 |
|---|---|
| `rtl/`、`constraints/` | 核心电路与时序约束 |
| `firmware/`、`host/` | ARM 服务与电脑客户端 |
| `tests/`、`scripts/` | 参考模型、测试台、构建及验收 |
| `data/`、`vendor/` | 测试数据、板级定义和许可 |
| `reports/` | 当前验收报告、原始文件索引及历史证据 |

`build/`、`artifacts/`、`captures/`、`release/` 是本地生成目录，不进入源码 Git 历史。
旧基线实测资料统一索引在 `reports/baseline_20260917/`；不能据此宣称修改后的硬件已通过板测。
