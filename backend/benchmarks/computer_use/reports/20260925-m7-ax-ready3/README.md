# M7 批次 4 重跑材料（v3，schema/JSON 恢复修复后，2026-09-25）

live2 证明宿主自动绑定生效（locate found、点击全部派发），但暴露两类问题：
(a) screenshot schema 暴露的 window_id 诱使模型传入 frame_id（非法 JSON）致
agent 崩溃——已修复：AX 模式 schema 隐藏 window_id + 非法 JSON 参数改为可恢复
工具错误（零派发保持）；(b) 选择器在 57 行候选中选错相邻项（22"10 to the X"
vs 23"7"）——真实模型能力数据，live3 复现则 AX 分支条件性暂缓。

- `../20260925-m7-ax-runtime3/` + `../20260925-m7-ax-proposal3/`：修复后
  重生成（352 文件预检通过）。
- 本目录 launcher：gate 11 / scope 5 全过（sha 一致）；预览（0 模型请求）
  清理全过、外层恢复 confirmed。
- 验收决策：`reviewed-2026-09-25-m7-live2-schema-and-json-recovery-fix`。
- live1+live2 累计 206 请求；live3 为声明新批次（9 trial / ≤234 请求）。
