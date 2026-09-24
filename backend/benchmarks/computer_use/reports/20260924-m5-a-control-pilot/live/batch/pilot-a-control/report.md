# computer_use benchmark

- Run label: `pilot-a-control`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| calc-open | 0/1 | 0% | 0%–79% | 15 | 9 | 16 | 15 | 108 | 238281 | 9 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| calc-open | 16 | 2.3 | 5.5 | 99 | 0.0 |

- API calls total: 16, mean 6.2s/call, median streamed ttft 2.3, LLM time total 99s

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
    "variant": "A-control",
    "freeze_dir": "/Users/zbcjackson/src/tank/backend/benchmarks/computer_use/reports/20260924-m5-runtime"
  },
  "input_cleanup": true,
  "budget_record_only": true,
  "configured_token_budget": 300000,
  "spend_budget": {
    "record_only": true,
    "cost_status": "unpriced",
    "batch": {
      "limit_tokens": 300000,
      "limit_nano_usd": 8000000000,
      "charged_tokens": 238281,
      "charged_nano_usd": 0,
      "known_tokens": 238281,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 16,
      "admitted_requests": 16
    },
    "trials": {
      "/private/tmp/tank-m5-a-control-20260924-live/batch/pilot-a-control/trials/calc-open/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 238281,
        "charged_nano_usd": 0,
        "known_tokens": 238281,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "ee487f4ca5ab42efb0627c40ae3920c3": {
        "trial": "/private/tmp/tank-m5-a-control-20260924-live/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7067,
        "output_tokens": 60,
        "status": "known"
      },
      "101fff0d00b94341b75b6b245f2bde5c": {
        "trial": "/private/tmp/tank-m5-a-control-20260924-live/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9542,
        "output_tokens": 378,
        "status": "known"
      },
      "d4ae921f611848e293d12d8634d7fce6": {
        "trial": "/private/tmp/tank-m5-a-control-20260924-live/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7517,
        "output_tokens": 290,
        "status": "known"
      },
      "81cb9871fc5040deb5131a9a53762558": {
        "trial": "/private/tmp/tank-m5-a-control-20260924-live/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7836,
        "output_tokens": 72,
        "status": "known"
      },
      "431b0ab2135c4fe98f7250f3b1fdff46": {
        "trial": "/private/tmp/tank-m5-a-control-20260924-live/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7742,
        "output_tokens": 30,
        "status": "known"
      },
      "d636595db82d4fc2a086c283b14fd6e9": {
        "trial": "/private/tmp/tank-m5-a-control-20260924-live/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10146,
        "output_tokens": 198,
        "status": "known"
      },
      "61e0ca0b7a3341d89f818d4c3ebb9d00": {
        "trial": "/private/tmp/tank-m5-a-control-20260924-live/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10372,
        "output_tokens": 30,
        "status": "known"
      },
      "4b6baaf8d5db4792bb0a2739ae007404": {
        "trial": "/private/tmp/tank-m5-a-control-20260924-live/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 12792,
        "output_tokens": 122,
        "status": "known"
      },
      "b0a2d16c83ce444eb378369ac70ca7c2": {
        "trial": "/private/tmp/tank-m5-a-control-20260924-live/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 12970,
        "output_tokens": 421,
        "status": "known"
      },
      "7ca258ae845647eaa4b80f74897bf8d3": {
        "trial": "/private/tmp/tank-m5-a-control-20260924-live/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 12983,
        "output_tokens": 34,
        "status": "known"
      },
      "ca9afbe3d3054d5998593722f5ee4586": {
        "trial": "/private/tmp/tank-m5-a-control-20260924-live/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 15407,
        "output_tokens": 832,
        "status": "known"
      },
      "5383f95b5020430586c2fe7fe8b3c942": {
        "trial": "/private/tmp/tank-m5-a-control-20260924-live/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 18671,
        "output_tokens": 188,
        "status": "known"
      },
      "c4be43f926e14858a470ef38fc588362": {
        "trial": "/private/tmp/tank-m5-a-control-20260924-live/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 21282,
        "output_tokens": 89,
        "status": "known"
      },
      "f280f81fd76548e095b9f7768dcab7d0": {
        "trial": "/private/tmp/tank-m5-a-control-20260924-live/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 23788,
        "output_tokens": 200,
        "status": "known"
      },
      "f9613cd23ead4d62b7e12bd107e360f9": {
        "trial": "/private/tmp/tank-m5-a-control-20260924-live/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 26403,
        "output_tokens": 687,
        "status": "known"
      },
      "c43f1f457a53421285aeccd952c8956b": {
        "trial": "/private/tmp/tank-m5-a-control-20260924-live/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 29524,
        "output_tokens": 608,
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
    "planner": 16,
    "locator": 0,
    "total": 16,
    "blocked": false
  },
  "request_limits": {
    "planner": 16,
    "locator": 0,
    "total": 16
  },
  "grounding": {
    "profile": null,
    "fallback_profile": null,
    "protocol": "legacy",
    "nullable_style": "integer",
    "strict": false,
    "detail": "auto",
    "status_field": false,
    "mode": "integrated",
    "host_restore": false
  },
  "token_budget": 0,
  "platform": "macos",
  "git_revision": "be2c235612561028c8980caa3419f48a872b269e",
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
          "sha256": "c74b64129fd2f1bbdef774203d2b0bfb56f799b2a3654e93884af2f5c2636a40",
          "file": "screenshots/shot_009.png",
          "captured_at": 1790216953.987046,
          "http_serialized_at": 1790216954.012148
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
