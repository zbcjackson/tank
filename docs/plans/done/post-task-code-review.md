> 状态：已完成（2026-09-28）。任务收尾评审关卡已加入项目指令，并通过 code-reviewer 第一轮复核。

# 任务收尾评审规则

## 步骤

1. 保留 AGENTS.md → CLAUDE.md 符号链接，在实际指令文件中新增完成后的评审规则。
2. 所有适用测试/验证通过后，使用 code-reviewer 的 review-and-refactor 模式，
   提供完整任务范围和验证记录；允许必要修复并重新验证，无问题立即结束，最多三轮。
3. 明确主执行者等待、累计轮次、不可静默跳过和防止递归触发的规则。
4. 验证文档、链接和角色配置一致性，再按新规则执行一次子 Agent 复核并关档。

## Tests

仅修改项目指令及文档，不新增形式单测。检查符号链接保持不变、两种入口读取同一规则、
角色链接可用、同步产物 --check 通过、docs/diff 检查通过；子 Agent 复核规则与现有
评审定义是否一致、是否存在无限委派或错误的提前完成条件。

## 结果

AGENTS.md 仍是指向 CLAUDE.md 的符号链接；实际指令新增强制完成关卡。
主执行者在适用测试和验证通过后委派 code-reviewer，以 review-and-refactor 模式
负责评审、必要修复和复验；父执行者等待结果，无问题立即结束，最多三轮，不递归触发。

本次已执行新关卡：子 Agent 第 1 轮未发现可操作或遗留问题，没有修改或另建提交，
按规则立即结束。主执行者与子 Agent 均验证 docs 检查、diff 空白、符号链接和
角色生成物 --check 通过。无运行代码变化，无应用回归要求，无新增延期事项。

## Verification Checklist（最终步骤）

1. web lint：无 web 代码变更，不适用。
2. web `tsc -b --noEmit`：无 TypeScript 变更，不适用。
3. backend ruff：无 Python 变更，不适用。
4. backend pytest：无应用代码或测试变更，不适用。
5. 改动 Python 文件 pyright：无 Python 变更，不适用。
6. CLI ruff：无 CLI 变更，不适用。
7. 开发服务 reload 日志：项目指令不进入应用运行代码，不适用。
8. Cucumber E2E：无应用行为变更，不适用。
9. `python3 scripts/check_docs.py`、同步脚本 `--check`、符号链接和 `git diff --check`。
10. protocol sync：无协议或生成产物变更，不适用。
