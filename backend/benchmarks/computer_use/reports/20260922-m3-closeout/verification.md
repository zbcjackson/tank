# 收尾验证

2026-09-22，代码基线 `6522882`；本次修改只有文档和离线审计档案。

- web `pnpm lint`：通过。
- web `npx tsc -b --noEmit`：通过。
- backend `uv run --no-sync ruff check core/src/ core/tests/`：通过（当前目录布局）。
- backend `uv run --no-sync pytest`：4615 passed、1 skipped、21 warnings，退出 0。
- changed-file pyright：不适用，未修改产品/测试 Python 文件；审计程序以 `.py.txt` 归档并实际执行。
- cli `uv run --no-sync ruff check src/ tests/`：通过。
- dev server `tmux capture-pane -t tank:1.1 -p -S -50 | rg -i 'error|traceback|exception'`：无匹配，检查通过。
- test `pnpm test`：14 scenarios / 55 steps 全部通过，退出 0。
- `python3 scripts/check_docs.py`：通过，37 files。
- `python3 scripts/check_protocol_sync.py`：通过。
- `git diff --check`：通过。
- `python3 backend/benchmarks/computer_use/reports/20260922-m3-closeout/audit.py.txt`：通过，544 份原始响应。

uv 使用 `UV_CACHE_DIR=/tmp/tank-uv-cache`；pytest 使用
`DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`。原始检查输出在同目录 `.txt` 档案。
本次回归不包含新增真实模型请求或桌面动作；历史实验的质量结论以各批原报告为准。
