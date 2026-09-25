# computer_use benchmark

- Run label: `local-form-r1-a`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **1/1** (100%, 95% CI 21%–100%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| local-form | 1/1 | 100% | 21%–100% | 14 | 14 | 15 | 15 | 36 | 138574 | 3 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| local-form | 15 | 1.4 | 2.1 | 36 | 0.0 |

- API calls total: 15, mean 2.4s/call, median streamed ttft 1.4, LLM time total 36s

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
      "charged_tokens": 138574,
      "charged_nano_usd": 0,
      "known_tokens": 138574,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 16,
      "admitted_requests": 15
    },
    "trials": {
      "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-a/local-form-r1-a/trials/local-form/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 138574,
        "charged_nano_usd": 0,
        "known_tokens": 138574,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "07913f9a6ecc4b32a844126151f77be2": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-a/local-form-r1-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5144,
        "output_tokens": 43,
        "status": "known"
      },
      "02f202008d6c4a0794ca47007911d774": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-a/local-form-r1-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5218,
        "output_tokens": 13,
        "status": "known"
      },
      "d45b1658243a4d77a25e0bea3b68b6c3": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-a/local-form-r1-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7393,
        "output_tokens": 139,
        "status": "known"
      },
      "8b4113429b2143ff9e22ec7319146518": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-a/local-form-r1-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7577,
        "output_tokens": 85,
        "status": "known"
      },
      "7aba06fe5ee445a88e84a53e87fe41cd": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-a/local-form-r1-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7739,
        "output_tokens": 38,
        "status": "known"
      },
      "461e5c16a0c143598dfd6942b4e1cdb1": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-a/local-form-r1-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7797,
        "output_tokens": 27,
        "status": "known"
      },
      "c95f027339e24cf5a6c188344d8fe4bc": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-a/local-form-r1-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9976,
        "output_tokens": 183,
        "status": "known"
      },
      "5a0cc936a6b24fcf8cf993688e52de9d": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-a/local-form-r1-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10206,
        "output_tokens": 45,
        "status": "known"
      },
      "25a037602f334dcbbc3e6d0b5072d173": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-a/local-form-r1-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10289,
        "output_tokens": 72,
        "status": "known"
      },
      "935c05dde20a43928d620e6493f5b6f8": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-a/local-form-r1-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10408,
        "output_tokens": 49,
        "status": "known"
      },
      "2a599e67997e42e8aacd04dfb892ecc2": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-a/local-form-r1-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10499,
        "output_tokens": 66,
        "status": "known"
      },
      "20ac8f12034e4c1eaa9891b281dd7bd5": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-a/local-form-r1-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10612,
        "output_tokens": 64,
        "status": "known"
      },
      "b90c7fa845a24dd3bba7a519f382f8f8": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-a/local-form-r1-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10723,
        "output_tokens": 105,
        "status": "known"
      },
      "a90846d4c164464db84925a87e0cecf6": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-a/local-form-r1-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10875,
        "output_tokens": 43,
        "status": "known"
      },
      "3365dac4e1ae42799b2bc59ff9f2b4b5": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r1-a/local-form-r1-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 13054,
        "output_tokens": 92,
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
    "planner": 15,
    "locator": 0,
    "total": 15,
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
      "success": true,
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
