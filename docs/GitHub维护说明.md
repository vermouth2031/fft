# GitHub 版本与证据维护

仓库：<https://github.com/vermouth2031/fft>。

## 分支和版本的区别

- `main` 是已合并的主分支。
- `optimization/phase4-competition-performance` 保存第二至第四阶段的后续成果和五组信号测试整理；通过 Pull Request 对照主分支审阅。
- 现有 `v2026.09.20` Release 对应旧发布版本。开发分支的新代码不会自动改变旧 Release 或旧启动镜像。
- `VERSION.json` 中的 `published: false` 表示第四阶段尚未发布正式 Release，不表示开发分支不能同步至 GitHub。

带工作目录的候选分支仍保留为实验记录。125 MSPS 候选未晋升，不能把候选性能与正式版本混写。

## Git 仓库包含什么

源码、构建脚本、验收报告、答辩材料和约3.2 MB的[五组信号完整证据](../reports/five_signals_20260923/测试报告.md)纳入版本管理。

五组信号目录保留生成参数、输入bin、独立参考、10次采集记录、图文报告及散列清单。历史JSON里的绝对路径表示原始测试环境；在其他电脑核查文件时，以目录内相对路径和散列清单为准，不直接执行历史绝对路径。

```powershell
python scripts/check_five_signals_archive.py
```

该命令不连接板卡，也不需要Vivado，检查140个证据文件和23个报告链接。它证明文件与归档一致，不替代实际硬件测试。

## 大文件与正式交付

`build/`、`captures/`、`artifacts/`和`release/`继续作为本地产物目录。硬件镜像和大规模原始回归证据通过完整交付包管理，不加入普通Git历史。

当前本地完整交付包为`release/phase4-complete-20260922.zip`，935528645字节，SHA-256：

```text
4e07fbc86a0768464a6923da5d096b288c8b15b7334f0840005291d2ec0d5b53
```

该冻结包对应源码提交`2dd36bac68d44f71b55ee4beb817c3391dcffc14`。9月23日新增五组信号不在9月22日冻结包中，应查看仓库中的独立证据目录。已有正式报告中指向`captures/`或`build/`的链接，需要在本地完整工作区或相应交付包中打开；GitHub源码下载不是完整硬件交付包。

以后发布新Release时，应记录准确的源码提交、硬件构建ID、镜像散列与验收范围，并上传相应完整包。保留旧包和旧标签，不用同名文件覆盖历史发布。

## 自动检查的范围

GitHub Actions检查Python语法、UDP协议与恢复、数字零区间参考、检测器兼容性，以及五组信号归档完整性。云端没有连接开发板，也没有Vivado，不能将Actions绿色通过写成一次新的板测或时序验收。

本地新增测试脚本为`scripts/test_five_signals.py`，需要匹配镜像的开发板、NumPy及AMD FFT位精确模型。它会拒绝覆盖已有采集目录。绘图脚本为`scripts/report_five_signals.py`，另需matplotlib及Windows微软雅黑字体；已保存的PNG和HTML可直接查看。
