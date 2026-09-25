# computer_use benchmark

- Run label: `settings-toggle-r1-c`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **1/1** (100%, 95% CI 21%–100%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| settings-toggle | 1/1 | 100% | 21%–100% | 12 | 9 | 15 | 15 | 54 | 212496 | 9 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| settings-toggle | 15 | 2.5 | 3.5 | 53 | 0.0 |

- API calls total: 15, mean 3.5s/call, median streamed ttft 2.5, LLM time total 53s

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
      "charged_tokens": 212496,
      "charged_nano_usd": 0,
      "known_tokens": 212496,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 31,
      "admitted_requests": 15
    },
    "trials": {
      "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r1-c/settings-toggle-r1-c/trials/settings-toggle/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 212496,
        "charged_nano_usd": 0,
        "known_tokens": 212496,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "c68f0269e3194baba9d8fa1dcf21ce97": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r1-c/settings-toggle-r1-c/trials/settings-toggle/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 3819,
        "output_tokens": 93,
        "status": "known"
      },
      "ed3294a23d464866b991109f50ca47f3": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r1-c/settings-toggle-r1-c/trials/settings-toggle/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6328,
        "output_tokens": 46,
        "status": "known"
      },
      "31ea19e937464360ae1ea05b323fd117": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r1-c/settings-toggle-r1-c/trials/settings-toggle/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8804,
        "output_tokens": 50,
        "status": "known"
      },
      "e453ffdc572f4920a5f0207294a54250": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r1-c/settings-toggle-r1-c/trials/settings-toggle/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11272,
        "output_tokens": 37,
        "status": "known"
      },
      "3a1cfcb36cd544f1aacdcef3d3bad2fc": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r1-c/settings-toggle-r1-c/trials/settings-toggle/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 13701,
        "output_tokens": 61,
        "status": "known"
      },
      "4aebae8ca07c4489907ed358793243aa": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r1-c/settings-toggle-r1-c/trials/settings-toggle/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 13659,
        "output_tokens": 24,
        "status": "known"
      },
      "3ff1277acdfa446dbebb1c565b393937": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r1-c/settings-toggle-r1-c/trials/settings-toggle/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 16069,
        "output_tokens": 55,
        "status": "known"
      },
      "164d960c175040b6a9db496e5539128c": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r1-c/settings-toggle-r1-c/trials/settings-toggle/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 18538,
        "output_tokens": 144,
        "status": "known"
      },
      "cf18dc60d30140c385e1cd8d9c0782d7": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r1-c/settings-toggle-r1-c/trials/settings-toggle/1",
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
      "314a795d605c46b59037f4a7d005a44d": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r1-c/settings-toggle-r1-c/trials/settings-toggle/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 18773,
        "output_tokens": 66,
        "status": "known"
      },
      "793c89232a1347359e691dc4ed578cf9": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r1-c/settings-toggle-r1-c/trials/settings-toggle/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 21268,
        "output_tokens": 62,
        "status": "known"
      },
      "41db0222bf6d43498493403484cb9490": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r1-c/settings-toggle-r1-c/trials/settings-toggle/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 23725,
        "output_tokens": 156,
        "status": "known"
      },
      "fea11b99bcb8459bb67f4f829783a3cf": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r1-c/settings-toggle-r1-c/trials/settings-toggle/1",
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
      "bf67b3eceef24e60b8cdc348fbf6330f": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r1-c/settings-toggle-r1-c/trials/settings-toggle/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 23975,
        "output_tokens": 73,
        "status": "known"
      },
      "fe9a6779ed8b4e638609dcd55d92e5f3": {
        "trial": "/private/tmp/tank-m6-settings-toggle-20260925-live/trials/settings-toggle-r1-c/settings-toggle-r1-c/trials/settings-toggle/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 26474,
        "output_tokens": 111,
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
    "planner": 13,
    "locator": 2,
    "total": 15,
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
      "task": "settings-toggle",
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
      "task": "settings-toggle",
      "tool_call_limit": 15,
      "timeout_s": 180,
      "gui_only": true
    }
  ]
}
```
