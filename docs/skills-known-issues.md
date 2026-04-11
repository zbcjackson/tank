# Skills System — Known Issues

## Fixed Issues

### Issue 1: Fork Sub-Agent Runs Tools Without Approval ✅
**Fix**: Skill fork mode now uses `AgentRunner.run_agent()` which always includes `approval_manager` and `approval_policy`.

### Issue 2: No UI Updates During Fork Execution ✅
**Fix**: `AgentRunner.run_agent()` yields all `AgentOutput` items and posts Bus events for agent lifecycle.

### Issue 3: Socket Permission Error (`Operation not permitted`) ✅
**Root Cause**: The seatbelt sandbox mounts `~` as read-only. `agent-browser` writes its socket to `~/.agent-browser/default.sock` — blocked.
**Fix**: Added `~/.agent-browser` as `rw` mount in `config.yaml` sandbox section.

### Issue 5: YAML Comma-Separated String Parsing ✅
**Fix**: Parser splits comma-separated strings for `allowed-tools`.

### Issue 6: `str(result)` Dumping Python Dict Repr ✅
**Fix**: `LLM.chat_stream()` uses `result["message"]` when available, falls back to `json.dumps`.

### Issue 7: Fork Sub-Agent Re-Delegates Instead of Executing ✅
**Fix**: Skill fork uses `AgentRunner.run_agent()` with `AgentDefinition` that disallows `agent`, `use_skill`, etc. Sub-agent executes directly.

## Open Issues

### Issue 4: `allowed-tools` Format Mismatch
**Status**: Partially addressed. Claude Code-style patterns like `Bash(npx agent-browser:*)` are stored and used as a signal for fork mode. Tank-specific tool filtering by name is deferred — fork sub-agents currently get all tools minus global disallowed set.
