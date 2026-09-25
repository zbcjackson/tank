# computer_use benchmark

- Run label: `settings-toggle-r1-a`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **1/1** (100%, 95% CI 21%–100%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| settings-toggle | 1/1 | 100% | 21%–100% | 7 | 6 | 8 | 15 | 22 | 65243 | 3 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| settings-toggle | 8 | 1.7 | 2.6 | 21 | 0.0 |

- API calls total: 8, mean 2.6s/call, median streamed ttft 1.7, LLM time total 21s

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
      "charged_tokens": 65243,
      "charged_nano_usd": 0,
      "known_tokens": 65243,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 16,
      "admitted_requests": 8
    },
    "trials": {
      "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r1-a/settings-toggle-r1-a/trials/settings-toggle/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 65243,
        "charged_nano_usd": 0,
        "known_tokens": 65243,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "2b25b22061a046d2a872ed3d6f313b6b": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r1-a/settings-toggle-r1-a/trials/settings-toggle/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5086,
        "output_tokens": 59,
        "status": "known"
      },
      "fff6c1bf46dc4f3b83b6478a4fab55e6": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r1-a/settings-toggle-r1-a/trials/settings-toggle/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5176,
        "output_tokens": 13,
        "status": "known"
      },
      "8d401be459534d4d9a8efa1a5a6217ef": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r1-a/settings-toggle-r1-a/trials/settings-toggle/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7351,
        "output_tokens": 97,
        "status": "known"
      },
      "27920efb24544222813400cde0c773a8": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r1-a/settings-toggle-r1-a/trials/settings-toggle/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7495,
        "output_tokens": 30,
        "status": "known"
      },
      "a357f89a8be54571a222f43c1e32e446": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r1-a/settings-toggle-r1-a/trials/settings-toggle/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9685,
        "output_tokens": 137,
        "status": "known"
      },
      "35c62f44a2da454e8d2152add814788e": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r1-a/settings-toggle-r1-a/trials/settings-toggle/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9130,
        "output_tokens": 111,
        "status": "known"
      },
      "8bec8927d47f4b788d497e7eadfab7c8": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r1-a/settings-toggle-r1-a/trials/settings-toggle/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9289,
        "output_tokens": 27,
        "status": "known"
      },
      "3c9c8beb061540bd9995e1fca6a69118": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r1-a/settings-toggle-r1-a/trials/settings-toggle/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11472,
        "output_tokens": 85,
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
    "planner": 8,
    "locator": 0,
    "total": 8,
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
