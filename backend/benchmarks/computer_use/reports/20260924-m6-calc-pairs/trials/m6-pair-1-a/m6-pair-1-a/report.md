# computer_use benchmark

- Run label: `m6-pair-1-a`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| calc-open | 0/1 | 0% | 0%–79% | 15 | 10 | 16 | 15 | 49 | 128142 | 3 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| calc-open | 16 | 1.3 | 2.2 | 40 | 0.0 |

- API calls total: 16, mean 2.5s/call, median streamed ttft 1.3, LLM time total 40s

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
      "charged_tokens": 128142,
      "charged_nano_usd": 0,
      "known_tokens": 128142,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 16,
      "admitted_requests": 16
    },
    "trials": {
      "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-a/m6-pair-1-a/trials/calc-open/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 128142,
        "charged_nano_usd": 0,
        "known_tokens": 128142,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "18ac6358e1dc4caa930b8129f9aa68d6": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-a/m6-pair-1-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5095,
        "output_tokens": 27,
        "status": "known"
      },
      "c6de543ffc3743458ef00bd100c58941": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-a/m6-pair-1-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5152,
        "output_tokens": 13,
        "status": "known"
      },
      "21d1312d88c5469f9c108d504a55807b": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-a/m6-pair-1-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7327,
        "output_tokens": 258,
        "status": "known"
      },
      "19aa73ee5b574ecea58496a1b8b89c6c": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-a/m6-pair-1-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7302,
        "output_tokens": 144,
        "status": "known"
      },
      "d3d8582e97484b318d6d18e12f264856": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-a/m6-pair-1-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7475,
        "output_tokens": 59,
        "status": "known"
      },
      "2c1e728d6a104fb0800463346b25075c": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-a/m6-pair-1-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6878,
        "output_tokens": 82,
        "status": "known"
      },
      "cf7d18e517694cde92a621a0ec746572": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-a/m6-pair-1-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6550,
        "output_tokens": 181,
        "status": "known"
      },
      "4e96609881ee497598b518e1d4364d73": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-a/m6-pair-1-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6779,
        "output_tokens": 58,
        "status": "known"
      },
      "2ee82b9f53da41d7abf31beaf5cf553d": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-a/m6-pair-1-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6952,
        "output_tokens": 210,
        "status": "known"
      },
      "49d019e4604c4fbaaf9d9b043752f1d1": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-a/m6-pair-1-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7210,
        "output_tokens": 48,
        "status": "known"
      },
      "17c6ffe6981a42ad960616bcb6a9a027": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-a/m6-pair-1-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9394,
        "output_tokens": 118,
        "status": "known"
      },
      "6538b12fe77d4959a95e79d15022299e": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-a/m6-pair-1-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9549,
        "output_tokens": 40,
        "status": "known"
      },
      "ac88f8a4074f4b469d41d205902d03fb": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-a/m6-pair-1-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9627,
        "output_tokens": 38,
        "status": "known"
      },
      "7f54e668788a41958fc65310975495c2": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-a/m6-pair-1-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9702,
        "output_tokens": 36,
        "status": "known"
      },
      "2487b4436c9645ce8d6abe608a57f0b8": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-a/m6-pair-1-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9774,
        "output_tokens": 25,
        "status": "known"
      },
      "e0c451cc33cc431a910882e152fa0cbd": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-a/m6-pair-1-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11947,
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
  "grounding": null,
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
          "result": "78"
        },
        "last_screenshot": {
          "sha256": "6fa8a6f37bb526b631536fee3b00ff2afb3e3d8408558f86f9b3768d09fa4cc3",
          "file": "screenshots/shot_003.png",
          "captured_at": 1790260752.116544,
          "http_serialized_at": 1790260752.1272051
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
