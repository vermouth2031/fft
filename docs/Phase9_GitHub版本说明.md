# Phase 9：16384 点 FFT GitHub 版本

本版本以独立分支和预发布管理，验收范围为 RAM/JTAG 实板运行。原 SD 镜像未更换，SD 安装与物理断电冷启动未验证。

| 项目 | 位置或状态 |
|---|---|
| 仓库 | https://github.com/vermouth2031/fft |
| 当前开发分支 | `phase9/fft16k` |
| 对照基线 | `phase8/ddr-dma-streaming`，r17 提交 `b37d7986f1114f33a0c0196521dd6525c34a98aa` |
| 已验收实现提交 | `9cd3adf1be5c42fa7d05462e8961bc00b1d82154` |
| 预发布标签 | `v2026.10.09-phase9-fft16k-ram-validated` |
| 硬件构建 ID | `48ec8e97bf87f19a0cbf4efcb7c8a501` |
| 合并状态 | 通过草稿 Pull Request 审阅，不自动合并至主分支 |

Git 分支保存源码、测试工具、输入向量和验收报告。Release 附件提供可下载的启动包、源码包、验收证据包和散列清单。`build/` 等本地构建中间目录不加入普通 Git 历史。

`VERSION.json` 的 `source_commit` 指已验收实现提交；后续 GitHub 管理提交只调整版本说明、发布元数据和云端检查。Release 标签指向包含这些管理文件的提交。`published: true` 表示已有 GitHub Release；`prerelease: true` 表示它仍是预发布，不能当作 SD 冷启动已验证的正式交付。

## 已完成的验证

- 16384 点 FFT、125 MSPS、I/Q 各 16 bit；双 Bank 各 32768 对样本。
- RTL 对 AMD 定点参考逐点比较：64 窗、1048576 个复数输出全部一致。
- 125 MHz 布局布线 setup/hold：+0.015/+0.048 ns。
- 79 组实板数值配置、1000 次动态切换、60/300 秒持续运行通过。
- 实板最大分析/发布延迟 281.296/281.576 µs；动态测试无硬件丢弃、FFT 编号间断或 UDP 缺包。

完整指标和限制见 [第九阶段优化验收报告](../reports/第九阶段优化验收报告.md)。0 dB 测试仍有漏检，Hann 窗边缘短突发存在频率偏差，扩大 FFT 不代表这些算法限制已经解决。

## 自动检查能证明什么

每次推送或创建 Pull Request 时，GitHub Actions 检查 Python 语法、主机协议、检测器兼容性、历史归档，以及本版本 1378 个证据和源码文件的完整性。

```powershell
python -X utf8 scripts/verify_phase9_evidence.py
```

此检查可以在没有开发板和 Vivado 的电脑上运行。云端绿色通过表示已保存的资料完整且相关软件检查通过，不表示重新进行了 FPGA 综合、时序验收、板测或冷启动。

## 下载和启动范围

- `iq_analyzer_source.zip`：源码及构建所需的项目文件；完整本地中间构建目录不在包内。
- `phase9_acceptance_evidence.zip`：本次原始板测记录、输入、参考、部分日志及离线完整性检查工具。
- `ethernet_sd_card.zip`：网络固件启动包。
- `sd_card.zip`：SD 自动测试固件和回放向量。
- `manifest.json`：构建产物与源码散列。
- `phase9_delivery_receipt.json`：本次上传附件的 SHA-256 和版本对应关系。

启动包已经生成；尚未把新版安装到物理 SD 卡并完成断电再上电验收。下载附件本身不会改变开发板启动状态。
