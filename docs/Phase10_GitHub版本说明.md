# Phase 10 GitHub 版本说明

当前已完成项目为 16K FFT 资源优化、USB DMA 修复及 SD 物理冷启动验证版。后续提频与降低延迟的建议不属于本次发布功能。

| 项目 | 位置或标识 |
|---|---|
| 本地工作目录 | `D:\fft\fft_phase10_resource_opt` |
| GitHub 分支 | [phase10/resource-opt](https://github.com/vermouth2031/fft/tree/phase10/resource-opt) |
| 固定版本 | [v2026.10.09-phase10-resource-opt-usb-sd-validated](https://github.com/vermouth2031/fft/releases/tag/v2026.10.09-phase10-resource-opt-usb-sd-validated) |
| 已验收实现提交 | `290e7cd9c16277ec04899433c3cc0df9444f5239` |
| 与 Phase 9 对比 | [草稿 PR #5](https://github.com/vermouth2031/fft/pull/5) |
| 硬件 build ID | `b162c5a41c3560519de11c7e90e379a7` |
| 发布回执 | [phase10_github_publication_20261009.json](../reports/phase10_github_publication_20261009.json) |

标签固定发布时已经验收的源码快照；分支继续保存发布回执与文档。回执登记提交不改变电路、固件或测试结果。main 与历史标签保留，未进行合并。

## 下载选择

| 需要什么 | 应下载什么 |
|---|---|
| 已验收的网络交互启动镜像 | Release 的 `ethernet_sd_card.zip`，内部为对应 `BOOT.BIN` |
| 当前分支源码及归档报告 | 分支页面 Code → Download ZIP，或 git clone 后切换 `phase10/resource-opt` |
| 不变的发布源码快照 | Release 下自动生成的 Source code ZIP，或检出上述标签 |
| 轻量源码和工具 | Release 的 `iq_analyzer_source.zip` |
| 可独立复核的冷启动完整证据 | Release 的 `phase10_sd_cold_boot_evidence.zip` |
| 文件身份校验 | Release 的 `SHA256SUMS.txt` 与 `manifest.json` |

Code → Download ZIP 不包含被忽略的 build、artifacts、release 目录，也不包含 Git 历史。源码包不是 SD 启动包。完整证据包与轻量源码包用途不同；轻量源码包不包含全部报告，离线证据检查请用证据包或完整仓库。

本次仅发布实际安装并验收的网络固件；另一种 SD 自动采集固件未作为本次冷启动交付附件。已安装 `BOOT.BIN` 的 SHA-256 为 `02a3ba1e871541fec4b5765704d6f23dd50330fb43272407da68ddc1ad2804f2`。

## 验收与边界

I/Q 各 16 bit，16384 点 FFT，板内回放处理 125 MSPS；真板分析/发布最大延迟 281.296/281.576 μs。LUT 22775、FF 27786、BRAM 128、DSP 49。RAM/JTAG、SD 完整读回与物理冷启动均有独立记录。

冷启动后通过 79 项矩阵（80896 个精确快照值）、1000 次 DMA 切换及 300.015 秒连续传输。物理断电事实来自用户明确确认，确认后只进行网络验证，无 JTAG 下载。详情见 [PHASE10_STATUS.md](../PHASE10_STATUS.md)。

125 MSPS 不表示千兆网口输入同速率的全新 IQ；未接外部 ADC。0 dB 漏检与 Hann 短边界突发误差仍保留。本次保留工程预发布标记，发布说明已明确真实通过的冷启动范围。

## 复核命令

在完整仓库或解压后的证据包根目录运行：

```powershell
python scripts/phase10_boot_evidence.py check
```

该命令核查归档散列、源代码与测试记录绑定关系，不连接开发板，也不会重新执行板测。GitHub Actions 的范围同样是主机软件与归档证据检查，不是云端硬件构建。

如需在原始完整构建目录重新打包，Windows 使用 UTF-8 模式，保证历史 JSON 中的中文路径按 UTF-8 读取：

```powershell
$env:PYTHONUTF8 = '1'
python scripts/phase10_boot_evidence.py package
```

重新打包可能改变 ZIP 时间戳和文档，因而改变压缩包散列；已发布附件保持冻结，不应覆盖。发布回执保存本次远端附件的大小和 SHA-256。
