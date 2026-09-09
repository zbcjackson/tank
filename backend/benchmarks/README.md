# Tank Benchmarks

本地基准套件：量化子代理完成真实任务的能力，用副作用判定成败（绝不比对像素）。

## 测什么 / 不测什么

**测**：一个子代理（定义提示词 × 模型 profile × 工具集）在真实桌面/文件系统上完成任务的
成功率、步数、耗时、token、截图数。首个套件 `computer_use`（桌面 GUI 任务）。

**不测**（刻意绕开，是 A/B 对比中的恒定量）：WorkerSupervisor 调度/持久化/回注、审批 UI、
ASR/TTS/语音链路。驱动器直连 `AgentRunner.run_agent`（见 `tank_backend/benchmarks/driver.py`）。

## 用法

```bash
cd backend/core
uv run python -m tank_backend.benchmarks \
    --suite ../../benchmarks/computer_use \
    --agent computer_use --trials 3 --label baseline-macos
```

- 报告与逐 trial trace（JSONL + 每步截图）落在 `benchmarks/<suite>/reports/<时间戳>-<label>/`
- **绝不在开发机裸跑**（会动真实鼠标键盘）：Linux 在 GUI VM，macOS 在真机/独立环境
- 跑批期间不动键鼠；环境钉死清单见任务套件目录下 suite.yaml 注释

## 结构与演进

```
benchmarks/
├── README.md                  ← 本文件
└── computer_use/              ← 套件 = suite.yaml + tasks/*.yaml + assets/ + reports/
    ├── suite.yaml             默认 agent / trials / 端口
    ├── tasks/*.yaml           每任务：instruction + setup + validator + teardown
    └── assets/                零外网页面（本地 http server 服务，副作用回传 capture 文件）
```

框架代码在 `backend/core/src/tank_backend/benchmarks/`（task / shell / pageserver /
trace / driver / runner / report / __main__），套件无关。

**演进路径**（加东西不改机制）：

1. 更多子代理套件：新增 `benchmarks/<name>/`（suite.yaml + tasks），`--agent <definition>` 换被测对象
2. 测调度/持久化：新增 driver（实现 `BenchmarkDriver` 协议，如 SupervisorDriver）
3. 测整 Tank（语音→回复全链路）：新增 driver 驱动 WS 客户端 + 新套件任务集
4. 更多 validator kind：目前只有 `shell`（只查副作用原则在此强制）

## 可靠性规则（沿用方案 §A17 八条）

确定性 setup/teardown；validator 只查副作用；零外网；每任务多 trial 报成功率+置信区间；
环境钉死；全量 trace；硬超时+步数上限；任务先人工金标跑一次、validator 过了才入套。
