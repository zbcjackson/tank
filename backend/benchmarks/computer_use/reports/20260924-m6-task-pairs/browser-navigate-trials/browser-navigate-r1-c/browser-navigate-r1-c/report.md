# computer_use benchmark

- Run label: `browser-navigate-r1-c`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| browser-navigate | 0/1 | 0% | 0%–79% | 4 | 3 | 6 | 15 | 17 | 42732 | 3 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| browser-navigate | 6 | 1.4 | 3.0 | 17 | 0.0 |

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
      "charged_tokens": 42732,
      "charged_nano_usd": 0,
      "known_tokens": 42732,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 31,
      "admitted_requests": 6
    },
    "trials": {
      "/private/tmp/tank-m6-browser-navigate-20260925-live/trials/browser-navigate-r1-c/browser-navigate-r1-c/trials/browser-navigate/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 42732,
        "charged_nano_usd": 0,
        "known_tokens": 42732,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "6952e9b9995e47be878a10b4d52bb2dc": {
        "trial": "/private/tmp/tank-m6-browser-navigate-20260925-live/trials/browser-navigate-r1-c/browser-navigate-r1-c/trials/browser-navigate/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 3872,
        "output_tokens": 84,
        "status": "known"
      },
      "4d8fb4bb19554978b4868befca4df8d1": {
        "trial": "/private/tmp/tank-m6-browser-navigate-20260925-live/trials/browser-navigate-r1-c/browser-navigate-r1-c/trials/browser-navigate/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6370,
        "output_tokens": 56,
        "status": "known"
      },
      "d057ec5227a643f2a4018291b3febce2": {
        "trial": "/private/tmp/tank-m6-browser-navigate-20260925-live/trials/browser-navigate-r1-c/browser-navigate-r1-c/trials/browser-navigate/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8816,
        "output_tokens": 147,
        "status": "known"
      },
      "e0eb5e3a27d5438cadf3df304fe250f2": {
        "trial": "/private/tmp/tank-m6-browser-navigate-20260925-live/trials/browser-navigate-r1-c/browser-navigate-r1-c/trials/browser-navigate/1",
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
      "92527a81a1704ae097d452ee6f277276": {
        "trial": "/private/tmp/tank-m6-browser-navigate-20260925-live/trials/browser-navigate-r1-c/browser-navigate-r1-c/trials/browser-navigate/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9055,
        "output_tokens": 68,
        "status": "known"
      },
      "0872478153bd4608b3bc3572ed94eb62": {
        "trial": "/private/tmp/tank-m6-browser-navigate-20260925-live/trials/browser-navigate-r1-c/browser-navigate-r1-c/trials/browser-navigate/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11540,
        "output_tokens": 170,
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
