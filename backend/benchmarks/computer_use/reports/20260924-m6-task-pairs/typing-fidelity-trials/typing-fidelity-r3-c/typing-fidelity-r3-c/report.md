# computer_use benchmark

- Run label: `typing-fidelity-r3-c`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **1/1** (100%, 95% CI 21%–100%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| typing-fidelity | 1/1 | 100% | 21%–100% | 13 | 9 | 17 | 15 | 56 | 238705 | 9 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| typing-fidelity | 17 | 2.2 | 3.3 | 56 | 0.0 |

- API calls total: 17, mean 3.3s/call, median streamed ttft 2.2, LLM time total 56s

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
      "charged_tokens": 238705,
      "charged_nano_usd": 0,
      "known_tokens": 238705,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 31,
      "admitted_requests": 17
    },
    "trials": {
      "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r3-c/typing-fidelity-r3-c/trials/typing-fidelity/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 238705,
        "charged_nano_usd": 0,
        "known_tokens": 238705,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "2bb35092c09d46d683904af7e267f0cd": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r3-c/typing-fidelity-r3-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 3931,
        "output_tokens": 45,
        "status": "known"
      },
      "6899b300541b41da873bf1b2421b5703": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r3-c/typing-fidelity-r3-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6386,
        "output_tokens": 52,
        "status": "known"
      },
      "cb2878e0190747f68da49e2d415dfd85": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r3-c/typing-fidelity-r3-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8850,
        "output_tokens": 105,
        "status": "known"
      },
      "3661acb140284981a5b2970efdc8e94c": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r3-c/typing-fidelity-r3-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11373,
        "output_tokens": 93,
        "status": "known"
      },
      "5d751054e6a64663882d866a02a1337b": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r3-c/typing-fidelity-r3-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 13887,
        "output_tokens": 39,
        "status": "known"
      },
      "087d1bad493848acbc731b5a423742ce": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r3-c/typing-fidelity-r3-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 16337,
        "output_tokens": 167,
        "status": "known"
      },
      "d65e48895c774369ac58c21f8d331060": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r3-c/typing-fidelity-r3-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2516,
        "output_tokens": 48,
        "status": "known"
      },
      "05da106b629340ae80706b66dd49df46": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r3-c/typing-fidelity-r3-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 16561,
        "output_tokens": 74,
        "status": "known"
      },
      "271353baf3f34f5799b7a37ad4500ec0": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r3-c/typing-fidelity-r3-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 16532,
        "output_tokens": 23,
        "status": "known"
      },
      "a6ea7cb5051b44b38b5a0aa37e18148b": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r3-c/typing-fidelity-r3-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 18929,
        "output_tokens": 127,
        "status": "known"
      },
      "9287a0fee3c24e528703893fd4632693": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r3-c/typing-fidelity-r3-c/trials/typing-fidelity/1",
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
      "c525de28a47e4aff9e8161d08d4811a5": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r3-c/typing-fidelity-r3-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 19144,
        "output_tokens": 74,
        "status": "known"
      },
      "3e578f17993541739aebd555a64befcf": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r3-c/typing-fidelity-r3-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 21648,
        "output_tokens": 188,
        "status": "known"
      },
      "e2abcb2f34774e03b832fb07af139738": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r3-c/typing-fidelity-r3-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 24333,
        "output_tokens": 170,
        "status": "known"
      },
      "56f3da36874e4704bcef2dcc719554db": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r3-c/typing-fidelity-r3-c/trials/typing-fidelity/1",
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
      "bf1ed47ed83f4069bc7d72037f687325": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r3-c/typing-fidelity-r3-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 24592,
        "output_tokens": 63,
        "status": "known"
      },
      "59bd09e2d05f468eaee68347ffd93ff7": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r3-c/typing-fidelity-r3-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 27079,
        "output_tokens": 218,
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
    "locator": 3,
    "total": 17,
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
      "task": "typing-fidelity",
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
      "task": "typing-fidelity",
      "tool_call_limit": 15,
      "timeout_s": 180,
      "gui_only": true
    }
  ]
}
```
