# computer_use benchmark

- Run label: `links-history-r3-a`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| links-history | 0/1 | 0% | 0%–79% | 10 | 10 | 11 | 15 | 25 | 83811 | 2 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| links-history | 11 | 1.2 | 1.8 | 25 | 0.0 |

- API calls total: 11, mean 2.2s/call, median streamed ttft 1.2, LLM time total 25s

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
      "charged_tokens": 83811,
      "charged_nano_usd": 0,
      "known_tokens": 83811,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 16,
      "admitted_requests": 11
    },
    "trials": {
      "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r3-a/links-history-r3-a/trials/links-history/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 83811,
        "charged_nano_usd": 0,
        "known_tokens": 83811,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "df70131518874a7f8112c87f6f765016": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r3-a/links-history-r3-a/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5171,
        "output_tokens": 57,
        "status": "known"
      },
      "0c5fa3c2e56349d18ba2f38510fe56c4": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r3-a/links-history-r3-a/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5259,
        "output_tokens": 13,
        "status": "known"
      },
      "0bd5b42fbd134dd7923794163b716079": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r3-a/links-history-r3-a/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7434,
        "output_tokens": 123,
        "status": "known"
      },
      "fd334d0489124e66a5c36f24e97f399a": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r3-a/links-history-r3-a/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7604,
        "output_tokens": 44,
        "status": "known"
      },
      "d3be349c89ba4d489885d5d88f39ea61": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r3-a/links-history-r3-a/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7670,
        "output_tokens": 61,
        "status": "known"
      },
      "d6706bd78f4f4a13b58c6e7a39e460af": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r3-a/links-history-r3-a/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7778,
        "output_tokens": 45,
        "status": "known"
      },
      "d5fcac9b4db54a7ba9f20abd86f1aa02": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r3-a/links-history-r3-a/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7845,
        "output_tokens": 61,
        "status": "known"
      },
      "9d63bcd0f1bd43c6ae94dadfd07a3a6b": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r3-a/links-history-r3-a/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7953,
        "output_tokens": 45,
        "status": "known"
      },
      "f6d0137e70ed4a1ab283b4b69c417282": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r3-a/links-history-r3-a/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8020,
        "output_tokens": 63,
        "status": "known"
      },
      "641031e909e44d20826d13ca1ab6ea15": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r3-a/links-history-r3-a/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8130,
        "output_tokens": 21,
        "status": "known"
      },
      "656623ec01724d9e8ce8cd05a7449a4d": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r3-a/links-history-r3-a/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10287,
        "output_tokens": 127,
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
    "planner": 11,
    "locator": 0,
    "total": 11,
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
      "task": "links-history",
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
      "task": "links-history",
      "tool_call_limit": 15,
      "timeout_s": 180,
      "gui_only": true
    }
  ]
}
```
