# computer_use benchmark

- Run label: `settings-toggle-r2-a`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **1/1** (100%, 95% CI 21%–100%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| settings-toggle | 1/1 | 100% | 21%–100% | 6 | 6 | 7 | 15 | 19 | 56943 | 3 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| settings-toggle | 7 | 1.7 | 2.6 | 18 | 0.0 |

- API calls total: 7, mean 2.6s/call, median streamed ttft 1.7, LLM time total 18s

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
    "variant": "A",
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
      "charged_tokens": 56943,
      "charged_nano_usd": 0,
      "known_tokens": 56943,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 16,
      "admitted_requests": 7
    },
    "trials": {
      "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r2-a/settings-toggle-r2-a/trials/settings-toggle/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 56943,
        "charged_nano_usd": 0,
        "known_tokens": 56943,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "f0d26b0b7d444885ab597515f88fbfc7": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r2-a/settings-toggle-r2-a/trials/settings-toggle/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5086,
        "output_tokens": 47,
        "status": "known"
      },
      "b189880c999d48fe8e9e5119e00d31ff": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r2-a/settings-toggle-r2-a/trials/settings-toggle/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5164,
        "output_tokens": 13,
        "status": "known"
      },
      "3d67bcb8d8b4419e80342de63073210e": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r2-a/settings-toggle-r2-a/trials/settings-toggle/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7339,
        "output_tokens": 82,
        "status": "known"
      },
      "4f28694b89434c59963232e78490a91e": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r2-a/settings-toggle-r2-a/trials/settings-toggle/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7468,
        "output_tokens": 30,
        "status": "known"
      },
      "23bb6111875841ec99cef813f392404b": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r2-a/settings-toggle-r2-a/trials/settings-toggle/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9658,
        "output_tokens": 103,
        "status": "known"
      },
      "0667c49b3a0949ef91fb338b9c7c0fe6": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r2-a/settings-toggle-r2-a/trials/settings-toggle/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9809,
        "output_tokens": 28,
        "status": "known"
      },
      "2e4695c97960409ebe33d8a7655f2ec5": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r2-a/settings-toggle-r2-a/trials/settings-toggle/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11997,
        "output_tokens": 119,
        "status": "known"
      }
    }
  },
  "request_budget": {
    "limits": {
      "planner": 16,
      "locator": 0,
      "total": 16
    },
    "planner": 7,
    "locator": 0,
    "total": 7,
    "blocked": false
  },
  "request_limits": {
    "planner": 16,
    "locator": 0,
    "total": 16
  },
  "grounding": null,
  "token_budget": 300000,
  "platform": "macos",
  "git_revision": "12dde91ea02ed19aea3975ac835264e8625da77a",
  "task_revision": "9442074589754111c1b5273dc1048298b42e78f3b0d48695373c30fe975004ee",
  "scoring_revision": "trial-token-gui-grounding-v5",
  "aborted_cleanup": false,
  "outcomes": [
    {
      "task": "settings-toggle",
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
      "task": "settings-toggle",
      "tool_call_limit": 15,
      "timeout_s": 180,
      "gui_only": true
    }
  ]
}
```
