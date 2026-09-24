# computer_use benchmark

- Run label: `m6-pair-2-d`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| calc-open | 0/1 | 0% | 0%–79% | 15 | 3 | 19 | 15 | 70 | 170531 | 5 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| calc-open | 19 | 1.9 | 2.9 | 61 | 0.0 |

- API calls total: 19, mean 3.2s/call, median streamed ttft 1.9, LLM time total 61s

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
      "charged_tokens": 170531,
      "charged_nano_usd": 0,
      "known_tokens": 170531,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 31,
      "admitted_requests": 19
    },
    "trials": {
      "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-d/m6-pair-2-d/trials/calc-open/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 170531,
        "charged_nano_usd": 0,
        "known_tokens": 170531,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "f8bc9b9a053f416b8396b08a4f9caebd": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-d/m6-pair-2-d/trials/calc-open/1",
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
      "c5fcc1cbdf5c479fa448804b34dcdd1d": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-d/m6-pair-2-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6374,
        "output_tokens": 200,
        "status": "known"
      },
      "8347931ed5244d2ea852108f788bea9f": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-d/m6-pair-2-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8308,
        "output_tokens": 158,
        "status": "known"
      },
      "c1a00f0c062640acac167ac16d4f8e13": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-d/m6-pair-2-d/trials/calc-open/1",
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
      "83eba488d45746f692767fbf2f17f70d": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-d/m6-pair-2-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8558,
        "output_tokens": 91,
        "status": "known"
      },
      "0bd200f265394eb2ae1e325e14ab4a18": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-d/m6-pair-2-d/trials/calc-open/1",
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
      "0c747938605246519cba721613eb3e49": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-d/m6-pair-2-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8744,
        "output_tokens": 84,
        "status": "known"
      },
      "695d56a03ec343fdb82d16cc998dd7ed": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-d/m6-pair-2-d/trials/calc-open/1",
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
      "0d753b6e45de457381773444bce222af": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-d/m6-pair-2-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8918,
        "output_tokens": 89,
        "status": "known"
      },
      "993184083e574a219af74ce8a15793d4": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-d/m6-pair-2-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8893,
        "output_tokens": 82,
        "status": "known"
      },
      "be1b999f73094a5cb5575099a351c744": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-d/m6-pair-2-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9006,
        "output_tokens": 68,
        "status": "known"
      },
      "a55391528137416a9c2804132e129d38": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-d/m6-pair-2-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8971,
        "output_tokens": 82,
        "status": "known"
      },
      "0fc9b107a9c34868ad0716a8cce499b9": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-d/m6-pair-2-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9111,
        "output_tokens": 141,
        "status": "known"
      },
      "83e6d4cfffa449ca965d04feb54364ca": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-d/m6-pair-2-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11615,
        "output_tokens": 467,
        "status": "known"
      },
      "c41339d6fa76426fa26e2935756fca72": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-d/m6-pair-2-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 12106,
        "output_tokens": 99,
        "status": "known"
      },
      "cec18691d5cb4340b13ae055e5c01e9b": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-d/m6-pair-2-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 12263,
        "output_tokens": 84,
        "status": "known"
      },
      "9ed007b39b3a4ff1b2280f6ad4480ffb": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-d/m6-pair-2-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 12187,
        "output_tokens": 55,
        "status": "known"
      },
      "5db13c410d2140e1a62c116cf0d87b6a": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-d/m6-pair-2-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 14646,
        "output_tokens": 72,
        "status": "known"
      },
      "08e2975d9bb44bd3a5d466d05e0b0cba": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-d/m6-pair-2-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 17081,
        "output_tokens": 104,
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
          "result": "7"
        },
        "last_screenshot": {
          "sha256": "ae4a1ef743d5c9d852686d719ee2a99a7520ed057a267c4c2e74e61cadcf48a9",
          "file": "screenshots/shot_005.png",
          "captured_at": 1790261153.97793,
          "http_serialized_at": 1790261153.994453
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
