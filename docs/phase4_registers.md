# 构建身份、吞吐与 Phase 8 DDR/DMA 寄存器

Phase 8 接口版本为 `0x00010004`，保留 Phase 7 的记录格式、双 Bank 地址和 UDP 命令，并将 IQ 上传路径改为 PS DDR 到 PL 的 AXI DMA。分析器基地址仍为 `0x40000000`，AXI DMA 控制器位于 `0x40400000`。

## 身份和时钟

| 偏移 | 含义 |
|---|---|
| `0x004` | 硬件接口版本，高 16 位为兼容主版本 |
| `0x010` | 板内每秒 IQ 对数，当前为 125000000 |
| `0x014` | FFT 时钟 Hz，当前为 125000000 |
| `0x08c` | 能力：bit0 数字零检测，bit1 构建身份和诊断快照，bit2 双 Bank 动态 IQ，bit3 DDR/AXI DMA 加载 |
| `0x090–0x09c` | 128bit 构建 ID，低 32bit 在低地址 |
| `0x0a0` | 时间戳时钟 Hz，当前与源时钟相同 |
| `0x0a4` | 测量记录格式版本，当前为 1 |
| `0x0a8` | 谱扫描并行 bin 数，当前为 8；历史隔离兼容候选为 4 |

构建 ID 是 `phase4_build_config.py` 对 RTL、约束、板卡预设、FFT/构建脚本和构建配置等输入计算 SHA-256 后取前 128bit。生成的 `iq_build_config.sv` 排除自身以避免递归。完整输入散列保存在 `build/config/build_identity.json`。固件 ELF、bitstream、XSA 和 BOOT 另有完整 SHA-256；构建 ID 不是 bitstream 散列，也不是认证机制。

主机拒绝未知接口主版本、缺失能力和未知记录格式。部署、板测及打包还会将读回字段逐项与本地已核验构建配置比较，避免仅凭旧的功能版本号将其他构建认作当前镜像。

## 快照协议

向 `0x100` 写入 1，请求源域与 FFT 域诊断快照。源域当拍锁存；FFT 域在请求同步到达后锁存，并通过 XPM 握手返回。数据保持到下一次有效请求，不直接跨域读取变化中的多位计数器。

| 偏移 | 含义 |
|---|---|
| `0x134` | bit0：结果有效；bit1：跨域请求未完成 |
| `0x138` | 完成快照的序号 |
| `0x140/144` | 回放发出样本数，64bit |
| `0x148/14c` | 输入 FIFO 接受样本数，64bit |
| `0x150` | 输入被拒绝次数，32bit |
| `0x154` | 输入 FIFO 写侧占用高水位，13bit 有效 |
| `0x158/15c` | FFT 快照返回源域的 tick，64bit |
| `0x160/164` | FFT 输入握手样本数，64bit |
| `0x168/16c` | FFT 输出复数点数，64bit |
| `0x170` | FFT 输出完整窗口数，32bit |
| `0x174` | 频域结果 FIFO 拒绝次数，32bit |
| `0x178` | 输入 FIFO 非法空读次数；当前读使能被空/复位状态保护，因此保持 0 |

请求繁忙或采集复位期间，AXI 请求返回错误。UDP 固件拒绝明显的重复繁忙请求。主机等待状态等于 1，再读取序号、负载并复查序号，超时或序号变化会使采集失败。

运行中源域与 FFT 域快照的时刻不同，不允许把瞬时计数差直接称为丢样。停止并排空后检查：

```
issued = accepted = FFT input = FFT output = captured IQ pairs
captured IQ pairs = 8192 × FFT output windows
FFT output windows = completed measurement windows
input rejected = result queue rejected = underreads = 0
0 < input FIFO high water < 4096
```

同时保留原结果环形缓冲丢弃数、UDP 丢包数、窗口序号、记录配置与时间戳检查。FIFO 高水位是写侧观察值，包含跨域指针可见性延迟，不是外部仪器测得的物理瞬时占用。

## 兼容与复现

原频域 128 字节、突发 64 字节记录保持格式版本 1。现实现源时钟与时间戳时钟相同，记录内采样率足以换算原有样本和周期字段；主机性能元数据显式使用时间戳频率。若以后拆分时钟，须重新设计记录定义，不能只改寄存器值。

构建配置当前仅允许已验证的 100/125 MHz 物理组合，拒绝通过修改 JSON 冒充提频。`scripts/run.ps1` 在构建前生成并检查配置，相同内容不重复改写文件，以免使正在运行的 Vivado 构建失效。

## Phase 7 双 Bank

`0x10000–0x2ffff` 仍是 32768 字的 IQ 窗口，`0x180` 选择该窗口映射到 Bank 0 或 1。运行时只允许写非活动 Bank。

| 偏移 | 含义 |
|---|---|
| `0x180` | host Bank 选择，bit0 |
| `0x184` | 控制：bit0 commit ready，bit1 arm，bit2 取消 pending，bit3 invalidate，bit4 清错误计数 |
| `0x188` | 状态：active/host/pending Bank、pending valid、两 Bank ready、running、host write allowed |
| `0x18c/0x190` | Bank 0/1 样本长度 |
| `0x194/0x198` | Bank 0/1 block ID |
| `0x19c/0x1a0` | Bank 0/1 CRC32 元数据 |
| `0x1a4` | 成功切换次数 |
| `0x1a8` | 当前 block ID |
| `0x1ac/0x1b0` | 最近切换 tick，64bit |
| `0x1b4` | 活动 Bank 写入拒绝次数 |
| `0x1b8` | 双 Bank 错误位 |

固件 UDP type 6 分块上传，type 7 commit/arm，type 8 查询状态，type 9 中止上传。固件验证每包 CRC32、offset 连续性和整块 CRC32；RTL 只接受长度为 8192 的整数倍且与当前 replay length 一致的 Bank，并在 `issued mod 8192 == 8191` 后切换。

## Phase 8 DDR/AXI DMA 加载器

UDP type 6 的 IQ 字先复制到 PS DDR 缓冲区。type 7 commit 在核对包序、整块 CRC 和长度后刷新 ARM 数据缓存，启动 AXI DMA MM2S；PL 端在写入非活动 Bank 的同时独立计算 CRC32。只有 DMA 的 `TLAST`、接收字数和 CRC 全部匹配时，目标 Bank 才会置 ready。旧的 FFT 边界 arm/switch 逻辑保持不变。

| 偏移 | 含义 |
|---|---|
| `0x1c0` | DMA 加载控制：bit0 start，bit1 abort，bit2 clear done/error；读回为 0 |
| `0x1c4` | DMA 目标 Bank，bit0 |
| `0x1c8` | 预期 IQ 对数，只接受 8192/16384/24576/32768 |
| `0x1cc` | 目标 block ID |
| `0x1d0` | 预期整块 CRC32 |
| `0x1d4` | 状态：bit0 active，bit1 done，bit2 error，bit3 target Bank |
| `0x1d8` | 本次 AXI Stream 已接收 IQ 对数 |
| `0x1dc` | 本次 PL 计算的最终 CRC32 |
| `0x1e0` | 成功 DMA 加载累计次数 |
| `0x1e4` | 错误位：bit0 长度/TLAST，bit1 TKEEP，bit2 超长，bit3 缺少期望 TLAST，bit4 CRC，bit5 abort，bit6 start 参数，bit7 配置写入 |

DMA 的 `M_AXI_MM2S` 通过 PS `S_AXI_HP0` 从 DDR 读取，32 bit `M_AXIS_MM2S` 与分析器 `S_AXIS_IQ` 同在 125 MHz。DMA 只写非活动 Bank；活动 Bank 始终由分析器以 125 MSPS 循环读取。因此这里的 125 MSPS 是板内消费速率，不是千兆以太网持续提供不重复 IQ 的速率。
