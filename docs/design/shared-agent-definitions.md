# 共享 Agent 定义与同步

`agents/` 保存可移植角色源文件，`scripts/sync_agents.py` 生成 Pi 和 Codex 的注册配置。
源目录是本项目的组织约定，不是跨工具的自动加载标准。该工具不依赖应用后端实现，
可复制到其它仓库，也可用 `--root` 为其它项目生成配置。

## 定义格式

每个 UTF-8 Markdown 文件包含且仅包含两个 YAML 元数据字段，然后是非空角色正文：

```markdown
---
name: planner
description: Plan implementation steps and verification.
---
# Planner

Read the project's requirements and conventions before preparing a plan.
```

脚本递归发现所有 `.md` 文件，因此可以把角色分组放在子目录。每个文件都须符合上述
格式，说明文档应放在源目录外。输出文件名来自 `name`，不依赖源文件名。
名称以小写字母开头，只包含小写字母、数字、连字符和下划线；名称须全目录唯一。
元数据必须是字符串；拒绝缺少/未知/重复字段，避免静默丢失用户以为会生效的设置。
模型、工具和权限不由本版转换器设置，各客户端继续使用其运行环境配置。

正文按文本保持一致，包括空行、引号、Unicode 和结尾换行；输入换行规范化为 LF。
新增角色只需新增定义文件，不需要修改脚本中的名称列表或分支。

## 运行

需要 Python 3.11+ 与 PyYAML。脚本声明了独立依赖，可由 uv 准备环境：

```bash
uv run --script scripts/sync_agents.py
uv run --script scripts/sync_agents.py --check
```

也可使用已安装 PyYAML 的 Python 直接运行。脚本默认将自身所在 `scripts/` 的上一层
作为项目根目录，默认源目录为该根目录下的 `agents/`，与启动时 cwd 无关。

```bash
# 改用前面讨论的共享目录（相对项目根目录）
uv run --script scripts/sync_agents.py --source-dir .agents/agents

# 用同一个脚本为另一个项目生成配置
uv run --script scripts/sync_agents.py --root /path/to/project --source-dir shared-agents
```

`--source-dir` 也接受绝对路径。源目录与生成目录不得互相包含，避免再次扫描生成物。
缺失或没有 Markdown 定义的源目录会报错，不会静默成功。

## 生成与覆盖规则

- Pi：`.pi/agents/<name>.md`，包含 YAML name/description 与角色正文。
- Codex：`.codex/agents/<name>.toml`，包含 name、description 和 developer_instructions。
- 生成文件标注由本脚本管理，不手工编辑；修改源文件后重新同步。
- 全部输入及目标覆盖冲突先校验，再开始写入；冲突时不写任何输出。
- 不覆盖没有本脚本标记的手工文件，不通过输出文件或父目录的符号链接写入。
- 内容相同的文件不重写；变化的文件使用同目录临时文件和原子替换，替换失败保留旧文件。
  这是单文件原子性，不是整个批次的事务；写入阶段发生 I/O 故障时可能已有部分文件更新，
  排除故障后重新同步即可收敛。应串行运行同步，不与其它配置写入操作并发。
- 不自动删除旧生成文件。删除或重命名源定义后，需要显式清理对应旧注册文件。

`--check` 只检查当前源定义对应的输出，列出缺失或不同的路径，不创建目录或写文件。
退出码：0 = 已同步/生成成功；1 = 检查发现差异；2 = 输入、冲突或 I/O 错误。
它不负责发现已删除源定义留下的旧文件。

Pi 仍需加载子 Agent 扩展；生成配置不等于安装扩展或运行 Agent。
格式依据：[Pi 子 Agent 示例](https://github.com/earendil-works/pi/tree/main/packages/coding-agent/examples/extensions/subagent)、
[Codex 自定义 Agent](https://learn.chatgpt.com/docs/agent-configuration/subagents)。

## 验证

`backend/core/tests/test_sync_agents.py` 通过真实 CLI 和临时目录验证多角色、嵌套源目录、
YAML/TOML 与正文一致性、输入失败零写入、配置保护、幂等和检查模式；注入替换失败验证
旧文件和临时文件处理。另有仓库源文件的 `--check` 用例，防止改了正文却忘记同步。
这些验证不调用模型，也不代表已运行 Pi/Codex 的真实委派。
