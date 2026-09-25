# computer_use benchmark

- Run label: `local-form-r2-a`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **1/1** (100%, 95% CI 21%–100%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| local-form | 1/1 | 100% | 21%–100% | 14 | 14 | 15 | 15 | 32 | 136406 | 3 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| local-form | 15 | 1.2 | 1.8 | 32 | 0.0 |

- API calls total: 15, mean 2.1s/call, median streamed ttft 1.2, LLM time total 32s

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
      "charged_tokens": 136406,
      "charged_nano_usd": 0,
      "known_tokens": 136406,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 16,
      "admitted_requests": 15
    },
    "trials": {
      "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r2-a/local-form-r2-a/trials/local-form/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 136406,
        "charged_nano_usd": 0,
        "known_tokens": 136406,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "ed4aba1e5b3747ce83a7ce07a882d7c0": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r2-a/local-form-r2-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5146,
        "output_tokens": 46,
        "status": "known"
      },
      "95a38419bb4a4367b5d6a828e99a5d32": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r2-a/local-form-r2-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5223,
        "output_tokens": 13,
        "status": "known"
      },
      "87261253c3244530aa03a1189798a334": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r2-a/local-form-r2-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7398,
        "output_tokens": 87,
        "status": "known"
      },
      "0af7e5409d17439aaf7c74058d447187": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r2-a/local-form-r2-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7530,
        "output_tokens": 67,
        "status": "known"
      },
      "8694cfb93ae941b0b9f871eccb564a45": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r2-a/local-form-r2-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7676,
        "output_tokens": 26,
        "status": "known"
      },
      "3f008d6b137648e6a0e4ece99c680a56": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r2-a/local-form-r2-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7722,
        "output_tokens": 14,
        "status": "known"
      },
      "af26ecf731c94f17a0ea5376e520b1f3": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r2-a/local-form-r2-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9888,
        "output_tokens": 137,
        "status": "known"
      },
      "a69e5a8a5b224f93a88df2e0dfe5f653": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r2-a/local-form-r2-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10071,
        "output_tokens": 33,
        "status": "known"
      },
      "924fe2798e814e85a8a923e12eb1bc99": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r2-a/local-form-r2-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10142,
        "output_tokens": 52,
        "status": "known"
      },
      "33a4e7ae120e4c279fbc3391303fc8b5": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r2-a/local-form-r2-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10241,
        "output_tokens": 36,
        "status": "known"
      },
      "11a62fc72131443bae2254e950d152ad": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r2-a/local-form-r2-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10319,
        "output_tokens": 52,
        "status": "known"
      },
      "08cff7d8f09e44d5bd5e262f1f0d75dd": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r2-a/local-form-r2-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10418,
        "output_tokens": 41,
        "status": "known"
      },
      "8fc757a7275341ed957fb61930744640": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r2-a/local-form-r2-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10506,
        "output_tokens": 54,
        "status": "known"
      },
      "99d4104e1e61437783db276d749037ce": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r2-a/local-form-r2-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10607,
        "output_tokens": 25,
        "status": "known"
      },
      "aee6932c00cd477aa67e6e57db7c4534": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r2-a/local-form-r2-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 12768,
        "output_tokens": 68,
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
