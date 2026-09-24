# computer_use benchmark

- Run label: `m6-pair-3-c`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| calc-open | 0/1 | 0% | 0%–79% | 15 | 4 | 19 | 15 | 69 | 147097 | 4 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| calc-open | 19 | 1.3 | 3.5 | 60 | 0.0 |

- API calls total: 19, mean 3.2s/call, median streamed ttft 1.3, LLM time total 60s

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
      "charged_tokens": 147097,
      "charged_nano_usd": 0,
      "known_tokens": 147097,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 31,
      "admitted_requests": 19
    },
    "trials": {
      "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-c/m6-pair-3-c/trials/calc-open/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 147097,
        "charged_nano_usd": 0,
        "known_tokens": 147097,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "69dbe879ee6b4e7e81a60aab6155dacd": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-c/m6-pair-3-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 3828,
        "output_tokens": 131,
        "status": "known"
      },
      "84f12136232e4187b07f4959ea6d36b9": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-c/m6-pair-3-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6373,
        "output_tokens": 363,
        "status": "known"
      },
      "47e5657950cc4de9acc83fbb0965b82d": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-c/m6-pair-3-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6061,
        "output_tokens": 259,
        "status": "known"
      },
      "f04f2f9f26e94b45acbe47e949743eb5": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-c/m6-pair-3-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6348,
        "output_tokens": 90,
        "status": "known"
      },
      "ac3101497dff45d981550e62bbb6ff50": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-c/m6-pair-3-c/trials/calc-open/1",
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
      "c3988f4b89d947038bed0b41e76b51fd": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-c/m6-pair-3-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6528,
        "output_tokens": 80,
        "status": "known"
      },
      "c376c52aa6f14cd0b6e788ef618881f6": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-c/m6-pair-3-c/trials/calc-open/1",
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
      "161f090665a3407f8dacd1ed44cc4f13": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-c/m6-pair-3-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6698,
        "output_tokens": 80,
        "status": "known"
      },
      "ec634a27c5f14a99a313d7c62f5b42bd": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-c/m6-pair-3-c/trials/calc-open/1",
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
      "7079fdfd45cb448fa57659a26ebdf7bf": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-c/m6-pair-3-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6866,
        "output_tokens": 80,
        "status": "known"
      },
      "37c3480ffa9b4372bc554ebcfd2c098d": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-c/m6-pair-3-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6832,
        "output_tokens": 39,
        "status": "known"
      },
      "4159ff2cda0e4c7ea7121d2ac1da8413": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-c/m6-pair-3-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9242,
        "output_tokens": 136,
        "status": "known"
      },
      "924d51c26c9f4d06834aa7ca204be785": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-c/m6-pair-3-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9409,
        "output_tokens": 91,
        "status": "known"
      },
      "462c07dd990a4799a39ae0b8898bc568": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-c/m6-pair-3-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9558,
        "output_tokens": 187,
        "status": "known"
      },
      "35295e58c1a74fee899ec0686f78dd86": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-c/m6-pair-3-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10492,
        "output_tokens": 190,
        "status": "known"
      },
      "b40de531827d4efc9e11d8e03d3d29d2": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-c/m6-pair-3-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10579,
        "output_tokens": 97,
        "status": "known"
      },
      "b1a3aeffdba84dc7ac9dbbb58a769d12": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-c/m6-pair-3-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10734,
        "output_tokens": 287,
        "status": "known"
      },
      "df9000460e0342ed9d4690771d9113b8": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-c/m6-pair-3-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 13402,
        "output_tokens": 362,
        "status": "known"
      },
      "9f1f970a2ce740bd9bb4a3b985edf8c5": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-c/m6-pair-3-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 13788,
        "output_tokens": 231,
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
  "git_revision": "b6a04c23be5f835822ab25486b81df84df67379b",
  "task_revision": "a4cdec43b05afd51461bbb2dd695a77f79d71ea87bfb785634d0b8c0092647c8",
  "scoring_revision": "trial-token-gui-grounding-v5",
  "aborted_cleanup": false,
  "outcomes": [
    {
      "task": "calc-open",
      "trial": 1,
      "stop_reason": null,
      "cleanup": "confirmed",
      "scoring": "strict",
      "success": false,
      "unknown_calls": 0,
      "assessment": {
        "revision": "calc-evidence-v1",
        "strict_expression": false,
        "business": null,
        "mouse_only": null,
        "pixels": "unknown",
        "reset_verified": true,
        "input_trace_complete": false,
        "display": {
          "result": "0"
        },
        "last_screenshot": {
          "sha256": "70eec35aa0f06525205640c28de1b8dca3cd804f44c0afb16f87804f30e98705",
          "file": "screenshots/shot_004.png",
          "captured_at": 1790261262.123198,
          "http_serialized_at": 1790261266.843194
        }
      }
    }
  ],
  "limits": [
    {
      "task": "calc-open",
      "tool_call_limit": 15,
      "timeout_s": 120,
      "gui_only": true
    }
  ]
}
```
