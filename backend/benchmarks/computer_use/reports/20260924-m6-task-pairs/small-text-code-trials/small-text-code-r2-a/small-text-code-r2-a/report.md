# computer_use benchmark

- Run label: `small-text-code-r2-a`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| small-text-code | 0/1 | 0% | 0%–79% | 4 | 9 | 5 | 15 | 16 | 38092 | 3 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| small-text-code | 5 | 2.1 | 3.4 | 15 | 0.0 |

- API calls total: 5, mean 3.1s/call, median streamed ttft 2.1, LLM time total 15s

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
      "charged_tokens": 38092,
      "charged_nano_usd": 0,
      "known_tokens": 38092,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 16,
      "admitted_requests": 5
    },
    "trials": {
      "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r2-a/small-text-code-r2-a/trials/small-text-code/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 38092,
        "charged_nano_usd": 0,
        "known_tokens": 38092,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "43abeda2f6bc411c826a14dad99ab7bd": {
        "trial": "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r2-a/small-text-code-r2-a/trials/small-text-code/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5150,
        "output_tokens": 43,
        "status": "known"
      },
      "0ab829179f4a4a768173719e22d67821": {
        "trial": "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r2-a/small-text-code-r2-a/trials/small-text-code/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5224,
        "output_tokens": 129,
        "status": "known"
      },
      "8aa17bd92c70428286f89879befe8eb9": {
        "trial": "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r2-a/small-text-code-r2-a/trials/small-text-code/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7590,
        "output_tokens": 95,
        "status": "known"
      },
      "6fc6bae6bdff47b1acaadce0219b7971": {
        "trial": "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r2-a/small-text-code-r2-a/trials/small-text-code/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8592,
        "output_tokens": 162,
        "status": "known"
      },
      "e312c83050444422b502ec33b6a9e2d5": {
        "trial": "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r2-a/small-text-code-r2-a/trials/small-text-code/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11010,
        "output_tokens": 97,
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
  "git_revision": "12dde91ea02ed19aea3975ac835264e8625da77a",
  "task_revision": "9442074589754111c1b5273dc1048298b42e78f3b0d48695373c30fe975004ee",
  "scoring_revision": "trial-token-gui-grounding-v5",
  "aborted_cleanup": false,
  "outcomes": [
    {
      "task": "small-text-code",
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
      "task": "small-text-code",
      "tool_call_limit": 15,
      "timeout_s": 180,
      "gui_only": true
    }
  ]
}
```
