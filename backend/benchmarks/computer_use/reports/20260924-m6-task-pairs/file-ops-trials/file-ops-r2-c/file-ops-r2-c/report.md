# computer_use benchmark

- Run label: `file-ops-r2-c`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| file-ops | 0/1 | 0% | 0%–79% | 15 | 9 | 19 | 15 | 62 | 254936 | 9 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| file-ops | 19 | 1.9 | 3.3 | 62 | 0.0 |

- API calls total: 19, mean 3.2s/call, median streamed ttft 1.9, LLM time total 62s

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
      "charged_tokens": 254936,
      "charged_nano_usd": 0,
      "known_tokens": 254936,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 31,
      "admitted_requests": 19
    },
    "trials": {
      "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r2-c/file-ops-r2-c/trials/file-ops/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 254936,
        "charged_nano_usd": 0,
        "known_tokens": 254936,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "90dd03c63e164959addcfa92da21bc4c": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r2-c/file-ops-r2-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 3857,
        "output_tokens": 114,
        "status": "known"
      },
      "897cb81f333b4504bff96723100ec8ab": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r2-c/file-ops-r2-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6385,
        "output_tokens": 81,
        "status": "known"
      },
      "d7d062d1cbe4416999673eb09ed8df35": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r2-c/file-ops-r2-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6363,
        "output_tokens": 35,
        "status": "known"
      },
      "ccd1d5f178f744b1a25e7861e56a1a1f": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r2-c/file-ops-r2-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8783,
        "output_tokens": 103,
        "status": "known"
      },
      "b7e33c4f32bf414480913b8956d543a3": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r2-c/file-ops-r2-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2503,
        "output_tokens": 52,
        "status": "known"
      },
      "546168aa36244171bee1dffc1e16aed4": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r2-c/file-ops-r2-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8979,
        "output_tokens": 79,
        "status": "known"
      },
      "485c0db7b4b84c148841e540b51be54c": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r2-c/file-ops-r2-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11479,
        "output_tokens": 102,
        "status": "known"
      },
      "40f52a0673034f9680e7e5b4f4efcb90": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r2-c/file-ops-r2-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 14000,
        "output_tokens": 74,
        "status": "known"
      },
      "a92dd607022b432bb46a07276b62fd2b": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r2-c/file-ops-r2-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 14136,
        "output_tokens": 32,
        "status": "known"
      },
      "cd921a10270646be8be666d5b400d053": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r2-c/file-ops-r2-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 16555,
        "output_tokens": 125,
        "status": "known"
      },
      "d59f2583e6664324a9ddc2f7331ca584": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r2-c/file-ops-r2-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 16738,
        "output_tokens": 31,
        "status": "known"
      },
      "8c98834ec9ea480592856c1188f6beb0": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r2-c/file-ops-r2-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 19153,
        "output_tokens": 81,
        "status": "known"
      },
      "6dc069d72e6840539258d4ff4b6d9974": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r2-c/file-ops-r2-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 21645,
        "output_tokens": 108,
        "status": "known"
      },
      "444d94c66e9343e4ad08bbff89008147": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r2-c/file-ops-r2-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2510,
        "output_tokens": 52,
        "status": "known"
      },
      "71ce1e97266b487a83220327bcc559dd": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r2-c/file-ops-r2-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 21843,
        "output_tokens": 73,
        "status": "known"
      },
      "3ad7e944019c451eaf1d266879cd5d7d": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r2-c/file-ops-r2-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 24337,
        "output_tokens": 198,
        "status": "known"
      },
      "c4a1ac1f6c43432794c6c4bd2644ae1c": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r2-c/file-ops-r2-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2504,
        "output_tokens": 48,
        "status": "known"
      },
      "d842c50a6eec49faaf54ada4b1a0a620": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r2-c/file-ops-r2-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 24588,
        "output_tokens": 40,
        "status": "known"
      },
      "bef5aeab63a8401b858409f342b389ed": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r2-c/file-ops-r2-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 27014,
        "output_tokens": 136,
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
    "locator": 3,
    "total": 19,
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
      "task": "file-ops",
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
      "task": "file-ops",
      "tool_call_limit": 15,
      "timeout_s": 180,
      "gui_only": true
    }
  ]
}
```
