# computer_use benchmark

- Run label: `multi-select-copy-r1-c`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| multi-select-copy | 0/1 | 0% | 0%–79% | 15 | 3 | 18 | 15 | 58 | 222349 | 6 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| multi-select-copy | 18 | 2.2 | 3.1 | 57 | 0.0 |

- API calls total: 18, mean 3.2s/call, median streamed ttft 2.2, LLM time total 57s

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
      "charged_tokens": 222349,
      "charged_nano_usd": 0,
      "known_tokens": 222349,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 31,
      "admitted_requests": 18
    },
    "trials": {
      "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-c/multi-select-copy-r1-c/trials/multi-select-copy/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 222349,
        "charged_nano_usd": 0,
        "known_tokens": 222349,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "872d521adf824244839c4422f85f47f1": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-c/multi-select-copy-r1-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 3871,
        "output_tokens": 53,
        "status": "known"
      },
      "94bb8ce956fb43a38e9cbb85915cddd6": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-c/multi-select-copy-r1-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6339,
        "output_tokens": 107,
        "status": "known"
      },
      "d5e4b036acc647909ba4e49dd5247d17": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-c/multi-select-copy-r1-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6343,
        "output_tokens": 26,
        "status": "known"
      },
      "5d9b7d462f6d447dbe6f7fd5b644ea40": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-c/multi-select-copy-r1-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8750,
        "output_tokens": 84,
        "status": "known"
      },
      "b591d04b9d334f3fad499acbe73ee2b8": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-c/multi-select-copy-r1-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11245,
        "output_tokens": 113,
        "status": "known"
      },
      "8d83efb4bdd840b98cb339105a638e82": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-c/multi-select-copy-r1-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11389,
        "output_tokens": 83,
        "status": "known"
      },
      "434a127f798f4b0e992d28880e75eccd": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-c/multi-select-copy-r1-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 13210,
        "output_tokens": 113,
        "status": "known"
      },
      "75992a9dbd4240d9bb5091d2c6471c46": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-c/multi-select-copy-r1-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2513,
        "output_tokens": 52,
        "status": "known"
      },
      "578ed29d98324593806577fc3365ee63": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-c/multi-select-copy-r1-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 13414,
        "output_tokens": 66,
        "status": "known"
      },
      "9a2a288253654587a5ded12cd3505822": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-c/multi-select-copy-r1-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 15987,
        "output_tokens": 116,
        "status": "known"
      },
      "e01d6f486c764296b2509a5ec1e916db": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-c/multi-select-copy-r1-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 16125,
        "output_tokens": 66,
        "status": "known"
      },
      "4eef1e93955545ddb83ebab022c4bdb8": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-c/multi-select-copy-r1-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 16249,
        "output_tokens": 80,
        "status": "known"
      },
      "0ea1eb1f719e44af96744eacfe8439bd": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-c/multi-select-copy-r1-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2503,
        "output_tokens": 51,
        "status": "known"
      },
      "85046448760845c58f520f3402c2ced3": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-c/multi-select-copy-r1-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 16423,
        "output_tokens": 68,
        "status": "known"
      },
      "6579dd2c9f764d6ebb3ff6105c7d41a8": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-c/multi-select-copy-r1-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 18982,
        "output_tokens": 99,
        "status": "known"
      },
      "e5726e5d8b5f46fb8d48f7818ac812e5": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-c/multi-select-copy-r1-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 19143,
        "output_tokens": 104,
        "status": "known"
      },
      "830c00a570e449f6ae60ed12ab755940": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-c/multi-select-copy-r1-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 19129,
        "output_tokens": 76,
        "status": "known"
      },
      "b45c5089c1d24a7482e690e71d3901a1": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-c/multi-select-copy-r1-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 19272,
        "output_tokens": 105,
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
    "planner": 16,
    "locator": 2,
    "total": 18,
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
  "git_revision": "12dde91ea02ed19aea3975ac835264e8625da77a",
  "task_revision": "9442074589754111c1b5273dc1048298b42e78f3b0d48695373c30fe975004ee",
  "scoring_revision": "trial-token-gui-grounding-v5",
  "aborted_cleanup": false,
  "outcomes": [
    {
      "task": "multi-select-copy",
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
      "task": "multi-select-copy",
      "tool_call_limit": 15,
      "timeout_s": 180,
      "gui_only": true
    }
  ]
}
```
