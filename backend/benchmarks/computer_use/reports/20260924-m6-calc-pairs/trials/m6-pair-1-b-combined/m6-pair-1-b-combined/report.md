# computer_use benchmark

- Run label: `m6-pair-1-b-combined`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **1/1** (100%, 95% CI 21%–100%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| calc-open | 1/1 | 100% | 21%–100% | 8 | 7 | 9 | 15 | 53 | 134457 | 8 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| calc-open | 9 | 2.4 | 3.9 | 44 | 0.0 |

- API calls total: 9, mean 4.8s/call, median streamed ttft 2.4, LLM time total 44s

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
    "variant": "B-combined",
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
      "charged_tokens": 134457,
      "charged_nano_usd": 0,
      "known_tokens": 134457,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 16,
      "admitted_requests": 9
    },
    "trials": {
      "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-b-combined/m6-pair-1-b-combined/trials/calc-open/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 134457,
        "charged_nano_usd": 0,
        "known_tokens": 134457,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "5df2574d14164d3cafac536dfe7ce5c3": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-b-combined/m6-pair-1-b-combined/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 4740,
        "output_tokens": 47,
        "status": "known"
      },
      "c5010bcdec4b431c88555ef6502f16ae": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-b-combined/m6-pair-1-b-combined/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7206,
        "output_tokens": 290,
        "status": "known"
      },
      "657ec82d86b5460caca162b8e640ffd0": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-b-combined/m6-pair-1-b-combined/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8797,
        "output_tokens": 127,
        "status": "known"
      },
      "9d806e63c0134122bbecaf906b6787ec": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-b-combined/m6-pair-1-b-combined/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11436,
        "output_tokens": 828,
        "status": "known"
      },
      "5354e89c075d4c6a972be88267992b92": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-b-combined/m6-pair-1-b-combined/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 14640,
        "output_tokens": 389,
        "status": "known"
      },
      "aaf6dd9672f843b39a912e3668d62a2e": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-b-combined/m6-pair-1-b-combined/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 17470,
        "output_tokens": 157,
        "status": "known"
      },
      "1fab4243971d436e973652a8190fbbdb": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-b-combined/m6-pair-1-b-combined/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 20061,
        "output_tokens": 160,
        "status": "known"
      },
      "4412117db0d5424e808a14f57321aa55": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-b-combined/m6-pair-1-b-combined/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 22656,
        "output_tokens": 149,
        "status": "known"
      },
      "ba6b94428dba41018c7590fc274cb941": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-1-b-combined/m6-pair-1-b-combined/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 25236,
        "output_tokens": 68,
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
    "planner": 9,
    "locator": 0,
    "total": 9,
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
    "protocol": "point",
    "nullable_style": "integer",
    "strict": false,
    "detail": "auto",
    "status_field": false,
    "mode": "integrated",
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
      "success": true,
      "unknown_calls": 0,
      "assessment": {
        "revision": "calc-evidence-v1",
        "strict_expression": true,
        "business": null,
        "mouse_only": null,
        "pixels": "unknown",
        "reset_verified": true,
        "input_trace_complete": false,
        "display": {
          "expression": "7×8",
          "result": "56"
        },
        "last_screenshot": {
          "sha256": "f71832ff17c550f53cdff2cda9916fb6e234a93d005932d7abfb398da1a3dfa1",
          "file": "screenshots/shot_008.png",
          "captured_at": 1790260804.4662158,
          "http_serialized_at": 1790260804.4897861
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
