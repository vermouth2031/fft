# Phase 12 GitHub 版本说明

本版本把数字 IQ 板内处理速率由 125 提升至 150 MSPS，在保持 I/Q 各 16 bit、16384 点 FFT、BRAM 128 和 DSP 49 的情况下，同口径满带 OFDM 主组 99% 占用带宽由 123.558044～123.901367 MHz 提升至 148.269653～148.681641 MHz。最大分析时间由 278.448 降至 234.426667 µs，最大结果发布时间为 234.660000 µs。

- 本地工程：`D:/fft/fft_phase12_wideband_150m`
- 开发分支：`phase12/wideband-150m`
- 本地已验收实现提交：`1a4a5d9d2e369eb7714f9c996228523c63d84d57`；尚未推送。
- 基线实现与版本登记：`162250cac5f53dce8e46875858307158f4941c1d`，Phase11 分支保留。
- 硬件 build ID：`444262675c923ecdf987042ee08f3da0`
- 网络启动文件 SHA-256：`2fbc3840b6df16408e66b4d7b80eb1d65a57cd7b033410c740c3b3357560491d`
- 计划发布标签：`v2026.10.11-phase12-wideband150-usb-sd-validated`，当前已完成验收和发布准备，尚未上传。
- 本次真实断电冷启动通过：仅网口确认版本和 epoch=0，79 项数值检查及 300.016 秒最宽带连续运行通过。9595 次切换、2746788 条频域记录，DMA 错误、丢样、记录缺口和 UDP 丢包均为 0。断电后未下载、未 JTAG 操作、未软件复位。

最终时钟为输入/时间戳 150 MHz、FFT 150 MHz。180 MHz FFT 的两次候选时序失败且未部署，不能作为已实现指标。setup/hold 为 +0.097/+0.010 ns；LUT 22765、FF 28377、BRAM 128、DSP 49、MMCM 1、BUFG 4。LUT/FF 相比基线增加约 0.64%/2.14%；频率格宽由 7.62939453125 增至 9.1552734375 kHz。

RAM/JTAG 验收包括完整 1048576 个 FFT 复数输出精确比对、79 项真板数值测试及 80896 个快照值、272 项宽带矩阵、1000 次 DMA 切换/故障注入及 60/300 秒最宽带连续运行。300 秒测试完成 9393 次切换、2746839 条频域记录，DMA 错误、丢样、序号缺口和 UDP 丢包均为 0。宽带以 99% 功率、两端各排除 0.5% 的方法定义；赛题未指定该算法或数值容差。

SD 上旧 Phase11 启动镜像保留为 `B5EDFF26.BIN`，此前 Phase10 备份 `B2F71552.BIN` 未修改。首次 SD 挂载失败发生在任何文件写入之前；相同产物重新初始化后安装成功。记录保留，不把未确认的瞬态问题归因于供电或硬件缺陷。

150 MSPS 是 FPGA 回放 Bank 的消耗速率；主机通过网络填充 DDR，再用 DMA 装载非活动 Bank。它不表示千兆网口持续供应 150 MSPS 的全新 IQ；尚未集成外部 ADC。原有低信噪比/短突发测量边界保留。

真实断电冷启动验收已通过，发布包包含以下附件：

| 用途 | 文件 |
|---|---|
| 网络固件启动镜像 | `ethernet_sd_card.zip`，内部为 `BOOT.BIN` |
| 轻量源码、脚本和数值输入 | `iq_analyzer_source.zip`，不含 reports/releases |
| 完整离线验收证据 | `phase12_sd_cold_boot_evidence.zip` |
| 产物与版本散列 | `manifest.json`、`SHA256SUMS.txt` |
| 独立验收清单 | `phase12_acceptance.json`、`phase12_boot_acceptance.json` |

GitHub 的 Code → Download ZIP 是对应分支的源码快照，包含纳入 Git 的报告，不包含被忽略的本地 bitstream/ELF/BOOT 构建产物，也不包含 Git 历史。不能将源码 ZIP 当作 SD 启动镜像。

完整仓库或证据包支持离线验证：

```powershell
python scripts/verify_phase12_evidence.py
python scripts/verify_phase12_cold_boot.py
```

两条离线核查均已通过；冷启动证据限定为本次用户确认的物理断电及其后的网口测试。离线检查与 GitHub Actions 检查源文件和实测证据的散列对应关系；云端不会重新执行 Vivado 综合或真板测试。
