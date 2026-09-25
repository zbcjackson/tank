# computer_use benchmark

- Run label: `browser-navigate-r2-a`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| browser-navigate | 0/1 | 0% | 0%–79% | 4 | 4 | 5 | 15 | 12 | 35365 | 2 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| browser-navigate | 5 | 1.3 | 2.1 | 12 | 0.0 |

- API calls total: 5, mean 2.4s/call, median streamed ttft 1.3, LLM time total 12s

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
      "charged_tokens": 35365,
      "charged_nano_usd": 0,
      "known_tokens": 35365,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 16,
      "admitted_requests": 5
    },
    "trials": {
      "/private/tmp/tank-m6-browser-navigate-20260925-live/trials/browser-navigate-r2-a/browser-navigate-r2-a/trials/browser-navigate/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 35365,
        "charged_nano_usd": 0,
        "known_tokens": 35365,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "7f3e36a860c94b7cb37484472dc9f5f9": {
        "trial": "/private/tmp/tank-m6-browser-navigate-20260925-live/trials/browser-navigate-r2-a/browser-navigate-r2-a/trials/browser-navigate/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5139,
        "output_tokens": 48,
        "status": "known"
      },
      "13429233b7f24065a7e4b56d9e900932": {
        "trial": "/private/tmp/tank-m6-browser-navigate-20260925-live/trials/browser-navigate-r2-a/browser-navigate-r2-a/trials/browser-navigate/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5218,
        "output_tokens": 13,
        "status": "known"
      },
      "a8891693e3f94eb893bcf244b633a81e": {
        "trial": "/private/tmp/tank-m6-browser-navigate-20260925-live/trials/browser-navigate-r2-a/browser-navigate-r2-a/trials/browser-navigate/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7393,
        "output_tokens": 122,
        "status": "known"
      },
      "ae25ca651b474435895ba26759abec27": {
        "trial": "/private/tmp/tank-m6-browser-navigate-20260925-live/trials/browser-navigate-r2-a/browser-navigate-r2-a/trials/browser-navigate/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7562,
        "output_tokens": 31,
        "status": "known"
      },
      "f9ac3ba0e801488b94d76acd5f1debad": {
        "trial": "/private/tmp/tank-m6-browser-navigate-20260925-live/trials/browser-navigate-r2-a/browser-navigate-r2-a/trials/browser-navigate/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9753,
        "output_tokens": 86,
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
    "planner": 5,
    "locator": 0,
    "total": 5,
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
