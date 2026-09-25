# computer_use benchmark

- Run label: `local-form-r1-c`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| local-form | 0/1 | 0% | 0%–79% | 13 | 9 | 18 | 15 | 46 | 231833 | 9 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| local-form | 18 | 2.0 | 2.7 | 46 | 0.0 |

- API calls total: 18, mean 2.5s/call, median streamed ttft 2.0, LLM time total 46s

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
      "charged_tokens": 231833,
      "charged_nano_usd": 0,
      "known_tokens": 231833,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 31,
      "admitted_requests": 18
    },
    "trials": {
      "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-c/local-form-r1-c/trials/local-form/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 231833,
        "charged_nano_usd": 0,
        "known_tokens": 231833,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "bdb3b3a3d7824291b173a5586efdabc8": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-c/local-form-r1-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 3881,
        "output_tokens": 50,
        "status": "known"
      },
      "aebcde0709474262a78ebec5037660e0": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-c/local-form-r1-c/trials/local-form/1",
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
      "b293152fe2bd4d73accb431872399dd1": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-c/local-form-r1-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8777,
        "output_tokens": 142,
        "status": "known"
      },
      "ab4c61609f5d41cfbd07168ef5593eb6": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-c/local-form-r1-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2501,
        "output_tokens": 52,
        "status": "known"
      },
      "61fa969146ef4448ad39534255f50ccb": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-c/local-form-r1-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9014,
        "output_tokens": 73,
        "status": "known"
      },
      "76d1884d89cb4ca0ad9bdaa50f310d9a": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-c/local-form-r1-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11513,
        "output_tokens": 46,
        "status": "known"
      },
      "fd14b5bb9ae6434dbcbcb747e7fe775f": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-c/local-form-r1-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 13988,
        "output_tokens": 86,
        "status": "known"
      },
      "29c503e43de347929328272ee14461ff": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-c/local-form-r1-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2501,
        "output_tokens": 52,
        "status": "known"
      },
      "f87ef98e52cf47ad92c5dfee9bb4d680": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-c/local-form-r1-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 14165,
        "output_tokens": 69,
        "status": "known"
      },
      "5dae56f2805e48a5a508aa3d8e5c5ea5": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-c/local-form-r1-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 16659,
        "output_tokens": 61,
        "status": "known"
      },
      "348d667b043a41a49bed2581deac64e4": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-c/local-form-r1-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 19144,
        "output_tokens": 105,
        "status": "known"
      },
      "ae98aff5e52e49a58882a145a0298c34": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-c/local-form-r1-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2501,
        "output_tokens": 52,
        "status": "known"
      },
      "9485e7ab198648d29c549ac4ec217609": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-c/local-form-r1-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 19343,
        "output_tokens": 67,
        "status": "known"
      },
      "8ae1506aa1344d7cb1692493b2c01339": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-c/local-form-r1-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 21824,
        "output_tokens": 65,
        "status": "known"
      },
      "25cd54ef3b414591ad2c67ed7070b868": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-c/local-form-r1-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 24310,
        "output_tokens": 119,
        "status": "known"
      },
      "6f6b530779334ea0be169ce3385dc359": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-c/local-form-r1-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2500,
        "output_tokens": 52,
        "status": "known"
      },
      "bd6b53bbc32a40b98efa93237f58d41e": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-c/local-form-r1-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 24521,
        "output_tokens": 65,
        "status": "known"
      },
      "1f45ca88e9c24b3faca4ab2d3398f4e7": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-c/local-form-r1-c/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 27015,
        "output_tokens": 134,
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
    "planner": 14,
    "locator": 4,
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
  "git_revision": "91877d76c39906ffcd486b37f4c077c32d2587af",
  "task_revision": "9442074589754111c1b5273dc1048298b42e78f3b0d48695373c30fe975004ee",
  "scoring_revision": "trial-token-gui-grounding-v5",
  "aborted_cleanup": false,
  "outcomes": [
    {
      "task": "local-form",
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
      "task": "local-form",
      "tool_call_limit": 15,
      "timeout_s": 180,
      "gui_only": true
    }
  ]
}
```
