# 项目补充备份与恢复说明（2026-10-21）

用户要求备份可能在清理 `D:/fft` 时丢失的项目资料。本次只新增备份文件和 GitHub 归档，没有删除本地文件，没有修改工程实现、报告正文、原有分支或旧发布附件，也没有重新运行真板测试。

## 备份入口

- [本次补充附件](https://github.com/vermouth2031/fft/releases/tag/v2026.10.21-project-preservation)
- [原报告与复现归档（恢复所需）](https://github.com/vermouth2031/fft/releases/tag/v2026.10.19-phase13-report-reproduction)
- [完整项目总结](PROJECT_SUMMARY.md)

本次清单覆盖 **116583 个文件路径**，新增保存 **3042 份独立内容**；其中 **110072 个路径**引用已归档的相同 SHA-256 内容。其余重复内容在本次 ZIP 内去重，通过清单恢复各自原始路径。新包不是旧归档的替代品，恢复需要两个发布版本。

## 已保留内容

1. 最终 Word/PDF 报告、历次报告修改稿、图表、第三/四章截图及修正的同窗口截图、报告审阅和写作资料。
2. 项目总结、交接说明、赛题材料、海报图片/PDF及生成脚本。
3. Phase6—Phase13 各工程现存源码、配置、测试脚本、输入数据、固件/启动产物、封装发布包和报告目录；复现工程的辅助脚本及复现记录。
4. 第三章仿真原始证据、第四章实板原始证据、R17 补充测试资料。
5. 两份独立 Git bundle：历史工程共享仓库的全部现存引用，以及复现工程全部现存引用。另存各工作区 HEAD、状态和二进制补丁。bundle 不依赖原来共享 `.git/worktrees` 的路径。

## 范围边界

这不是整块硬盘镜像。未收入可重新生成的 Vivado/Vitis `build` 缓存、`.Xil`、`xsim.dir`、Python 缓存、临时文件、重复解压/下载副本，以及 Phase6/7 `captures` 中约 25 GiB 的历史大批量采集文件。现存正式 `reports`、发布包和最终版本验收记录已在选定范围内。逐项排除原因写在清单的 `omitted`。

Vivado/Vitis、Python 安装程序、系统网卡配置、硬件连接和板卡 SD 的实时状态不属于本备份。恢复源代码后可重新构建，不能保证直接恢复未打包的 IDE 缓存。原始源码和报告均按字节保存，未因归档而重新生成或排版。

## 下载并恢复选定文件

下载两次发布的全部附件（两个目录分开，避免旧版与新版同名脚本冲突）：

```powershell
gh release download v2026.10.19-phase13-report-reproduction --repo vermouth2031/fft --dir previous_archive
python previous_archive/restore_archives.py
gh release download v2026.10.21-project-preservation --repo vermouth2031/fft --dir supplemental_archive
python supplemental_archive/restore_backup.py --previous previous_archive --output restored_fft
```

`restore_backup.py` 只使用 Python 标准库，要求目标目录为空；不删除文件、不覆盖已有目标。它先校验并合并本次分卷，再按 `backup-manifest.json.gz` 从新旧 ZIP 或独立附件提取文件，逐文件核验 SHA-256。分卷保留。相对路径对应原 `D:/fft`，特殊 `_recovery` 目录保存 Git 历史与状态。清单压缩采用标准 gzip。

本次 `PROJECT_SUMMARY.md` 可直接阅读；其本地证据相对链接在完整恢复后的原中文文件名总结中使用。

## Git 历史恢复

在上述恢复完成后，可以将 bundle 克隆到**新的**目录：

```powershell
git clone restored_fft/_recovery/historical-project-all-refs.bundle historical_git
git clone restored_fft/_recovery/reproduction-all-refs.bundle reproduced_git
```

如果需要恢复工作区当时的实际文件，应结合恢复出的工程文件、`_recovery/*-status.json` 与补丁；bundle 本身只保存被引用的提交历史，不包含工作区未提交内容。恢复清单已另存选定的工作区文件。不要把旧工作树 `.git` 指针直接拷贝到新机器。GitHub 原仓库地址为 `https://github.com/vermouth2031/fft.git`；本次未修改当前复现工程指向本地目录的 origin。

## 完整性

`SHA256SUMS.txt` 校验本次附件，`supplement-parts.json` 校验每卷和原始 ZIP，`backup-manifest.json.gz` 记录每个恢复路径的源文件、大小、散列和实际储存位置。旧归档 100 个附件的服务器 SHA-256 已与此前逐一回下载的回执比对。本次新增附件已逐一重新下载并通过 SHA-256 校验，分卷拼接散列一致。


## 完成验收

发布共 175 个附件；116,583 个文件已在独立空目录实际恢复并逐一校验 SHA-256，两份 Git bundle 均成功克隆并通过完整性检查。详见 [发布回执](publication-receipt.json)、[恢复验收](restore-verification.json) 和 [最终状态](FINAL_STATUS.json)。没有删除任何本地原文件。
