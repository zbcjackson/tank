# computer_use benchmark

- Run label: `terminal-write-r3-a`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **1/1** (100%, 95% CI 21%–100%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| terminal-write | 1/1 | 100% | 21%–100% | 6 | 6 | 7 | 15 | 16 | 50554 | 2 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| terminal-write | 7 | 1.4 | 2.2 | 16 | 0.0 |

- API calls total: 7, mean 2.3s/call, median streamed ttft 1.4, LLM time total 16s

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
      "charged_tokens": 50554,
      "charged_nano_usd": 0,
      "known_tokens": 50554,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 16,
      "admitted_requests": 7
    },
    "trials": {
      "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r3-a/terminal-write-r3-a/trials/terminal-write/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 50554,
        "charged_nano_usd": 0,
        "known_tokens": 50554,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "fda85fbbd08d4abda6f3ed491e360a01": {
        "trial": "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r3-a/terminal-write-r3-a/trials/terminal-write/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5100,
        "output_tokens": 48,
        "status": "known"
      },
      "1089350d376b4e60abf771b5df88542d": {
        "trial": "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r3-a/terminal-write-r3-a/trials/terminal-write/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5178,
        "output_tokens": 13,
        "status": "known"
      },
      "5ec82c4cb0484d6d8c3cf48b5e51ba36": {
        "trial": "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r3-a/terminal-write-r3-a/trials/terminal-write/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7353,
        "output_tokens": 89,
        "status": "known"
      },
      "fea9983b12c34f009df6b2c24c7d5a87": {
        "trial": "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r3-a/terminal-write-r3-a/trials/terminal-write/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7490,
        "output_tokens": 48,
        "status": "known"
      },
      "dbdb5ee1aea248b08212b5968e5434de": {
        "trial": "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r3-a/terminal-write-r3-a/trials/terminal-write/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7585,
        "output_tokens": 37,
        "status": "known"
      },
      "176866b001f84128b5f102148f490680": {
        "trial": "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r3-a/terminal-write-r3-a/trials/terminal-write/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7642,
        "output_tokens": 29,
        "status": "known"
      },
      "61e022fb2cf04f1894f9b7859a4e7675": {
        "trial": "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r3-a/terminal-write-r3-a/trials/terminal-write/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9823,
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
