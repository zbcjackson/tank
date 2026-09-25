# computer_use benchmark

- Run label: `drag-file-r3-a`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| drag-file | 0/1 | 0% | 0%–79% | 15 | 11 | 16 | 15 | 45 | 104074 | 3 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| drag-file | 16 | 1.6 | 2.3 | 45 | 0.0 |

- API calls total: 16, mean 2.8s/call, median streamed ttft 1.6, LLM time total 45s

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
      "charged_tokens": 104074,
      "charged_nano_usd": 0,
      "known_tokens": 104074,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 16,
      "admitted_requests": 16
    },
    "trials": {
      "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-a/drag-file-r3-a/trials/drag-file/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 104074,
        "charged_nano_usd": 0,
        "known_tokens": 104074,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "f6d8514b98184a9db07ad29443036cad": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-a/drag-file-r3-a/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5107,
        "output_tokens": 59,
        "status": "known"
      },
      "5d502d97fa524f3793d5d621fb78455c": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-a/drag-file-r3-a/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5196,
        "output_tokens": 29,
        "status": "known"
      },
      "689e5f1556c844589d399d8250ba5e4c": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-a/drag-file-r3-a/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5250,
        "output_tokens": 25,
        "status": "known"
      },
      "57e26252b3734a88bb930dc1790e9086": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-a/drag-file-r3-a/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5105,
        "output_tokens": 27,
        "status": "known"
      },
      "5536ba1a86c54b45a90e51e0f6b779ed": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-a/drag-file-r3-a/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5172,
        "output_tokens": 25,
        "status": "known"
      },
      "5159326f51cb4959ae2bb8cb331fc374": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-a/drag-file-r3-a/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5218,
        "output_tokens": 13,
        "status": "known"
      },
      "d34e04031fca40a4b75b3947e103dfa0": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-a/drag-file-r3-a/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 4838,
        "output_tokens": 22,
        "status": "known"
      },
      "753a8700c86f43459dbfa768ba2b00c2": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-a/drag-file-r3-a/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 4935,
        "output_tokens": 64,
        "status": "known"
      },
      "431aa0e354d547eb9c9e049053d954b4": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-a/drag-file-r3-a/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5047,
        "output_tokens": 13,
        "status": "known"
      },
      "1551173dc20740de8be8198df66aef16": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-a/drag-file-r3-a/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5135,
        "output_tokens": 47,
        "status": "known"
      },
      "c4e4638435194c69b72768d0c9af5656": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-a/drag-file-r3-a/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5212,
        "output_tokens": 13,
        "status": "known"
      },
      "263eefd2f5944209ada26324038345b8": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-a/drag-file-r3-a/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7351,
        "output_tokens": 174,
        "status": "known"
      },
      "1938066e9db243529782103526ef4fb5": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-a/drag-file-r3-a/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7589,
        "output_tokens": 44,
        "status": "known"
      },
      "edee567d6f0548858aaf971667119eed": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-a/drag-file-r3-a/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9793,
        "output_tokens": 170,
        "status": "known"
      },
      "cc805cf58c89481d8db8c3197b26ff24": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-a/drag-file-r3-a/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10027,
        "output_tokens": 26,
        "status": "known"
      },
      "54b97dd3fec14a549b87fece2026d368": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-a/drag-file-r3-a/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 12213,
        "output_tokens": 135,
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
      "task": "drag-file",
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
      "task": "drag-file",
      "tool_call_limit": 15,
      "timeout_s": 180,
      "gui_only": true
    }
  ]
}
```
