# Phase 11 GitHub 版本说明

本次归档 16384 点 FFT、150 MHz FFT 时钟优化及 USB 供电 SD 冷启动验证版本。输入保持 I/Q 各 16 bit、板内回放 125 MSPS；最大分析/发布延迟为 278.448/278.728 微秒。

- 工作目录：`D:\fft\fft_phase11_latency_opt`
- 分支：[phase11/latency-opt](https://github.com/vermouth2031/fft/tree/phase11/latency-opt)
- 固定发布：[v2026.10.10-phase11-fft150-usb-sd-validated](https://github.com/vermouth2031/fft/releases/tag/v2026.10.10-phase11-fft150-usb-sd-validated)
- 已验收实现提交：`dd453426866ecf5550bc690daaccc8871df837d8`
- 硬件 build ID：`9de00f7c8261de0723505e5e50040906`
- 启动文件 SHA-256：`462b1dde7437e9a9ce367d628d12c709ea9a37c4ef2febcc6109a97bb6c00b69`

标签固定源码、SD 安装与冷启动验收快照；分支随后可增加发布回执。此前的 Phase 10 发布与 main 保留。

| 用途 | 下载文件 |
|---|---|
| 已安装并通过冷启动验证的网络启动镜像 | `ethernet_sd_card.zip`，内部 `BOOT.BIN` |
| 源码与完整归档报告 | 分支 Code → Download ZIP，或标签自动生成的 Source code ZIP |
| 轻量源码、脚本和数值输入 | `iq_analyzer_source.zip`，不含 reports/release 归档 |
| 完整离线验收证据 | `phase11_sd_cold_boot_evidence.zip` |
| 文件校验和版本标识 | `SHA256SUMS.txt` 与 `manifest.json` |

源码包与启动镜像不同；Code → Download ZIP 不包含被忽略的构建产物，也不包含 Git 历史。

RAM/JTAG 验收包括 1048576 个 FFT 复数输出精确比对、79 项真板数值测试、1000 次 DMA 切换及 60/300 秒连续运行。用户确认实际断电再上电后，只通过网口验证，未使用 JTAG、未下载程序、未触发复位；冷启动后的 79 项数值测试、80896 个快照值及 60 秒连续运行全部通过。60 秒完成 1919 次切换，DMA 错误、丢样、UDP 丢包为 0。此前 300 秒结果属于 RAM/JTAG 验收，不能当作冷启动后的 300 秒测试。

LUT 22621、FF 27782、BRAM 128/140、DSP 49/220、MMCM 1/4。125 MSPS 是板内处理速率，不表示网口可持续提供同速率的全新 IQ；未集成外部 ADC。原有低信噪比和短突发测量边界保留。本次采用工程预发布标记。

在完整仓库或完整证据包根目录执行：

```powershell
python scripts/verify_phase11_cold_boot.py
```

该命令离线核查源代码、SD 读回和实测归档的散列绑定，不连接开发板。GitHub Actions 执行主机测试与证据核查，不代表云端重新进行了 FPGA 综合或实板测试。

在保留构建产物的原工程重新打包：`python scripts/package_phase11_cold_boot.py`。发布附件位于 `release/phase11_sd_verified`；已发布附件保持冻结，重新生成的 ZIP 可能具有不同的文件散列。
