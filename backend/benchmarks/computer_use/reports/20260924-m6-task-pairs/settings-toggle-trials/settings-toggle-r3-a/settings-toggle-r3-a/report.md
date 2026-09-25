# computer_use benchmark

- Run label: `settings-toggle-r3-a`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **1/1** (100%, 95% CI 21%–100%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| settings-toggle | 1/1 | 100% | 21%–100% | 6 | 6 | 7 | 15 | 19 | 57119 | 3 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| settings-toggle | 7 | 1.6 | 2.4 | 18 | 0.0 |

- API calls total: 7, mean 2.6s/call, median streamed ttft 1.6, LLM time total 18s

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
      "charged_tokens": 57119,
      "charged_nano_usd": 0,
      "known_tokens": 57119,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 16,
      "admitted_requests": 7
    },
    "trials": {
      "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r3-a/settings-toggle-r3-a/trials/settings-toggle/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 57119,
        "charged_nano_usd": 0,
        "known_tokens": 57119,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "06987ee50b5b4a81b91459655bc627ba": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r3-a/settings-toggle-r3-a/trials/settings-toggle/1",
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
      "2935866f740a4c3b9d122b72d9ebba30": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r3-a/settings-toggle-r3-a/trials/settings-toggle/1",
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
      "83ab9ed3d80447e98f90c80820fa7b4e": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r3-a/settings-toggle-r3-a/trials/settings-toggle/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7351,
        "output_tokens": 96,
        "status": "known"
      },
      "b5647b7a6d314b8bbe80b799a22bf55b": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r3-a/settings-toggle-r3-a/trials/settings-toggle/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7494,
        "output_tokens": 30,
        "status": "known"
      },
      "4eff60d15bee47d6983921385261187a": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r3-a/settings-toggle-r3-a/trials/settings-toggle/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9684,
        "output_tokens": 110,
        "status": "known"
      },
      "06f1f038b50d4be59dc2b36eabc0047c": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r3-a/settings-toggle-r3-a/trials/settings-toggle/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9842,
        "output_tokens": 27,
        "status": "known"
      },
      "9465d18ed71c4b82bb674347afcefd5b": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r3-a/settings-toggle-r3-a/trials/settings-toggle/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 12029,
        "output_tokens": 122,
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
