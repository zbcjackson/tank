# computer_use benchmark

- Run label: `local-form-r3-c`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| local-form | 0/1 | 0% | 0%–79% | 15 | 11 | 20 | 15 | 58 | 301259 | 11 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| local-form | 20 | 2.1 | 2.8 | 57 | 0.0 |

- API calls total: 20, mean 2.9s/call, median streamed ttft 2.1, LLM time total 57s

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
      "charged_tokens": 301259,
      "charged_nano_usd": 0,
      "known_tokens": 301259,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 31,
      "admitted_requests": 20
    },
    "trials": {
      "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-c/local-form-r3-c/trials/local-form/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 301259,
        "charged_nano_usd": 0,
        "known_tokens": 301259,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "7812382a12124389afd343ff9a2f3ff8": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-c/local-form-r3-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 3883,
        "output_tokens": 48,
        "status": "known"
      },
      "e6ffe4a03aa2466b81ff0d05f043c6a8": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-c/local-form-r3-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6349,
        "output_tokens": 37,
        "status": "known"
      },
      "ede2d0db96c34b839e380a802ec4d470": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-c/local-form-r3-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8777,
        "output_tokens": 152,
        "status": "known"
      },
      "f4b7d45cfc53490d82272b3abd4a3aa1": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-c/local-form-r3-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2500,
        "output_tokens": 51,
        "status": "known"
      },
      "70065699627d4a8ca8381ad96c518e82": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-c/local-form-r3-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9020,
        "output_tokens": 69,
        "status": "known"
      },
      "ebb9f71365d14a68847f25a6dcaec465": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-c/local-form-r3-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11522,
        "output_tokens": 92,
        "status": "known"
      },
      "8eebb0ff51e1496f8ad5be9a0b31da40": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-c/local-form-r3-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 14043,
        "output_tokens": 45,
        "status": "known"
      },
      "9b0c2201f2984b68b9e1e5ad5bb0e979": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-c/local-form-r3-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 16497,
        "output_tokens": 188,
        "status": "known"
      },
      "a2f79c785bec48c6b8342b0a01d88101": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-c/local-form-r3-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2507,
        "output_tokens": 52,
        "status": "known"
      },
      "0bc2c24e42814b8cb34458d01b96fdcf": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-c/local-form-r3-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 16774,
        "output_tokens": 66,
        "status": "known"
      },
      "2ffd3e2cb0cb44b29d4544e0ec54c958": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-c/local-form-r3-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 19257,
        "output_tokens": 45,
        "status": "known"
      },
      "b961a1b8d8804844a8ef73204771f6d6": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-c/local-form-r3-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 21722,
        "output_tokens": 94,
        "status": "known"
      },
      "e483f231339a439182988012e6ff9074": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-c/local-form-r3-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2507,
        "output_tokens": 52,
        "status": "known"
      },
      "6d50ec8df041494b8c494be4a27d45fe": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-c/local-form-r3-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 21908,
        "output_tokens": 69,
        "status": "known"
      },
      "fcc41397932a42d19cc100579bc3eaa9": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-c/local-form-r3-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 24403,
        "output_tokens": 48,
        "status": "known"
      },
      "29c35b35e5eb41f0b69e642a7edc7db9": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-c/local-form-r3-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 26867,
        "output_tokens": 112,
        "status": "known"
      },
      "d29fe4f0fb1e4358b61475320ee3ef95": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-c/local-form-r3-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2509,
        "output_tokens": 52,
        "status": "known"
      },
      "54d75b75b9b24b7885186523f3edf8c2": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-c/local-form-r3-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 27072,
        "output_tokens": 68,
        "status": "known"
      },
      "234d8c4546864b48b8569c196f2a1bd7": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-c/local-form-r3-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 29560,
        "output_tokens": 64,
        "status": "known"
      },
      "ee5dba2610ad42528973630b8c86bfa0": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-c/local-form-r3-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 32050,
        "output_tokens": 128,
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
    "locator": 4,
    "total": 20,
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
      "task": "local-form",
      "trial": 1,
      "stop_reason": "budget",
      "cleanup": "confirmed",
      "scoring": "strict",
      "success": false,
      "unknown_calls": 0,
      "assessment": {}
    }
  ],
  "limits": [
    {
      "task": "local-form",
      "tool_call_limit": 15,
      "timeout_s": 180,
      "gui_only": true
    }
  ]
}
```
