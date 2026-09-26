# Computer-use 多显示器支持

> **Status:** In progress — 2026-09-26 立项，生产工具链、单测与 benchmark 三线并行。
> 同日实现全部落地：枚举/按屏截图/跨屏坐标（含 frame 路径）、doctor、
> benchmark min_displays + multi-display-calc；实机双屏冒烟通过（拓扑/副屏
> 截图 1080×1920/跨屏 CGEvent 坐标逐点精确；未做真实点击与 1-trial 批跑，
> 待机器空闲时按 §3 实机验收补记）。
> 触发来源：[backlog「Computer-use 多显示器支持」](../../backlog.md)（单屏限制阻碍实际桌面任务；
> 本机已具备双显示器验收环境：主屏 1920×1080@2x + 副屏 1080×1920@2x @ (1920,-602)）。

## 0. 目标与非目标

**目标**

1. 生产（macOS 工具链）：`screenshot` 与坐标动作（click/scroll/mouse_move/drag）支持按显示器
   选择目标屏；坐标契约保持"相对于返回的截图"不变。
2. M2 image/frame 路径：窗口可绑定任意显示器上的可见窗口；`Observation.map_point`
   还原到全局 Quartz 坐标（加显示器原点）。
3. 测试：上述行为全部有单测覆盖（fake Quartz，与现有 capture_chain 风格一致）。
4. benchmark：任务 schema 支持 `min_displays`（环境不满足时显式 skip 并记录）；
   运行元数据记录显示器拓扑；新增多屏任务 `multi-display-calc`；suite.yaml 环境钉死说明更新。

**非目标（保持不动）**

- Linux 后端保持主屏语义（Linux adapter 本就在 backlog 另行立项）。
- 旧 DesktopExecutor / 旧 N2 插件不扩建（backlog B4 原则：不为待退役路径加控制层）；
  其主屏行为在多屏主机上仍正确（只截主屏、只点主屏）。
- AX 分支在副屏上的行为不验收（M7 条件性暂缓不变）；`display_geometry` 元组形状不变，
  AX 代码无需改动即可继续工作。
- 不做"拼合所有屏为一张图"的 composite 模式：不同屏缩放系数不同，且会破坏
  "坐标相对截图"的已验证契约（M0–M8 校准基线）。
- `computer_use_common.py` 的 COORDINATE_NOTE 等共享文案不动（单屏提示字节不变，
  保护 benchmark 前后可比性与跨平台一致性 pin 测试）。

## 1. 实证依据（本机双屏，2026-09-26）

| 事实 | 证据 |
|---|---|
| `screencapture -D` 吃 **1-based 序号**（1=主屏），不是 CGDirectDisplayID | `-D 5` 报错 "Must be a number from 1-2"；`-D 1`→3840×2160（主屏）、`-D 2`→2160×3840（副屏） |
| 序号顺序无文档保证（CGGetActiveDisplayList 顺序"no particular order"） | 故弃用 `-D` |
| `screencapture -R<ox>,<oy>,w,h>` 用**全局显示坐标**，可跨屏精确截取 | `-R1920,-602,540,960` 得 1080×1920@2x（副屏局部）；负 y 原点有效 |
| pyobjc `CGGetActiveDisplayList(n, None, None)` 返回 `(err, ids_tuple, count)` | 本机 `(0, (2, 5), 2)` |
| 主屏全局原点恒为 (0,0)，副屏原点可为负 | 副屏 bounds=(1920,-602,1080,1920) |

**按屏截图方案：`screencapture -x [-C] -R<ox>,<oy>,<w>,<h>`（显示器全局 bounds）**，
之后沿用既有 per-display 缩放系数 + sips 缩放 + 尺寸校验。默认（无 display 参数）仍走
`-m` 主屏路径，单屏行为与文案字节级不变。

## 2. 设计

### 2.1 显示器枚举与身份（`computer_use_macos.py`）

- `DisplayGeometry = (display_id, origin_x, origin_y, w_pts, h_pts, pw_px, ph_px)`，
  与 frame 路径现有 `display_geometry` 元组同形。
- `_active_displays() -> tuple[DisplayGeometry, ...]`：`CGGetActiveDisplayList(16, None, None)`
  → 每台 `CGDisplayBounds` + `CGDisplayCopyDisplayMode`；按 id 排序（枚举顺序不稳定，
  排序保证拓扑比较确定）；主屏必须位于 (0,0)，尺寸必须为正，否则 ValueError。
- `_display_geometry(display_id)`：单台元组；未知 id 报错并列出可用显示器。

### 2.2 按屏截图（legacy 路径）

- `_capture_screenshot_macos(*, include_cursor=True, display=None)`：
  - `display=None`：现有 `-m` 主屏路径原样（默认调用方零变化）。
  - `display=<id>`：校验 id 在活跃列表 → `-R ox,oy,w,h`（取整）→ 该屏缩放系数 →
    sips 缩到该屏 point 宽 → 按该屏 point 尺寸校验（复用现有校验逻辑）。
- 截图缓存 `_screen_point_size` → `_screen_caches: dict[id, (w, h, ox, oy)]` +
  `_active_display: int | None`（最近一次截图的屏）。每次截图更新两者。
- `ScreenshotTool` 增加 `display` 参数（int，可选）；结果文本：
  - 单屏：文案不变（字节级）。
  - 多屏：追加 DISPLAYS 说明（各屏 id/main/origin/size + 当前截图屏 +
    "坐标工具可传 display=<id>，默认最近截图的屏"）。

### 2.3 坐标动作（legacy 路径）

- `click/scroll/mouse_move/drag` 增加可选 `display`（进入 `get_info`，macOS only；
  `click_schema` 自动带入 properties）。
- 解析规则：
  - 未传 `display`：用 `_active_display` 的缓存（无缓存 → 主屏默认 1920×1080、原点 (0,0)，
    与现状一致；**不读 Quartz**，保证既有测试与无屏环境不变）。
  - 传了 `display`：缓存命中则用；未命中 → `run_native(_display_geometry)` 现场读
    （等价：缓存存的 point 尺寸=实时值）；未知 id → 错误结果列出显示器，零输入。
- `_normalized_to_pixel(x, y, display)`：归一化 → 该屏**局部** point，再加缓存原点得
  **全局** CGEvent 坐标。主屏原点 (0,0) ⇒ 既有断言（事件坐标==局部坐标）不变。

### 2.4 M2 image/frame 路径（`computer_frame.py` / `computer_observation.py`）

- `_geometry()` → `_topology()`（全屏拓扑，按 id 排序的元组串，用于变化检测）+
  `_geometry(display_id)`（单屏元组，用于 Observation 绑定）。主屏在 (0,0) 的校验保留，
  "仅支持主屏"限制删除。
- `_window_bounds`：窗口必须**完整落在恰好一台显示器内**（全局 bounds 判包含），
  返回该屏**局部** crop；跨屏/出界窗口拒绝（与现状"必须完整在主屏"同级严格度）。
- screenshot（image 模式）新增 `display` 参数：窗口绑定优先（取包含该窗口的屏），
  显式 display 与窗口所在屏冲突时报错；都未给 → 主屏。
- `Observation.map_point`：输出 = 该屏局部 point + `display_geometry[1:3]` 原点
  （主屏 (0,0) ⇒ 现值不变）。
- 观察校验：绑定屏 `_geometry(id)` 与快照不一致 → 拒绝；窗口 bounds 重算不一致 → 拒绝
  （均为零输入拒绝）。
- frame 动作（click/mouse_move/scroll/drag）在 image 模式**拒绝**显式 `display`
  （frame 已固定屏）；schema 同步。`computer_locate`/`computer_frame` 里
  "Main-display window" 描述文案更新。
- batch：legacy 模式动作里的 display 透传；image 模式由上述 frame 拒绝兜底。

### 2.5 自检与脚本

- `computer_doctor`：macOS 增加 `displays` 检查项（枚举失败 → FAIL + 修复提示；
  正常 → OK + 拓扑摘要）。
- `calibrate_macos_coordinates.py` 不动（主屏九点校准语义不变）。

### 2.6 benchmark

- `task.py`：`BenchTask.min_displays: int = 1` + YAML 解析（非法值报 TaskError）。
- `runner.py`：macOS 读显示器数量（复用 `_active_displays`，失败按 0 处理并记录）；
  `min_displays` 不满足 → 跳过该任务，logger 记录，报告 metadata 增加
  `skipped_tasks: [{task, reason}]`（不进成功率分母）。运行 metadata 增加
  `displays` 拓扑（仅 macOS，读失败记录错误字符串）。
- 新任务 `16-multi-display-calc.yaml`（macos, min_displays: 2, strict, gui_only）：
  指示 agent 先把焦点切到非主显示器（点击其桌面），在其上打开 Calculator 算 7×8
  并截图确认。validator = `calc_validator`（严格 7×8/56）`&&`
  `display_validator --calculator-on-secondary`（Calculator 可见窗口完整位于非主屏）。
- 新模块 `benchmarks/display_validator.py`：CGWindowList 找 Calculator 窗口 →
  断言完整位于恰一台非主屏；Quartz 不可用 fail-closed（exit 2）。
- `suite.yaml`：删除"只接一块显示器"钉死，改为"单屏或多屏均可；多屏需记录拓扑且
  跑批期间布局不变"；`README.md` 增补说明。

## 3. Tests（先行）

单测（`backend/core/tests/`）：

1. `_active_displays`：枚举/排序/主屏 (0,0) 校验/非法尺寸报错（fake Quartz）。
2. 按屏截图：`-R ox,oy,w,h` 命令形状；sips 缩到该屏宽；尺寸校验用该屏期望值；
   未知 id 报错。
3. 缓存：`screenshot(display=5)` 更新 active+缓存；默认 click 落在屏 5（事件坐标含
   原点偏移）；显式 `display=2` 用屏 2 缓存；未知 id 错误且零 `CGEventPost`。
4. 文案：单屏截图结果文本与现文案完全一致（字节级）；多屏追加 DISPLAYS 段。
5. frame：副屏窗口绑定（全局→局部 crop、map_point 加原点、click 发全局坐标）；
   跨屏窗口拒绝；display 与窗口冲突拒绝；绑定屏消失后动作拒绝（零输入）；
   image 模式动作传 display 拒绝。
6. `Observation.map_point` 原点平移单测（副屏几何）。
7. doctor：displays 检查 ok/fail 两态。
8. `test_bench_task`：min_displays 解析 + 非法值。
9. `test_bench_runner`：min_displays 不满足 → 跳过并写入 skipped_tasks；满足 → 正常跑。
10. `display_validator` 单测（fake 窗口列表：在副屏通过 / 在主屏失败 / 跨屏失败 /
    Quartz 缺失败 closed）。

实机验收（本机双屏，人工步骤，写入计划收尾）：

- doctor 显示双屏拓扑；`screenshot(display=5)` 得竖屏图；副屏归一化点击命中目标；
  frame 模式绑定副屏窗口点击命中；拓扑变化（拔副屏）后动作零输入拒绝。
- benchmark：单屏环境下 `multi-display-calc` 被 skip 且报告记录原因；双屏环境
  smoke 1-trial 通过链路（效果结论另按 README 可比性规则另行评估，不在本计划宣称）。

## 4. 实施顺序

1. 计划文档 + backlog 移条（本提交）。
2. 显示器枚举 + 按屏截图 + 缓存重构（Tests 1–2）。
3. 坐标动作 display 参数 + 多屏文案（Tests 3–4）。
4. frame/observation 多屏（Tests 5–6）。
5. doctor displays（Tests 7）。
6. benchmark：schema/runner/task/validator/README（Tests 8–10）。
7. `docs/design/computer-use.md` 更新 + 收尾核对。

每步跑 Verification Checklist 适用项（backend ruff/pytest/pyright + docs 检查）。

## 5. Verification Checklist（最终步，全部适用项必须通过）

1. `cd web && pnpm lint`（未改 web，跑基线确认）
2. `cd web && npx tsc -b --noEmit`（同上）
3. `cd backend && uv run ruff check src/ tests/`
4. `cd backend && uv run pytest`
5. `cd backend && uv run pyright <改动文件>`
6. `cd cli && uv run ruff check src/ tests/`（未改 cli，跑基线确认）
7. dev server 无错误（`tmux capture-pane -t tank`）
8. `cd test && pnpm test`（需后端+前端在跑；协议未动，跑基线确认）
9. `python3 scripts/check_docs.py`
10. `python3 scripts/check_protocol_sync.py`（协议未动，基线确认）
