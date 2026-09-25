# computer_use benchmark

- Run label: `editor-save-r3-c`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| editor-save | 0/1 | 0% | 0%–79% | 15 | 7 | 19 | 15 | 72 | 250237 | 8 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| editor-save | 19 | 2.1 | 3.4 | 71 | 0.0 |

- API calls total: 19, mean 3.8s/call, median streamed ttft 2.1, LLM time total 71s

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
      "charged_tokens": 250237,
      "charged_nano_usd": 0,
      "known_tokens": 250237,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 31,
      "admitted_requests": 19
    },
    "trials": {
      "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r3-c/editor-save-r3-c/trials/editor-save/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 250237,
        "charged_nano_usd": 0,
        "known_tokens": 250237,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "e7d89d14ba174315b5ebe4724e7dd435": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r3-c/editor-save-r3-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 3844,
        "output_tokens": 90,
        "status": "known"
      },
      "1b192567d6c749daa1623092dfa12478": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r3-c/editor-save-r3-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6349,
        "output_tokens": 133,
        "status": "known"
      },
      "61a532259c10408ea010f74e30ee9873": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r3-c/editor-save-r3-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8977,
        "output_tokens": 105,
        "status": "known"
      },
      "47b517faa36549d890ca4bb54ad56d05": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r3-c/editor-save-r3-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10822,
        "output_tokens": 93,
        "status": "known"
      },
      "25eeb7cc87c24703b0041a77cefb1163": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r3-c/editor-save-r3-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2501,
        "output_tokens": 51,
        "status": "known"
      },
      "70bf85426a4140d69dd5284d8b9d8397": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r3-c/editor-save-r3-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11011,
        "output_tokens": 79,
        "status": "known"
      },
      "7b0bcc35448e4e869787b2a4ddc8839f": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r3-c/editor-save-r3-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 13427,
        "output_tokens": 223,
        "status": "known"
      },
      "4feb14a64d704c92b366fca65af83fb5": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r3-c/editor-save-r3-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 13674,
        "output_tokens": 99,
        "status": "known"
      },
      "ee11163ff3124fc891a8c8b71ae849d0": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r3-c/editor-save-r3-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 13835,
        "output_tokens": 33,
        "status": "known"
      },
      "9bcb20f646bd4556be4522adb6f3b132": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r3-c/editor-save-r3-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 16251,
        "output_tokens": 211,
        "status": "known"
      },
      "f5d40f6b7efd4afabd282d47a239dd2c": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r3-c/editor-save-r3-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2507,
        "output_tokens": 48,
        "status": "known"
      },
      "cf8972eeb81c432fb24c46318b3d725b": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r3-c/editor-save-r3-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 16521,
        "output_tokens": 92,
        "status": "known"
      },
      "c55ec5c0eac648b398a4ff7c6238cf5d": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r3-c/editor-save-r3-c/trials/editor-save/1",
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
      "38f57903031c489c8ec70861fbdcbe56": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r3-c/editor-save-r3-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 16672,
        "output_tokens": 86,
        "status": "known"
      },
      "c5b82f4ea7e945c8803c7f72c3df084a": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r3-c/editor-save-r3-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 19163,
        "output_tokens": 131,
        "status": "known"
      },
      "785ba85da0784c67bb5581aca3983624": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r3-c/editor-save-r3-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 21732,
        "output_tokens": 173,
        "status": "known"
      },
      "8bd11ced34f54ef88fc63c91496927c8": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r3-c/editor-save-r3-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 21934,
        "output_tokens": 89,
        "status": "known"
      },
      "98a236f011c5452488b5d70ef45dc1f1": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r3-c/editor-save-r3-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 22080,
        "output_tokens": 51,
        "status": "known"
      },
      "a85c090c869342d9b895a1805b1a1b2e": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r3-c/editor-save-r3-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 24531,
        "output_tokens": 67,
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
  "git_revision": "12dde91ea02ed19aea3975ac835264e8625da77a",
  "task_revision": "9442074589754111c1b5273dc1048298b42e78f3b0d48695373c30fe975004ee",
  "scoring_revision": "trial-token-gui-grounding-v5",
  "aborted_cleanup": false,
  "outcomes": [
    {
      "task": "editor-save",
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
      "task": "editor-save",
      "tool_call_limit": 15,
      "timeout_s": 180,
      "gui_only": true
    }
  ]
}
```
