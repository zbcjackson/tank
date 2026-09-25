# computer_use benchmark

- Run label: `editor-save-r2-c`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| editor-save | 0/1 | 0% | 0%–79% | 15 | 4 | 19 | 15 | 68 | 213493 | 7 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| editor-save | 19 | 2.0 | 2.9 | 68 | 0.0 |

- API calls total: 19, mean 3.6s/call, median streamed ttft 2.0, LLM time total 68s

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
      "charged_tokens": 213493,
      "charged_nano_usd": 0,
      "known_tokens": 213493,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 31,
      "admitted_requests": 19
    },
    "trials": {
      "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r2-c/editor-save-r2-c/trials/editor-save/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 213493,
        "charged_nano_usd": 0,
        "known_tokens": 213493,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "04224682a65c4487a98ed6505e20a932": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r2-c/editor-save-r2-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 3844,
        "output_tokens": 89,
        "status": "known"
      },
      "33e787f374824d92b0b2385cbba02e66": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r2-c/editor-save-r2-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6344,
        "output_tokens": 91,
        "status": "known"
      },
      "c50c5354da8a499489eaa465cec40cf8": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r2-c/editor-save-r2-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6332,
        "output_tokens": 33,
        "status": "known"
      },
      "dade4e1775c646afa2370e94f27e1235": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r2-c/editor-save-r2-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8753,
        "output_tokens": 104,
        "status": "known"
      },
      "447aefe950d4442997f028364afa67e9": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r2-c/editor-save-r2-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2503,
        "output_tokens": 51,
        "status": "known"
      },
      "d380c904795e439596df291b9cbbb9c5": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r2-c/editor-save-r2-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8951,
        "output_tokens": 67,
        "status": "known"
      },
      "a9d6d93ca50942a4a7f2f1beac729d31": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r2-c/editor-save-r2-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11488,
        "output_tokens": 147,
        "status": "known"
      },
      "9f2a399a665647de869b938f833d97fd": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r2-c/editor-save-r2-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2508,
        "output_tokens": 48,
        "status": "known"
      },
      "7787e88d637a46969d5dfbd32c45987a": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r2-c/editor-save-r2-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11691,
        "output_tokens": 94,
        "status": "known"
      },
      "6d417e3e27f249da9f0d5d6b5f4848d2": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r2-c/editor-save-r2-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 12543,
        "output_tokens": 101,
        "status": "known"
      },
      "5e1783880d7346e9bdf54663767dbbd9": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r2-c/editor-save-r2-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 883,
        "output_tokens": 52,
        "status": "known"
      },
      "e683e19c562d4b6d9f81c398c5d01aa6": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r2-c/editor-save-r2-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 12736,
        "output_tokens": 65,
        "status": "known"
      },
      "4a8402aa0aff46c8a7ae382ed4b0b432": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r2-c/editor-save-r2-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 15303,
        "output_tokens": 210,
        "status": "known"
      },
      "dd81da861d3848fcb80e62fa3b00a9a4": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r2-c/editor-save-r2-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 15575,
        "output_tokens": 80,
        "status": "known"
      },
      "8a1daef6e955438398875fa5ca2752ac": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r2-c/editor-save-r2-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 15541,
        "output_tokens": 21,
        "status": "known"
      },
      "4b90f68d1f2f4cad9e9f7ddfa6060f99": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r2-c/editor-save-r2-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 17946,
        "output_tokens": 183,
        "status": "known"
      },
      "8b39de7de7524229a1204e5702b5b54c": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r2-c/editor-save-r2-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 18187,
        "output_tokens": 210,
        "status": "known"
      },
      "a4af9ab7fa314e61b74eb1ad5d7297dc": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r2-c/editor-save-r2-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 20133,
        "output_tokens": 200,
        "status": "known"
      },
      "7a811ba64f5a4d56b48ff2a877ef0cd7": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r2-c/editor-save-r2-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 20364,
        "output_tokens": 22,
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
