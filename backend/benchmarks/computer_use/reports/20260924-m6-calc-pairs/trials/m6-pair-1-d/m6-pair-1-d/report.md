# computer_use benchmark

- Run label: `m6-pair-1-d`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| calc-open | 0/1 | 0% | 0%–79% | 14 | 10 | 20 | 15 | 83 | 199922 | 7 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| calc-open | 20 | 2.0 | 3.1 | 74 | 0.0 |

- API calls total: 20, mean 3.7s/call, median streamed ttft 2.0, LLM time total 74s

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
    "variant": "D",
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
      "charged_tokens": 199922,
      "charged_nano_usd": 0,
      "known_tokens": 199922,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 31,
      "admitted_requests": 20
    },
    "trials": {
      "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-d/m6-pair-1-d/trials/calc-open/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 199922,
        "charged_nano_usd": 0,
        "known_tokens": 199922,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "f3e98cf51fc1441c94f4de93b19c3c65": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-d/m6-pair-1-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 3828,
        "output_tokens": 71,
        "status": "known"
      },
      "5aac4b8689bb40ec94e54bafa99d627d": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-d/m6-pair-1-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6304,
        "output_tokens": 156,
        "status": "known"
      },
      "5056e8ceb81d4883a0be6658df237cd9": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-d/m6-pair-1-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2558,
        "output_tokens": 81,
        "status": "known"
      },
      "d945ca94f94b4160a90ac4f1959595a3": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-d/m6-pair-1-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6547,
        "output_tokens": 118,
        "status": "known"
      },
      "7ec75df65122421c9025ad49e3a06ebd": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-d/m6-pair-1-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9206,
        "output_tokens": 130,
        "status": "known"
      },
      "dac5696537ec4edfa742a517bdd40ca5": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-d/m6-pair-1-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2557,
        "output_tokens": 81,
        "status": "known"
      },
      "b71a6c6250b44d399047a0bd1cf930fa": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-d/m6-pair-1-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9427,
        "output_tokens": 141,
        "status": "known"
      },
      "92d1c11166e64abebf8b3aeddb1314c6": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-d/m6-pair-1-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11403,
        "output_tokens": 115,
        "status": "known"
      },
      "2879b4ab28e7496397db9202f729e0ea": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-d/m6-pair-1-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2560,
        "output_tokens": 81,
        "status": "known"
      },
      "c7ab3ec14b1a4e25bc94cc0084928bd2": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-d/m6-pair-1-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11610,
        "output_tokens": 115,
        "status": "known"
      },
      "ac407ec03dd5437f8148ef7cb771316d": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-d/m6-pair-1-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11754,
        "output_tokens": 106,
        "status": "known"
      },
      "8c2187fb3b004a73ac0b9182d3726869": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-d/m6-pair-1-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11910,
        "output_tokens": 41,
        "status": "known"
      },
      "d90a0bf4f8c440c1ab2e13a11eebae66": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-d/m6-pair-1-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 14347,
        "output_tokens": 174,
        "status": "known"
      },
      "885229d6285843cd811567837a745f2c": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-d/m6-pair-1-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2563,
        "output_tokens": 81,
        "status": "known"
      },
      "7cd9aa9f5f364a9fa1ae8f12f9cbc68e": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-d/m6-pair-1-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 14612,
        "output_tokens": 88,
        "status": "known"
      },
      "8844c963a7c74fdd9e2730ca7901c65b": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-d/m6-pair-1-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2557,
        "output_tokens": 81,
        "status": "known"
      },
      "2a5c520581ed467e96ab12a3b45f5859": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-d/m6-pair-1-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 14792,
        "output_tokens": 89,
        "status": "known"
      },
      "b59df910a5934669add37c4843a0ee62": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-d/m6-pair-1-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 17305,
        "output_tokens": 100,
        "status": "known"
      },
      "bcc3f08f67984a408cfeccb511131918": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-d/m6-pair-1-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 19816,
        "output_tokens": 56,
        "status": "known"
      },
      "b9e11fdfc6874f7f82cf778e7779770d": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-d/m6-pair-1-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 22261,
        "output_tokens": 100,
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
    "planner": 15,
    "locator": 5,
    "total": 20,
    "blocked": false
  },
  "request_limits": {
    "planner": 16,
    "locator": 15,
    "total": 31
  },
  "grounding": {
    "profile": "locator",
    "fallback_profile": null,
    "protocol": "bbox",
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
          "result": "56"
        },
        "last_screenshot": {
          "sha256": "03a8ec6b4774c4948780dd56cb684b5d75aa6065d0558ff52dad3170c9578b73",
          "file": "screenshots/shot_007.png",
          "captured_at": 1790260934.16095,
          "http_serialized_at": 1790260934.179421
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
