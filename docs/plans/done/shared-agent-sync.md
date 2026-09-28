> 状态：已完成（2026-09-28）。通用多 Agent 同步脚本、配置产物与全部适用验证已完成。

# 多 Agent 定义同步

## 范围与步骤

1. 共享 Markdown 使用 YAML frontmatter 的 name/description，正文保持工具无关。
2. 新增独立 Python 脚本，递归扫描源目录；默认 agents/，支持 --source-dir 和 --root。
   生成 .pi/agents 的 Markdown 和 .codex/agents 的 TOML，不写死某个 Agent 名称。
3. 全部输入和目标先校验再写入；拒绝重复名称、非法元数据、目标符号链接和手工配置覆盖。
   已生成文件更新采用单文件原子替换，相同内容不重复写；不自动删除历史文件。
4. --check 只检测缺失/差异，不写文件。为现有 code-reviewer 补充元数据并生成配置。
5. 更新使用说明和索引，完成下面的验证后关档。

不安装 Pi 扩展，不运行付费 Agent 请求，不引入供应商模型映射或任意配置转换框架。
脚本使用 PyYAML 解析元数据，以内联脚本依赖声明支持独立运行，不导入应用实现。

## Tests

按 TDD 逐项验证真实 CLI 与临时目录：多个/嵌套定义的格式与正文一致性、重新同步与
只检查模式、重复/非法输入导致零写入、保护手工文件与符号链接、与 cwd 无关的路径解析。
测试归入现有 backend pytest，全部原生配置用 YAML/TOML 解析器验证。

## 交付与验证记录

- `scripts/sync_agents.py` 不含特定角色名称，默认扫描现有 agents/，支持自定义源目录、
  目标项目根目录和只读 --check；使用内联依赖声明，可独立运行。
- 现有 code-reviewer 已补充 name/description，并实际生成 Pi 与 Codex 的配置；
  源文件及两份产物都纳入版本管理。使用约定见[共享定义说明](../../design/shared-agent-definitions.md)。
- 29 项 CLI/文件系统回归全部通过；后端完整回归 5249 passed / 1 skipped；
  Cucumber 18 场景 / 71 步通过。web lint/typecheck、backend/CLI ruff、改动 Python
  文件 pyright、reload 日志、docs/diff 检查均通过。
- 独立 `uv run --script` 实际运行成功，生成后的 --check 通过；原生 YAML/TOML 解析
  验证正文一致。没有安装 Pi 扩展或调用模型，不把配置生成记为真实委派运行验收。
- 协议未改；无新增延期事项。自动清理历史生成文件与任意工具配置转换不在本次范围内。

## Verification Checklist（最终步骤）

1. `cd web && pnpm lint`
2. `cd web && npx tsc -b --noEmit`
3. `cd backend && uv run ruff check core/src/ core/tests/ ../scripts/sync_agents.py`
4. `cd backend && uv run pytest`
5. `cd backend && uv run pyright <改动的 Python 文件>`，不新增类型错误抑制。
6. `cd cli && uv run ruff check src/ tests/`
7. `tmux capture-pane -t tank -p -S -50 | grep -i "error\|traceback\|exception"`；空输出即通过。
8. `cd test && pnpm test`，backend/frontend 必须运行。
9. `python3 scripts/check_docs.py`，同步脚本 --check，以及 `git diff --check`。
10. `python3 scripts/check_protocol_sync.py`：本次不改协议，若范围变化则执行。
