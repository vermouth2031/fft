# Zybo Z7 数字 I/Q 频谱分析仪

在 Zybo Z7-20 上完成数字基带信号的幅度、突发长度、频点和 99% 占用带宽测量。

**处理规格：I/Q 各 16 位 · 100 MSPS · 8192 点 FFT · ARM + FPGA + 电脑客户端。**

当前版本 `0x00010001` 已通过双模式实板验收，实体SD已更新，并通过复位启动及用户确认断电上电后的数值采集验证。新增数字零背景测长，原门限模式继续保留。完整结果见[本轮优化验收报告](reports/本轮优化验收报告.md)。

电脑先装载 I/Q 文件，FPGA 从本地 RAM 高速回放并完成分析。FFT 使用 AMD IP；此工程不含外部 ADC。

## 从这里开始

- [本轮优化验收报告](reports/本轮优化验收报告.md)：数值、时序、资源及完整实板测试。
- [冷启动验证报告](reports/冷启动验证报告.md)：用户确认断电上电后的版本与实测结果。
- [帧长度误差分析](reports/帧长度定义与误差分析.md)：两种检测模式的测量定义与误差。
- [第二阶段优化方案](第二阶段优化实施方案.md)：待实施的误差、噪声、带宽与性能优化。
- [第三方声明](THIRD_PARTY_NOTICES.md)：厂商 IP、驱动及板级定义的使用范围。

## GitHub 版本与下载

当前发布：**v2026.09.20**，硬件版本 `0x00010001`。本版纳入双模式优化、完整实板与冷启动后验证，以及第二阶段方案；方案中的后续目标尚未实现。

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
- 标称最大分析延迟199.79µs；当前setup/hold裕量0.030/0.004ns。数字零模式仅适用于精确零背景，协议帧同步、125MSPS及外部ADC不属于已实现功能。

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
