# computer_use benchmark

- Run label: `small-text-code-r2-c`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| small-text-code | 0/1 | 0% | 0%–79% | 8 | 5 | 11 | 15 | 34 | 110575 | 6 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| small-text-code | 11 | 2.0 | 3.5 | 34 | 0.0 |

- API calls total: 11, mean 3.1s/call, median streamed ttft 2.0, LLM time total 34s

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
      "charged_tokens": 110575,
      "charged_nano_usd": 0,
      "known_tokens": 110575,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 31,
      "admitted_requests": 11
    },
    "trials": {
      "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r2-c/small-text-code-r2-c/trials/small-text-code/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 110575,
        "charged_nano_usd": 0,
        "known_tokens": 110575,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "901f150a65e04e16aeae26693bb8ff45": {
        "trial": "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r2-c/small-text-code-r2-c/trials/small-text-code/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 3885,
        "output_tokens": 43,
        "status": "known"
      },
      "c06e6876b5fc42908354970ce2d1ea9f": {
        "trial": "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r2-c/small-text-code-r2-c/trials/small-text-code/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6348,
        "output_tokens": 43,
        "status": "known"
      },
      "a89e796fc5824cba9bbe6d5111a33be0": {
        "trial": "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r2-c/small-text-code-r2-c/trials/small-text-code/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8781,
        "output_tokens": 205,
        "status": "known"
      },
      "d5d581fea2a3466ba976155ddc613a31": {
        "trial": "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r2-c/small-text-code-r2-c/trials/small-text-code/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10722,
        "output_tokens": 104,
        "status": "known"
      },
      "de6f511ac7c240f9bd8e722f62f734ce": {
        "trial": "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r2-c/small-text-code-r2-c/trials/small-text-code/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2505,
        "output_tokens": 52,
        "status": "known"
      },
      "bf3c6510397e4bb28b6851c3bb38c7a0": {
        "trial": "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r2-c/small-text-code-r2-c/trials/small-text-code/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10914,
        "output_tokens": 73,
        "status": "known"
      },
      "5e31a6fb40784e0fa22dbceafb0cfa1e": {
        "trial": "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r2-c/small-text-code-r2-c/trials/small-text-code/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 13413,
        "output_tokens": 67,
        "status": "known"
      },
      "08a0656527d746d282583c48e05f9219": {
        "trial": "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r2-c/small-text-code-r2-c/trials/small-text-code/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 15897,
        "output_tokens": 112,
        "status": "known"
      },
      "eaa20f5d32934165a50ea16dd23681e0": {
        "trial": "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r2-c/small-text-code-r2-c/trials/small-text-code/1",
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
      "93024bf79fed46729eb15004ad443849": {
        "trial": "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r2-c/small-text-code-r2-c/trials/small-text-code/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 16099,
        "output_tokens": 65,
        "status": "known"
      },
      "48be8f57fb35472f86b25622c6d3021e": {
        "trial": "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r2-c/small-text-code-r2-c/trials/small-text-code/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 18590,
        "output_tokens": 102,
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
    "planner": 9,
    "locator": 2,
    "total": 11,
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
