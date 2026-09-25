# computer_use benchmark

- Run label: `terminal-write-r2-c`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **1/1** (100%, 95% CI 21%–100%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| terminal-write | 1/1 | 100% | 21%–100% | 5 | 4 | 6 | 15 | 22 | 50278 | 4 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| terminal-write | 6 | 2.4 | 3.4 | 22 | 0.0 |

- API calls total: 6, mean 3.6s/call, median streamed ttft 2.4, LLM time total 22s

## Run metadata

```json
{
  "agent_name": "computer_use",
  "engine": null,
  "extension": null,
  "config": {
    "model": "qwen3.7-flash-2026-07-15"
  },
  "prompt_revision": "929bdb4162b475c28e0212d3c6c200a5af93366c6f0f279066ba245a53f17945",
  "comparison_contract": {
    "variant": "C",
    "freeze_dir": "/Users/zbcjackson/src/tank/backend/benchmarks/computer_use/reports/20260925-m6-tasks-runtime"
  },
  "input_cleanup": true,
  "budget_record_only": true,
  "agent_budget_enforced": true,
  "configured_token_budget": 300000,
  "spend_budget": {
    "record_only": true,
    "cost_status": "unpriced",
    "batch": {
      "limit_tokens": 300000,
      "limit_nano_usd": 8000000000,
      "charged_tokens": 50278,
      "charged_nano_usd": 0,
      "known_tokens": 50278,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 31,
      "admitted_requests": 6
    },
    "trials": {
      "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r2-c/terminal-write-r2-c/trials/terminal-write/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 50278,
        "charged_nano_usd": 0,
        "known_tokens": 50278,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "04b6e5252e724206a7b64540fb16fc38": {
        "trial": "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r2-c/terminal-write-r2-c/trials/terminal-write/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 3833,
        "output_tokens": 43,
        "status": "known"
      },
      "a5f3dec992764731b89b4cb7c7231747": {
        "trial": "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r2-c/terminal-write-r2-c/trials/terminal-write/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6293,
        "output_tokens": 88,
        "status": "known"
      },
      "245e305155c8467c9e8e4801b676b10d": {
        "trial": "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r2-c/terminal-write-r2-c/trials/terminal-write/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6278,
        "output_tokens": 23,
        "status": "known"
      },
      "65d20bfddb5d43e391c1ed0141176407": {
        "trial": "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r2-c/terminal-write-r2-c/trials/terminal-write/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8692,
        "output_tokens": 64,
        "status": "known"
      },
      "2fe8e3aa669a4770a443059fd4fa324b": {
        "trial": "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r2-c/terminal-write-r2-c/trials/terminal-write/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11172,
        "output_tokens": 59,
        "status": "known"
      },
      "40cd37c07e7c4346938a40cb0a7dbb9d": {
        "trial": "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r2-c/terminal-write-r2-c/trials/terminal-write/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 13648,
        "output_tokens": 85,
        "status": "known"
      }
    }
  },
  "request_budget": {
    "limits": {
      "planner": 16,
      "locator": 15,
      "total": 31
    },
    "planner": 6,
    "locator": 0,
    "total": 6,
    "blocked": false
  },
  "request_limits": {
    "planner": 16,
    "locator": 15,
    "total": 31
  },
  "grounding": {
    "profile": null,
    "fallback_profile": null,
    "protocol": "point",
    "nullable_style": "integer",
    "strict": false,
    "detail": "auto",
    "status_field": false,
    "mode": "split",
    "host_restore": true
  },
  "token_budget": 300000,
  "platform": "macos",
  "git_revision": "12dde91ea02ed19aea3975ac835264e8625da77a",
  "task_revision": "9442074589754111c1b5273dc1048298b42e78f3b0d48695373c30fe975004ee",
  "scoring_revision": "trial-token-gui-grounding-v5",
  "aborted_cleanup": false,
  "outcomes": [
    {
      "task": "terminal-write",
      "trial": 1,
      "stop_reason": null,
      "cleanup": "confirmed",
      "scoring": "strict",
      "success": true,
      "unknown_calls": 0,
      "assessment": {}
    }
  ],
  "limits": [
    {
      "task": "terminal-write",
      "tool_call_limit": 15,
      "timeout_s": 120,
      "gui_only": true
    }
  ]
}
```
