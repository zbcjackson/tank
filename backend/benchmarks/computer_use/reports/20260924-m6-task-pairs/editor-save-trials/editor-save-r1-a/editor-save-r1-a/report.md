# computer_use benchmark

- Run label: `editor-save-r1-a`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| editor-save | 0/1 | 0% | 0%–79% | 15 | 12 | 16 | 15 | 43 | 154236 | 4 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| editor-save | 16 | 1.3 | 2.3 | 43 | 0.0 |

- API calls total: 16, mean 2.7s/call, median streamed ttft 1.3, LLM time total 43s

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
      "charged_tokens": 154236,
      "charged_nano_usd": 0,
      "known_tokens": 154236,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 16,
      "admitted_requests": 16
    },
    "trials": {
      "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-a/editor-save-r1-a/trials/editor-save/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 154236,
        "charged_nano_usd": 0,
        "known_tokens": 154236,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "4b0e4a016f144749830ca12a24e359ce": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-a/editor-save-r1-a/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5111,
        "output_tokens": 27,
        "status": "known"
      },
      "f75f7804d02a425897ecc7b84774106e": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-a/editor-save-r1-a/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5168,
        "output_tokens": 13,
        "status": "known"
      },
      "94cbc02b3d63432faaf1cafedd6bef00": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-a/editor-save-r1-a/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7343,
        "output_tokens": 104,
        "status": "known"
      },
      "18242700abcc43f88a0b01f8c0562fdd": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-a/editor-save-r1-a/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6755,
        "output_tokens": 47,
        "status": "known"
      },
      "9582af2f11074eb68d1a97d6d444611d": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-a/editor-save-r1-a/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6882,
        "output_tokens": 44,
        "status": "known"
      },
      "8854b81275ec4cf2af13dc23bedd31d5": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-a/editor-save-r1-a/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9082,
        "output_tokens": 86,
        "status": "known"
      },
      "36a0d90d569245e990c05dce8bb3f409": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-a/editor-save-r1-a/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9209,
        "output_tokens": 41,
        "status": "known"
      },
      "688fe2d0a92c4faeaeac9e6e74e63901": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-a/editor-save-r1-a/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9361,
        "output_tokens": 113,
        "status": "known"
      },
      "851c07235d53410186b6536beff9355e": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-a/editor-save-r1-a/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9521,
        "output_tokens": 127,
        "status": "known"
      },
      "31cea1c73e634d0bb25db2779b8c8177": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-a/editor-save-r1-a/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9690,
        "output_tokens": 41,
        "status": "known"
      },
      "b0a6a938bc554545a8ce7b88751bc3d5": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-a/editor-save-r1-a/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9776,
        "output_tokens": 25,
        "status": "known"
      },
      "40da2ef8581b4a0c90f7d8e87276211b": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-a/editor-save-r1-a/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11945,
        "output_tokens": 126,
        "status": "known"
      },
      "43468141d6e44b899f6330a0b3e9ab0c": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-a/editor-save-r1-a/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 12117,
        "output_tokens": 87,
        "status": "known"
      },
      "5c74dfe5a17e414f80fb82d70ae3dc4b": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-a/editor-save-r1-a/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 12249,
        "output_tokens": 20,
        "status": "known"
      },
      "9995228ecc564051a98695b6f9b9d9b0": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-a/editor-save-r1-a/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 14425,
        "output_tokens": 89,
        "status": "known"
      },
      "b526b16dc90545939ae5a87a138f85c4": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-a/editor-save-r1-a/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 14561,
        "output_tokens": 51,
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
  "git_revision": "12dde91ea02ed19aea3975ac835264e8625da77a",
  "task_revision": "9442074589754111c1b5273dc1048298b42e78f3b0d48695373c30fe975004ee",
  "scoring_revision": "trial-token-gui-grounding-v5",
  "aborted_cleanup": false,
  "outcomes": [
    {
      "task": "editor-save",
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
      "task": "editor-save",
      "tool_call_limit": 15,
      "timeout_s": 180,
      "gui_only": true
    }
  ]
}
```
