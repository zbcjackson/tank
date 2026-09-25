# computer_use benchmark

- Run label: `terminal-write-r2-a`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **1/1** (100%, 95% CI 21%–100%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| terminal-write | 1/1 | 100% | 21%–100% | 7 | 6 | 8 | 15 | 20 | 68034 | 3 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| terminal-write | 8 | 1.9 | 2.4 | 20 | 0.0 |

- API calls total: 8, mean 2.5s/call, median streamed ttft 1.9, LLM time total 20s

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
      "charged_tokens": 68034,
      "charged_nano_usd": 0,
      "known_tokens": 68034,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 16,
      "admitted_requests": 8
    },
    "trials": {
      "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r2-a/terminal-write-r2-a/trials/terminal-write/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 68034,
        "charged_nano_usd": 0,
        "known_tokens": 68034,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "369a26de367a4de1989b6d19b436f863": {
        "trial": "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r2-a/terminal-write-r2-a/trials/terminal-write/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5100,
        "output_tokens": 27,
        "status": "known"
      },
      "1bb112fba34b438ca0537742afd22932": {
        "trial": "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r2-a/terminal-write-r2-a/trials/terminal-write/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5157,
        "output_tokens": 13,
        "status": "known"
      },
      "f284c1ec6163444382c626133e3fa987": {
        "trial": "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r2-a/terminal-write-r2-a/trials/terminal-write/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7332,
        "output_tokens": 141,
        "status": "known"
      },
      "0b4d32e83ac94e01b4233a2084b67bee": {
        "trial": "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r2-a/terminal-write-r2-a/trials/terminal-write/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9382,
        "output_tokens": 76,
        "status": "known"
      },
      "f83b1ca54c064112aa49d04adc3979b5": {
        "trial": "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r2-a/terminal-write-r2-a/trials/terminal-write/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9506,
        "output_tokens": 47,
        "status": "known"
      },
      "1f771d8731944b4dbab87e4b3e589c5b": {
        "trial": "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r2-a/terminal-write-r2-a/trials/terminal-write/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9600,
        "output_tokens": 37,
        "status": "known"
      },
      "76623a46c3094b76b1b64cfec1158ff7": {
        "trial": "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r2-a/terminal-write-r2-a/trials/terminal-write/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9657,
        "output_tokens": 28,
        "status": "known"
      },
      "350ee6264b574ea5819af504509ea879": {
        "trial": "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r2-a/terminal-write-r2-a/trials/terminal-write/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11837,
        "output_tokens": 94,
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
