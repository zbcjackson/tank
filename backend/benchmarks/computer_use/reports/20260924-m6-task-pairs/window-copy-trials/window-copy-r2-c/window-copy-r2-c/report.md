# computer_use benchmark

- Run label: `window-copy-r2-c`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| window-copy | 0/1 | 0% | 0%–79% | 15 | 8 | 18 | 15 | 60 | 271121 | 9 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| window-copy | 18 | 2.1 | 3.4 | 59 | 0.0 |

- API calls total: 18, mean 3.3s/call, median streamed ttft 2.1, LLM time total 59s

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
      "charged_tokens": 271121,
      "charged_nano_usd": 0,
      "known_tokens": 271121,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 31,
      "admitted_requests": 18
    },
    "trials": {
      "/private/tmp/tank-m6-window-copy-20260925-live/trials/window-copy-r2-c/window-copy-r2-c/trials/window-copy/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 271121,
        "charged_nano_usd": 0,
        "known_tokens": 271121,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "fdc39cde2c2d4433979eac4b6dacf24d": {
        "trial": "/private/tmp/tank-m6-window-copy-20260925-live/trials/window-copy-r2-c/window-copy-r2-c/trials/window-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 3901,
        "output_tokens": 48,
        "status": "known"
      },
      "bb6b24b81a8a4f959e6160830d01b1aa": {
        "trial": "/private/tmp/tank-m6-window-copy-20260925-live/trials/window-copy-r2-c/window-copy-r2-c/trials/window-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6363,
        "output_tokens": 109,
        "status": "known"
      },
      "581673b698a04730ac7b98e0b843f64d": {
        "trial": "/private/tmp/tank-m6-window-copy-20260925-live/trials/window-copy-r2-c/window-copy-r2-c/trials/window-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8211,
        "output_tokens": 59,
        "status": "known"
      },
      "c9efad9622ff4b11960e971510f912eb": {
        "trial": "/private/tmp/tank-m6-window-copy-20260925-live/trials/window-copy-r2-c/window-copy-r2-c/trials/window-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10681,
        "output_tokens": 39,
        "status": "known"
      },
      "fb6362b3603540cfaf77bcfa6b27ca9b": {
        "trial": "/private/tmp/tank-m6-window-copy-20260925-live/trials/window-copy-r2-c/window-copy-r2-c/trials/window-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 13106,
        "output_tokens": 91,
        "status": "known"
      },
      "f821dc66ff3447c7b59228523224dd37": {
        "trial": "/private/tmp/tank-m6-window-copy-20260925-live/trials/window-copy-r2-c/window-copy-r2-c/trials/window-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 13094,
        "output_tokens": 35,
        "status": "known"
      },
      "910264f3814743c59ccb57b838617d8a": {
        "trial": "/private/tmp/tank-m6-window-copy-20260925-live/trials/window-copy-r2-c/window-copy-r2-c/trials/window-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 15515,
        "output_tokens": 72,
        "status": "known"
      },
      "02f1cc2edf2c4c88af41c7bd3f516ad5": {
        "trial": "/private/tmp/tank-m6-window-copy-20260925-live/trials/window-copy-r2-c/window-copy-r2-c/trials/window-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 15611,
        "output_tokens": 97,
        "status": "known"
      },
      "9d1e1b74767a4690981970d063093450": {
        "trial": "/private/tmp/tank-m6-window-copy-20260925-live/trials/window-copy-r2-c/window-copy-r2-c/trials/window-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2504,
        "output_tokens": 52,
        "status": "known"
      },
      "23317a1f2e4e4830940e1ac0913d23a9": {
        "trial": "/private/tmp/tank-m6-window-copy-20260925-live/trials/window-copy-r2-c/window-copy-r2-c/trials/window-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 15799,
        "output_tokens": 75,
        "status": "known"
      },
      "db499cd0dadb4f5a99ebcfc2d674fa9f": {
        "trial": "/private/tmp/tank-m6-window-copy-20260925-live/trials/window-copy-r2-c/window-copy-r2-c/trials/window-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 18299,
        "output_tokens": 134,
        "status": "known"
      },
      "586277e70bcc47c999cf62b3bd43bdf3": {
        "trial": "/private/tmp/tank-m6-window-copy-20260925-live/trials/window-copy-r2-c/window-copy-r2-c/trials/window-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 20514,
        "output_tokens": 166,
        "status": "known"
      },
      "5255b0efb30d459bb8705503c3d141fe": {
        "trial": "/private/tmp/tank-m6-window-copy-20260925-live/trials/window-copy-r2-c/window-copy-r2-c/trials/window-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 23080,
        "output_tokens": 121,
        "status": "known"
      },
      "f200565249f548208ad13bf0f2731e04": {
        "trial": "/private/tmp/tank-m6-window-copy-20260925-live/trials/window-copy-r2-c/window-copy-r2-c/trials/window-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 23125,
        "output_tokens": 32,
        "status": "known"
      },
      "33f885150d294b06acc3d5742953f406": {
        "trial": "/private/tmp/tank-m6-window-copy-20260925-live/trials/window-copy-r2-c/window-copy-r2-c/trials/window-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 25541,
        "output_tokens": 150,
        "status": "known"
      },
      "94d7c1ed1a344deb9a592c7c5cc2de04": {
        "trial": "/private/tmp/tank-m6-window-copy-20260925-live/trials/window-copy-r2-c/window-copy-r2-c/trials/window-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 25749,
        "output_tokens": 132,
        "status": "known"
      },
      "aa85210c7c78479a982ae861f8584256": {
        "trial": "/private/tmp/tank-m6-window-copy-20260925-live/trials/window-copy-r2-c/window-copy-r2-c/trials/window-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2508,
        "output_tokens": 52,
        "status": "known"
      },
      "a796c6446d88452c8b6a9b22f9663f93": {
        "trial": "/private/tmp/tank-m6-window-copy-20260925-live/trials/window-copy-r2-c/window-copy-r2-c/trials/window-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 25976,
        "output_tokens": 80,
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
    "locator": 2,
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
  "git_revision": "12dde91ea02ed19aea3975ac835264e8625da77a",
  "task_revision": "9442074589754111c1b5273dc1048298b42e78f3b0d48695373c30fe975004ee",
  "scoring_revision": "trial-token-gui-grounding-v5",
  "aborted_cleanup": false,
  "outcomes": [
    {
      "task": "window-copy",
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
      "task": "window-copy",
      "tool_call_limit": 15,
      "timeout_s": 180,
      "gui_only": true
    }
  ]
}
```
