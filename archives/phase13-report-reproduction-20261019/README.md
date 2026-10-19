# Phase13 最终报告与后续复现材料归档

归档日期：2026-10-19。最终报告由用户明确确认为 `D:/fft/报告.docx` 与 `D:/fft/报告.pdf`，两份文件按原字节归档，没有修改内容、目录、字体或排版，也没有重新导出 PDF。

## 获取文件

- [最终 Word 报告](report/报告.docx)
- [最终 PDF 报告](report/报告.pdf)
- [完整归档附件](https://github.com/vermouth2031/fft/releases/tag/v2026.10.19-phase13-report-reproduction)
- [逐文件来源、大小和 SHA-256](file-manifest.json.gz)
- [下载附件 SHA-256](SHA256SUMS.txt)

| 附件 | 内容 |
| --- | --- |
| final_report.docx / final_report.pdf | 用户确认的最终报告原文件 |
| phase13_reproduction_snapshot.zip | 本地 reports 完整快照、复现操作记录、失败尝试与最终成功验收、已封装的 SD 发布包、GUI 启动脚本 |
| phase13_simulation_capture.zip | 第三章仿真截图、WDB/VCD、波形配置、脚本、日志、原始数据和证据索引 |
| phase13_board_capture.zip | 第四章实板采集、有限回放、DMA1000、连续300秒、截图与修正后的同窗口图 |
| file-manifest.json / SHA256SUMS.txt | 文件溯源与下载校验 |

## 工程和数据的对应关系

本归档分支以 `0f224112cf0480e7e4eefcb2077350f2634b4135` 为基础；后续复现使用的源提交为 `cb04c3bb36940ad93665691d92cb46f533961107`。实现提交为 `806af4d4d50d696c358c5f22563000a9d56f899e`。本次未修改 RTL、PS 固件或上位机实现。原发布标签 `v2026.10.13-phase13-structure160-usb-sd-validated` 保持不变。

工程配置：I/Q 各16 bit、160 MSPS、16384点 FFT，构建 ID `4757a33c02eed50a403db87d09cb091f`。复现记录保留于 [reproduction-summary](reproduction-summary)：2026-10-13 的 RAM/JTAG 有限79例、宽带272例、DMA1000及故障用例、连续60/300秒与 SD 真正断电冷启动验收；2026-10-14 的报告采集存于截图包。2026-10-19 是归档日期，不代表重新执行了上述测试。

`reports` 快照还包含前序阶段的历史证据，不能将其全部理解为本次新增测试。初次 epoch=79 的冷启动检查和失败的 GUI/Python 尝试作为历史记录保留，最终通过的冷启动以 epoch=0 开始的验收为准。

## 截图使用说明

`figures/chapter3-original` 和 `figures/chapter4-original` 保留原截图、原索引及原文件名，截图文件名不一定等于最终报告的题注编号。

最终报告图4-7和图4-9对应的修正图分别为 [figure4_7.png](figures/chapter4-corrected/figure4_7.png) 与 [figure4_9.png](figures/chapter4-corrected/figure4_9.png)。[同窗口证据](figures/chapter4-corrected/screenshot_evidence.json) 明确记录频域数值与谱快照均对应窗口0。原始截图仅用于追溯，不应覆盖修正图。突发长度来自独立突发记录，不能等同于 FFT 窗口长度。

第三章证据索引保留不同单元测试的实际时钟、核心 WDB 冻结范围与完整验证来源；不得把所有单元波形都解释为160 MHz或完整核心回归。前端离线查看截图来源于已采集的真板记录，不代表归档当日实时连接。

## 恢复与核验

检出本归档标签后，将 `phase13_reproduction_snapshot.zip` 解压到一个独立的工程副本，恢复其中的 reports、reproduction、release 和启动脚本。ZIP 内 `launchers/Open_Reproduced_IQ_Monitor.cmd` 对应原工程根目录的启动脚本；其中绝对路径可能需要根据新机器调整。为准确恢复原复现目录，应以快照中的 reports 整体替换独立副本的 reports（避免残留原版本中已删除的文件），因此请先保留原发布版本。`reproduction-worktree.patch` 和 `reproduction-worktree-status.json` 记录原复现工作区相对于源提交的修改与删除。

已验证的 SD 分发包位于快照中的 `release/phase13_sd_verified`，其中有独立的 `SHA256SUMS.txt`、源代码包、启动包与冷启动证据包。它与2026-10-13第一次发布的构建产物有独立散列，应按各自清单核验，不能混用。

下载后先根据 `SHA256SUMS.txt` 核验附件，再根据 `file-manifest.json` 对照 ZIP 内逐文件 SHA-256。清单保留原本机路径作为溯源信息，恢复时按归档相对路径使用。

未重复收入 portable_verification 解压副本及 inherited_release 副本；已有封装验证包与原发布标签可恢复相应内容。仿真缓存（.Xil、xsim.dir、__pycache__）及第四章工作区中旧报告副本未收入，具体排除路径见清单。本归档没有更新 main，也没有改变原工程分支或原发布附件。

仓库内逐文件清单采用无损 gzip 压缩，解压内容与 Release 附件 `file-manifest.json` 完全一致。

## 大包分卷下载

受上传链路影响，Release 中两个大 ZIP 使用 `.zip.part001` 等连续分卷传输。分卷内容按顺序拼接后与本归档清单中的原 ZIP 完全一致。报告 Word/PDF 和实板截图 ZIP 可直接下载使用。

请先下载全部 Release 附件，再运行：

```powershell
gh release download v2026.10.19-phase13-report-reproduction --repo vermouth2031/fft --dir phase13_archive
cd phase13_archive
python restore_archives.py
```

[下载说明](DOWNLOAD_README.txt)、[恢复脚本](restore_archives.py)、[分卷清单](split-manifest.json) 和 [分卷 SHA-256](SPLIT_SHA256SUMS.txt) 提供传输与恢复校验。脚本先校验每卷，再合并并校验完整 ZIP；它不会删除分卷。固定发布标签保留原归档数据提交，分支后续提交补充下载方式和发布回执。

[发布回执](publication-receipt.json)：100 个附件已逐一重新下载并验证 SHA-256，两个分卷包已还原并与原 ZIP 散列一致；原归档提交的分支和标签自动检查均通过。
