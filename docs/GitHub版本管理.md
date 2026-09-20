# GitHub 版本管理

公共仓库：`vermouth2031/fft`。默认分支：`main`。

已发布基线的显示名称为 `2023\9\17`，Git标签为 `2023-09-17`。反斜杠不能用于Git标签，因此显示名称与标签采用上述对应关系；原始板测时间为2026-09-17。本轮优化在本地 `optimization/100msps-cleanup` 分支实施，发布状态以远端实际提交为准。

## 内容分工

- Git：RTL、约束、PS 固件、电脑程序、构建与验证脚本、输入向量、文档和报告。
- GitHub Release：预编译硬件/启动包、原始实板证据、SHA-256 文件清单。
- 本地保留：Vivado/Vitis 构建缓存、完整采集导出和设备准备记录。

下载源码后，将硬件附件和实板证据附件解压到源码根目录，即可恢复其中的 `artifacts/`、`release/sd_card/`、`release/ethernet_sd_card/` 和 `captures/`。构建需要自行安装 Vivado/Vitis 2026.1；主机采集与图形界面使用 Python 3.12 标准库，不依赖 Vivado。

GitHub Actions 自动运行 Python 语法和主机 UDP 协议测试。RTL 仿真、Vivado 时序及真实板卡验收仍以本机工具和实测证据为准。

## 后续修改

1. 在独立分支修改，例如 `feature/new-signal` 或 `fix/udp-recovery`。
2. 执行与改动相关的测试，记录结果；修改 RTL 后重新仿真、实现及板测。
3. 提交并推送分支，通过 Pull Request 合入 `main`。
4. 新版本更新 `VERSION.json`、`CHANGELOG.md`，创建新的标签及 Release，不覆盖旧版本记录。

当前发布在 `vermouth2031` 名下。若后续需要放入 `killua365`，可由该账户 Fork，或由两端具备权限的账户办理仓库转移；本次不修改它的其他仓库。
