# Zybo Z7 数字 I/Q 频谱分析仪

在 Zybo Z7-20 上完成数字基带信号的幅度、突发长度、频点和 99% 占用带宽测量。

**处理规格：I/Q 各 16 位 · 100 MSPS · 8192 点 FFT · ARM + FPGA + 电脑客户端。**

当前版本 `0x00010001` 已通过双模式实板验收，实体SD已更新并验证复位启动。新增数字零背景测长，原门限模式继续保留。完整结果见[本轮优化验收报告](reports/本轮优化验收报告.md)。

电脑先装载 I/Q 文件，FPGA 从本地 RAM 高速回放并完成分析。FFT 使用 AMD IP；此工程不含外部 ADC。

## 从这里开始

- [当前验收状态](docs/验收状态.md)：新旧版本、实际通过的验证、待完成事项。
- [架构与开发指南](docs/架构与开发指南.md)：核心模块、数据路径、构建与验证。
- [使用与设计说明](docs/使用与设计说明.md)：操作、寄存器和测量定义。
- [演示操作卡](docs/演示操作卡.md)：连接现有板卡并运行演示。
- [赛题对照与实施方案](docs/赛题对照与后续实施方案.md)：已完成内容、实施步骤、验收门槛。
- [参赛技术报告](docs/参赛技术报告.md)：方案选择、算法、自研内容与演示材料。
- [第三方声明](THIRD_PARTY_NOTICES.md)：厂商 IP、驱动及板级定义的使用范围。

## 运行

已连接并启动网络固件的板卡：双击 `Open_IQ_Monitor.cmd`。
命令行示例：

```powershell
python host/iq_client.py capture --board 192.168.1.10 --vector data/vectors/qpsk_sps4.bin --window hann --out captures/example_run
```

每次使用新的采集目录；GUI 与命令行不要同时控制板卡。默认网络为电脑 `192.168.1.20/24`、板卡 `192.168.1.10`。

## 构建

Windows，Vivado/Vitis 2026.1，Python 3.12；本机工具路径在 `scripts/run.ps1` 中配置。

```powershell
.\scripts\run.ps1 -Action All
```

完整构建包含参考、RTL 仿真、布局布线、软件和启动包，可能耗时较长。
工具日志统一放在 `build/logs/`。时钟、FFT IP 配置修改后的重建规则见开发指南。

## 目录

| 目录 | 内容 |
|---|---|
| `rtl/`、`constraints/` | 核心电路与时序约束 |
| `firmware/`、`host/` | ARM 服务与电脑客户端 |
| `tests/`、`scripts/` | 参考模型、测试台、构建及验收 |
| `data/`、`vendor/` | 测试数据、板级定义和许可 |
| `docs/`、`reports/` | 维护文档与版本对应的验证证据 |

`build/`、`artifacts/`、`captures/`、`release/` 是本地生成目录，不进入源码 Git 历史。
旧基线实测资料统一索引在 `reports/baseline_20260917/`；不能据此宣称修改后的硬件已通过板测。
