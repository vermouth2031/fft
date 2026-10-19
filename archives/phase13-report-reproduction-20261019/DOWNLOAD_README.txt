Phase13 最终报告与复现材料下载说明

最终报告为 final_report.docx 和 final_report.pdf，可以直接下载打开。
phase13_board_capture.zip 可以直接解压。

受上传链路影响，两个大 ZIP 按原始字节分卷上传：
phase13_reproduction_snapshot.zip.part001 ...
phase13_simulation_capture.zip.part001 ...
分卷文件不能单独解压，必须全部下载并按顺序合并。

使用 GitHub CLI 一次下载全部附件：
gh release download v2026.10.19-phase13-report-reproduction --repo vermouth2031/fft --dir phase13_archive
cd phase13_archive
python restore_archives.py

也可在发布页逐一下载全部 .partNNN、split-manifest.json 和 restore_archives.py 到同一目录，然后运行 python restore_archives.py。
脚本使用 Python 标准库，无需安装额外依赖；先校验每个分卷，再合并并校验完整 ZIP，保留分卷文件。

完整 ZIP 的散列与原 SHA256SUMS.txt、file-manifest.json 对应，分卷没有改变 ZIP 内容。
SPLIT_SHA256SUMS.txt 用于校验分卷、分卷清单和恢复脚本。归档数据测试日期为2026-10-13/14，发布归档日期为2026-10-19。
