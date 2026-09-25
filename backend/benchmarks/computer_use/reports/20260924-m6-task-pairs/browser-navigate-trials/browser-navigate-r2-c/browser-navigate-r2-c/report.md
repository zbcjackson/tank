# computer_use benchmark

- Run label: `browser-navigate-r2-c`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| browser-navigate | 0/1 | 0% | 0%–79% | 4 | 3 | 6 | 15 | 17 | 42664 | 3 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| browser-navigate | 6 | 1.4 | 2.6 | 17 | 0.0 |

- API calls total: 6, mean 2.8s/call, median streamed ttft 1.4, LLM time total 17s

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
    "freeze_dir": "/Users/zbcjackson/src/tank/backend/benchmarks/computer_use/reports/20260924-m6-calc-runtime"
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
      "charged_tokens": 42664,
      "charged_nano_usd": 0,
      "known_tokens": 42664,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 31,
      "admitted_requests": 6
    },
    "trials": {
      "/private/tmp/tank-m6-browser-navigate-20260925-live/trials/browser-navigate-r2-c/browser-navigate-r2-c/trials/browser-navigate/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 42664,
        "charged_nano_usd": 0,
        "known_tokens": 42664,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "a3f1b33188d0421580490ae3fefc8f84": {
        "trial": "/private/tmp/tank-m6-browser-navigate-20260925-live/trials/browser-navigate-r2-c/browser-navigate-r2-c/trials/browser-navigate/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 3869,
        "output_tokens": 84,
        "status": "known"
      },
      "1062bb16a1b74d068ef4ae80081ec4e1": {
        "trial": "/private/tmp/tank-m6-browser-navigate-20260925-live/trials/browser-navigate-r2-c/browser-navigate-r2-c/trials/browser-navigate/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6367,
        "output_tokens": 56,
        "status": "known"
      },
      "02d37b3114dd4ce592ccfd77d53b2fa3": {
        "trial": "/private/tmp/tank-m6-browser-navigate-20260925-live/trials/browser-navigate-r2-c/browser-navigate-r2-c/trials/browser-navigate/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8811,
        "output_tokens": 143,
        "status": "known"
      },
      "8a1b1ada86b145dcbcd4bdf105121e86": {
        "trial": "/private/tmp/tank-m6-browser-navigate-20260925-live/trials/browser-navigate-r2-c/browser-navigate-r2-c/trials/browser-navigate/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2502,
        "output_tokens": 52,
        "status": "known"
      },
      "6aac897c42284db0951587c8797c701e": {
        "trial": "/private/tmp/tank-m6-browser-navigate-20260925-live/trials/browser-navigate-r2-c/browser-navigate-r2-c/trials/browser-navigate/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9045,
        "output_tokens": 66,
        "status": "known"
      },
      "ffe47e6ad415417aaa89d2676c8df8d9": {
        "trial": "/private/tmp/tank-m6-browser-navigate-20260925-live/trials/browser-navigate-r2-c/browser-navigate-r2-c/trials/browser-navigate/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11533,
        "output_tokens": 136,
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
    "planner": 5,
    "locator": 1,
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
  "git_revision": "91877d76c39906ffcd486b37f4c077c32d2587af",
  "task_revision": "9442074589754111c1b5273dc1048298b42e78f3b0d48695373c30fe975004ee",
  "scoring_revision": "trial-token-gui-grounding-v5",
  "aborted_cleanup": false,
  "outcomes": [
    {
      "task": "browser-navigate",
      "trial": 1,
      "stop_reason": null,
      "cleanup": "confirmed",
      "scoring": "strict",
      "success": false,
      "unknown_calls": 0,
      "assessment": {}
    }
  ],
  "limits": [
    {
      "task": "browser-navigate",
      "tool_call_limit": 15,
      "timeout_s": 180,
      "gui_only": true
    }
  ]
}
```
