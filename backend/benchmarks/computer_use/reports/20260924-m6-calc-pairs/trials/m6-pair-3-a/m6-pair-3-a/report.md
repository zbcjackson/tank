# computer_use benchmark

- Run label: `m6-pair-3-a`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| calc-open | 0/1 | 0% | 0%–79% | 15 | 14 | 16 | 15 | 67 | 226204 | 6 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| calc-open | 16 | 1.9 | 2.4 | 58 | 0.0 |

- API calls total: 16, mean 3.6s/call, median streamed ttft 1.9, LLM time total 58s

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
      "charged_tokens": 226204,
      "charged_nano_usd": 0,
      "known_tokens": 226204,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 16,
      "admitted_requests": 16
    },
    "trials": {
      "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-a/m6-pair-3-a/trials/calc-open/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 226204,
        "charged_nano_usd": 0,
        "known_tokens": 226204,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "a15954f8728842e382cc4197f2470e09": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-a/m6-pair-3-a/trials/calc-open/1",
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
      "623b3382b41948299188540c88cb5734": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-a/m6-pair-3-a/trials/calc-open/1",
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
      "ce61680ac10f4944a1264e8eb8b54dab": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-a/m6-pair-3-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7327,
        "output_tokens": 330,
        "status": "known"
      },
      "b7a8b511b59b4977aaca1655185ce79a": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-a/m6-pair-3-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9628,
        "output_tokens": 571,
        "status": "known"
      },
      "60087460d3d441d99cd1a323e4c198c9": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-a/m6-pair-3-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10246,
        "output_tokens": 26,
        "status": "known"
      },
      "c76c6d2fa9af49bfb3e837c8e47644db": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-a/m6-pair-3-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 12432,
        "output_tokens": 72,
        "status": "known"
      },
      "43b425eeafda45239861c9366a89bf45": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-a/m6-pair-3-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 14620,
        "output_tokens": 419,
        "status": "known"
      },
      "abe5137c16934425954dacd41f8afb74": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-a/m6-pair-3-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 15087,
        "output_tokens": 55,
        "status": "known"
      },
      "5d205d60c65e461580c5ed45be76342b": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-a/m6-pair-3-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 15190,
        "output_tokens": 53,
        "status": "known"
      },
      "f36e7ec9594f454c836e6d39254a7b3b": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-a/m6-pair-3-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 15291,
        "output_tokens": 55,
        "status": "known"
      },
      "582508a7332b407fb793ac2b5ff0d33d": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-a/m6-pair-3-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 15394,
        "output_tokens": 24,
        "status": "known"
      },
      "0aa32485d2ae427e9a2aba24455c779b": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-a/m6-pair-3-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 17566,
        "output_tokens": 109,
        "status": "known"
      },
      "1fdbcd0c802c47148a96b078fcae30b1": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-a/m6-pair-3-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 19822,
        "output_tokens": 381,
        "status": "known"
      },
      "e9208870a2c84a16bcc422027d51f638": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-a/m6-pair-3-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 20251,
        "output_tokens": 53,
        "status": "known"
      },
      "bb7dddc4aa1f44839c49ee1776c70d54": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-a/m6-pair-3-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 20352,
        "output_tokens": 53,
        "status": "known"
      },
      "f770fd6d3e214f78923c0ef5549359c8": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-a/m6-pair-3-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 20453,
        "output_tokens": 57,
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
          "result": "7×8"
        },
        "last_screenshot": {
          "sha256": "aa25fd4fe981a90c564bcb7c38a452da67da035847b8b9d3d1d24645c4cd5fea",
          "file": "screenshots/shot_006.png",
          "captured_at": 1790261375.486541,
          "http_serialized_at": 1790261387.7321799
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
