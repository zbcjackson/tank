# Tank 语音助手前后端分离及多端支持实施方案

## 1. 项目背景与目标
将 Tank 语音助手从单机硬件绑定架构重构为 **Client/Server (C/S)** 架构。
*   **目标：** 支持 Web、macOS (Tauri)、移动端及多端并发访问。
*   **核心挑战：** 保持语音交互的低延迟，实现远程音频流的高效传输与实时打断。

## 2. 总体架构设计

### 2.1 逻辑分层
*   **计算后端 (Backend Server):** 运行 ASR (Faster-Whisper)、LLM、TTS (Edge-TTS) 和工具链。
*   **交互前端 (Frontend Client):** 负责音频采集、本地 VAD 检测、音频播放及 UI 渲染。
*   **传输层:** 基于 WebSocket 的全双工实时流式通信。

### 2.2 核心技术栈
*   **后端:** Python 3.10+ / FastAPI / SQLModel
*   **前端:** React 18 / TypeScript / Vite / Tailwind CSS
*   **桌面封装:** Tauri (Rust 核心)
*   **测试工具:** Vitest (前端单元测试), Playwright (E2E 测试), Pytest (后端测试)

---

## 3. 后端详细设计 (计算与编排层)

### 3.1 Session 管理
*   **SessionAssistant:** 每一个连接对应一个 Assistant 实例，维护独立的对话上下文。
*   **会话隔离:** 通过内存 Session Manager 或 Redis 维护 `SessionID -> Assistant` 的映射。

### 3.2 虚拟音频流水线 (Virtual Audio Pipeline)
重构 `Assistant` 类，使其解耦硬件：
*   **Virtual Input:** 实现一个异步队列，用于接收 WebSocket 传来的原始 PCM 数据。
*   **Virtual Output:** 捕获 TTS 生成的音频流并将其封装为二进制帧发送至 WebSocket。

### 3.3 并发与性能
*   使用 `FastAPI` 的异步机制处理长连接。
*   ASR 和 TTS 引擎在 GPU 模式下运行，支持并发推理。

---

## 4. 前端详细设计 (感知与渲染层)

### 4.1 音频处理管线
*   **本地 VAD (核心):** 使用 `silero-vad` (WASM版) 在前端执行。
    *   *逻辑：* 仅在检测到人声时才向后端发送音频流，显著降低服务端带宽和压力。
*   **打断逻辑 (Interruption):** 前端检测到新语音起止时，立即通过 WS 发送 `interrupt` 信号。

### 4.2 Web 封装与 Tauri 集成
*   **Web 端:** 纯 React 应用，利用 Web Audio API。
*   **macOS 应用:** 使用 Tauri 包装 Web 代码。
    *   *Rust 侧职责：* 管理系统菜单栏图标、全局快捷键 (Option + Space)、开机自启。

---

## 5. 通信协议定义 (WebSocket)

### 5.1 消息格式 (JSON)
```json
// 类型定义: "signal" (控制), "text" (转录/回复), "audio" (二进制前置)
{
  "type": "transcript", 
  "content": "你好",
  "is_final": false,
  "session_id": "xxx"
}
```

### 5.2 音频传输
*   采用原始 PCM (16kHz, 16bit, Mono) 或压缩格式。
*   二进制帧紧跟在相应的描述 JSON 之后发送，或使用专门的二进制通道。

---

## 6. 测试策略与质量保障

### 6.1 单元测试 (Unit)
*   **后端:** 测试 `Assistant` 状态机在“收到音频帧 -> 识别 -> 思考 -> 响应”链路中的正确性。
*   **前端 (Vitest):** 测试协议解析器 `ProtocolHandler`，模拟各种 WebSocket 断连和重连场景。

### 6.2 端到端测试 (E2E - Playwright)
*   **环境模拟:** 在 CI 环境中模拟虚拟麦克风输入（通过 Playwright 注入音频文件）。
*   **断言:** 验证 UI 界面在特定音频输入后，是否在规定时间内出现了预期的文字回复，并且扬声器状态（模拟）正常。

---

## 7. 任务实施清单 (Task List)

### 阶段一：后端重构 (预计 1 周)
- [ ] **A-1:** 定义 `BaseAudioSource` / `BaseAudioSink` 抽象接口。
- [ ] **A-2:** 重构 `src/voice_assistant/core/assistant.py` 支持注入式 I/O。
- [ ] **A-3:** 实现 `QueueAudioSource` 用于接收外部推送的音频数据。
- [ ] **A-4:** 编写 Python 集成测试，验证“无声卡”模式下的端到端流程。

### 阶段二：API 与 WebSocket 服务 (预计 1 周)
- [ ] **B-1:** 搭建 FastAPI 应用骨架。
- [ ] **B-2:** 实现 WebSocket 路由及会话生命周期管理。
- [ ] **B-3:** 开发消息调度器，将 WS 二进制流导向 `QueueAudioSource`。
- [ ] **B-4:** 实现基础的 JWT 身份验证 API。

### 阶段三：前端 Web 核心开发 (预计 2 周)
- [ ] **C-1:** 初始化 React + TS + Vite 环境。
- [ ] **C-2:** 编写 Web Audio 采集模块及 Silero VAD 集成。
- [ ] **C-3:** 实现 WebSocket 状态机类（处理重连、心跳、打断）。
- [ ] **C-4:** 构建基础聊天 UI（仿 TUI 风格）。
- [ ] **C-5:** 编写 Playwright E2E 测试脚本。

### 阶段四：macOS 封装与优化 (预计 1 周)
- [ ] **D-1:** 接入 Tauri 框架。
- [ ] **D-2:** 开发 Tauri Rust 插件：系统托盘与全局快捷键逻辑。
- [ ] **D-3:** 进行 GPU 并发测试与端到端延迟调优。
- [ ] **D-4:** 编写 Docker 部署脚本。

---

## 8. 未来演进
*   **移动端:** 按照相同的协议，使用 Flutter 开发 iOS/Android 客户端。
*   **持久化:** 接入 SQLModel 存储对话历史和用户自定义配置。
*   **插件系统:** 扩展 ToolManager，支持更多第三方 API 工具。
