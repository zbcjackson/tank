# computer_use benchmark

- Run label: `m6-pair-2-c`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| calc-open | 0/1 | 0% | 0%–79% | 15 | 6 | 21 | 15 | 61 | 178866 | 6 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| calc-open | 21 | 1.4 | 2.1 | 51 | 0.0 |

- API calls total: 21, mean 2.4s/call, median streamed ttft 1.4, LLM time total 51s

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
      "charged_tokens": 178866,
      "charged_nano_usd": 0,
      "known_tokens": 178866,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 31,
      "admitted_requests": 21
    },
    "trials": {
      "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-c/m6-pair-2-c/trials/calc-open/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 178866,
        "charged_nano_usd": 0,
        "known_tokens": 178866,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "3c089824cf044fab87b316ed1d40a6c9": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-c/m6-pair-2-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 3828,
        "output_tokens": 54,
        "status": "known"
      },
      "5bfc20de507640a295d0f34f9659551e": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-c/m6-pair-2-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6295,
        "output_tokens": 157,
        "status": "known"
      },
      "8695b69b3be747fead6f9397eed37a6a": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-c/m6-pair-2-c/trials/calc-open/1",
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
      "2ec84a131de64837aadfe7d28646116a": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-c/m6-pair-2-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6546,
        "output_tokens": 122,
        "status": "known"
      },
      "99d54397bdaa43bbb6fce2511a511232": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-c/m6-pair-2-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5993,
        "output_tokens": 93,
        "status": "known"
      },
      "30f5f5f1408347ecafeaa8f9bb7c4be5": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-c/m6-pair-2-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6115,
        "output_tokens": 76,
        "status": "known"
      },
      "93ddf1bdb44e497da4cd8c3b1976ddc9": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-c/m6-pair-2-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6088,
        "output_tokens": 30,
        "status": "known"
      },
      "2c946ae4b5d0419fa71063bdb1b9f9ee": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-c/m6-pair-2-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8487,
        "output_tokens": 94,
        "status": "known"
      },
      "b1523f91aac74844a096b4b94f31c72b": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-c/m6-pair-2-c/trials/calc-open/1",
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
      "191bb70d1fdb40179ba31936378236fc": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-c/m6-pair-2-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8671,
        "output_tokens": 80,
        "status": "known"
      },
      "49277af813c642e8b7496a775c118d27": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-c/m6-pair-2-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11177,
        "output_tokens": 116,
        "status": "known"
      },
      "3b7ba5ae67b04be1b9422e6287606f90": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-c/m6-pair-2-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2503,
        "output_tokens": 53,
        "status": "known"
      },
      "2fb79a2395744203b605ff6be6498657": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-c/m6-pair-2-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11174,
        "output_tokens": 28,
        "status": "known"
      },
      "b98049f7b53040669badcab0d2b2486d": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-c/m6-pair-2-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 13587,
        "output_tokens": 110,
        "status": "known"
      },
      "ea335d77dfd7424b8cd0d306281ca455": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-c/m6-pair-2-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2508,
        "output_tokens": 53,
        "status": "known"
      },
      "074ad8875dcd417e8c79db2f61b9075a": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-c/m6-pair-2-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 13723,
        "output_tokens": 73,
        "status": "known"
      },
      "867da9cceb4a428ca077b39d370fafe8": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-c/m6-pair-2-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 15090,
        "output_tokens": 223,
        "status": "known"
      },
      "0e6ebf0100b14d9cbeba3e9734f9828e": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-c/m6-pair-2-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 15337,
        "output_tokens": 95,
        "status": "known"
      },
      "508dd3f29cd04b05a38fe7131ed99b9f": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-c/m6-pair-2-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 1407,
        "output_tokens": 52,
        "status": "known"
      },
      "751529f04ca04c849c600b07964db2aa": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-c/m6-pair-2-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 15528,
        "output_tokens": 69,
        "status": "known"
      },
      "b0936ee926e04a5da637b9b4886ed74b": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-c/m6-pair-2-c/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 18014,
        "output_tokens": 109,
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
    "locator": 5,
    "total": 21,
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
          "result": "7×"
        },
        "last_screenshot": {
          "sha256": "7b608e0899560669fb7f3f8d81ec4182b3fef524fcbe030bc0dc072bbb0af7cf",
          "file": "screenshots/shot_006.png",
          "captured_at": 1790261082.337754,
          "http_serialized_at": 1790261082.353854
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
