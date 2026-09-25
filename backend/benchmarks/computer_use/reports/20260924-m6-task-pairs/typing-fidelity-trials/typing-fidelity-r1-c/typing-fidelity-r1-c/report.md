# computer_use benchmark

- Run label: `typing-fidelity-r1-c`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| typing-fidelity | 0/1 | 0% | 0%–79% | 15 | 12 | 19 | 15 | 65 | 327668 | 12 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| typing-fidelity | 19 | 2.1 | 3.2 | 65 | 0.0 |

- API calls total: 19, mean 3.4s/call, median streamed ttft 2.1, LLM time total 65s

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
      "charged_tokens": 327668,
      "charged_nano_usd": 0,
      "known_tokens": 327668,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 31,
      "admitted_requests": 19
    },
    "trials": {
      "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r1-c/typing-fidelity-r1-c/trials/typing-fidelity/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 327668,
        "charged_nano_usd": 0,
        "known_tokens": 327668,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "28513922a09b4811b4d4d590a6a022fe": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r1-c/typing-fidelity-r1-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 3927,
        "output_tokens": 60,
        "status": "known"
      },
      "96b3f9a6bcd4431096f25f766c11e2ff": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r1-c/typing-fidelity-r1-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6398,
        "output_tokens": 68,
        "status": "known"
      },
      "08e0a4be6941493fb5cbd28a54d821c4": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r1-c/typing-fidelity-r1-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8887,
        "output_tokens": 124,
        "status": "known"
      },
      "a6e137c26bf84c3aa4e2ac7d7c52c8dc": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r1-c/typing-fidelity-r1-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2506,
        "output_tokens": 52,
        "status": "known"
      },
      "1b73fbb61e8246fa8c3e67d1882b9175": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r1-c/typing-fidelity-r1-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9106,
        "output_tokens": 70,
        "status": "known"
      },
      "1ed6381897a94f7cb1be5bac5701912b": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r1-c/typing-fidelity-r1-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11611,
        "output_tokens": 107,
        "status": "known"
      },
      "4ffa2fd56e9944fb952c9b570491561d": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r1-c/typing-fidelity-r1-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 14128,
        "output_tokens": 87,
        "status": "known"
      },
      "37e53b0b9b394aadb5cf23dcca9ee802": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r1-c/typing-fidelity-r1-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 16645,
        "output_tokens": 67,
        "status": "known"
      },
      "6c5bb22fe5a04a3f903631fe719cff02": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r1-c/typing-fidelity-r1-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 19127,
        "output_tokens": 103,
        "status": "known"
      },
      "4ea652c3cd264326b4fa8793041a7855": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r1-c/typing-fidelity-r1-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 21661,
        "output_tokens": 90,
        "status": "known"
      },
      "da5f66f14bcf4194837279effbf609dd": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r1-c/typing-fidelity-r1-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 24165,
        "output_tokens": 134,
        "status": "known"
      },
      "b4b0dcbb6afe45b78aae43d3ca872dff": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r1-c/typing-fidelity-r1-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2506,
        "output_tokens": 52,
        "status": "known"
      },
      "b0edb4f578664db4bf9f9d6e39de8d59": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r1-c/typing-fidelity-r1-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 24390,
        "output_tokens": 67,
        "status": "known"
      },
      "746cc5bfc38741078e1dd6c8a9b63fab": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r1-c/typing-fidelity-r1-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 26883,
        "output_tokens": 264,
        "status": "known"
      },
      "1e67d7cdad2c4b0b8042177ab176bf5f": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r1-c/typing-fidelity-r1-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 29646,
        "output_tokens": 83,
        "status": "known"
      },
      "25945453f8bf483d9a303abc6774eff0": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r1-c/typing-fidelity-r1-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 32141,
        "output_tokens": 72,
        "status": "known"
      },
      "b64ca787f3c14730bd088aa32531721f": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r1-c/typing-fidelity-r1-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 34706,
        "output_tokens": 158,
        "status": "known"
      },
      "f791dc05df3e423094de28cf4f1c0105": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r1-c/typing-fidelity-r1-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2502,
        "output_tokens": 52,
        "status": "known"
      },
      "746856d0700245b4af3ce79be2e90030": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r1-c/typing-fidelity-r1-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 34957,
        "output_tokens": 66,
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
      "task": "typing-fidelity",
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
      "task": "typing-fidelity",
      "tool_call_limit": 15,
      "timeout_s": 180,
      "gui_only": true
    }
  ]
}
```
