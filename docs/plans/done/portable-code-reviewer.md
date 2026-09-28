> 状态：已完成（2026-09-28）。评审角色已迁到通用目录并泛化；清单、模式、三轮上限和项目约定均明确。

# 通用代码评审角色

## 范围与步骤

1. 将专用目录中的角色迁到 `agents/code-reviewer.md`，移除项目/任务和工具绑定。
2. 查阅 Fowler/Beck 与 Google 的一手资料，写入固定 Code Smell 参考清单。
3. 定义默认独立评审与明确授权后的自主重构模式，明确最多三轮及结束条件。
4. 从目标项目读取测试和提交约定，修复旧文档与报告引用。
5. 完成以下验证后关档；不更改业务代码或重新执行上一次 S0 评审。

## 交付与选择

交付为 [agents/code-reviewer.md](../../../agents/code-reviewer.md)，普通 Markdown，
没有工具专属元数据或自动发现承诺；可复制到其它项目或由调用方作为上下文加载。
内置 24 项经典 Code Smell 的名称和判断提示，并链接 Fowler/Beck 的公开章节、
Fowler 的 Smell 说明与重构目录、Google 评审指南。

仅评审、未授权修改时默认 review-only；明确授权修改时用 review-and-refactor 自主闭环。
模式控制修改权限，不决定审查独立性或效果；由另一个执行者评审原代码后可以自行修复，
对自己新增修改的检查则属于自检。两者使用相同质量标准，测试/提交从目标项目读取。
最多三轮不是必须三轮：任一轮无可操作问题且无遗留问题立即结束，只有做了修改并通过
必需验证时才进入下一轮。不把证据不足误报为没有问题。

目录补充说明：根目录 `agents/` 是此处的角色文本组织约定，不是跨工具加载标准；
通用性来自文件内容可移植。各工具的自动注册机制需另行适配，不混入通用角色正文。

旧角色文件已删除，历史评审记录和交互报告中的入口已指向新定义。
角色内容、引用和 diff 检查通过；文档一致性检查通过（42 个文档），报告链接更新后
TypeScript 检查通过。无运行代码/协议变化，无需应用回归，无新增延期事项。

## Tests

本次是 Markdown 角色说明与文档修改，不新增形式单测。
检查角色不含特定项目/工具假设、固定清单齐全、两种模式与三轮边界明确、旧路径引用
已修复、来源链接与内部链接可用；运行文档一致性及 diff 检查。

## Verification Checklist（最终步骤）

1. `cd web && pnpm lint`：无 web 代码变更，不适用。
2. `cd web && npx tsc -b --noEmit`：无 web 代码变更，不适用。
3. `cd backend && uv run ruff check core/src/ core/tests/`：无 Python 变更，不适用。
4. `cd backend && uv run pytest`：无运行代码变更，不适用。
5. 改动 Python 文件 pyright：无 Python 变更，不适用。
6. `cd cli && uv run ruff check src/ tests/`：无 CLI 变更，不适用。
7. 开发服务 reload 日志：角色说明不进入运行服务，不适用。
8. `cd test && pnpm test`：无应用行为变更，不适用。
9. `python3 scripts/check_docs.py`，另检查角色引用与 `git diff --check`。
10. `python3 scripts/check_protocol_sync.py`：无协议变更，不适用。
