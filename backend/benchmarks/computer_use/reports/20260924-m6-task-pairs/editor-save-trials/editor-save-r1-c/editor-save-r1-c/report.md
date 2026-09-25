# computer_use benchmark

- Run label: `editor-save-r1-c`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| editor-save | 0/1 | 0% | 0%–79% | 15 | 5 | 19 | 15 | 71 | 248339 | 9 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| editor-save | 19 | 2.1 | 3.3 | 70 | 0.0 |

- API calls total: 19, mean 3.7s/call, median streamed ttft 2.1, LLM time total 70s

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
      "charged_tokens": 248339,
      "charged_nano_usd": 0,
      "known_tokens": 248339,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 31,
      "admitted_requests": 19
    },
    "trials": {
      "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-c/editor-save-r1-c/trials/editor-save/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 248339,
        "charged_nano_usd": 0,
        "known_tokens": 248339,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "1797a2b57a2045909cac9150a031f193": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-c/editor-save-r1-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 3844,
        "output_tokens": 90,
        "status": "known"
      },
      "b32458fc580942acbc80a3ed18dc060c": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-c/editor-save-r1-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6338,
        "output_tokens": 77,
        "status": "known"
      },
      "ed400433dc8c4c3a9078026eb219fe72": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-c/editor-save-r1-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6312,
        "output_tokens": 31,
        "status": "known"
      },
      "bda1e0ba7c1647f3a804ec16a41584c8": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-c/editor-save-r1-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8724,
        "output_tokens": 109,
        "status": "known"
      },
      "d3b18c66ec2c4805802640d05f2ad348": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-c/editor-save-r1-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2501,
        "output_tokens": 51,
        "status": "known"
      },
      "7ed57a19ba994bf7b9a0405ee6f6bece": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-c/editor-save-r1-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8924,
        "output_tokens": 78,
        "status": "known"
      },
      "6d0a75df013b43b9b7148bf55c6cca65": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-c/editor-save-r1-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11468,
        "output_tokens": 207,
        "status": "known"
      },
      "a3329fc13b6c439b8a814cbb5ae758df": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-c/editor-save-r1-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 13414,
        "output_tokens": 102,
        "status": "known"
      },
      "fbcbbe39a73b46c1a8c999cf5f3b086c": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-c/editor-save-r1-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2502,
        "output_tokens": 51,
        "status": "known"
      },
      "7eab37d0efdc4ecc92dd031fd4fd2dbf": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-c/editor-save-r1-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 13612,
        "output_tokens": 75,
        "status": "known"
      },
      "cd004104eb124658829cadbb246cea7e": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-c/editor-save-r1-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 16185,
        "output_tokens": 151,
        "status": "known"
      },
      "6ccfd21eff414fc79bde46506b17de20": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-c/editor-save-r1-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 16398,
        "output_tokens": 28,
        "status": "known"
      },
      "f3e1ecba64c34154af8045eba2bca7ab": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-c/editor-save-r1-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 18808,
        "output_tokens": 143,
        "status": "known"
      },
      "31ba611689ca47e59d0fb28eeab02d81": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-c/editor-save-r1-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2502,
        "output_tokens": 48,
        "status": "known"
      },
      "354669e6922b451eb216f3169544b116": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-c/editor-save-r1-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 19008,
        "output_tokens": 86,
        "status": "known"
      },
      "c26614231c5841e382bf97e0dda37cf3": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-c/editor-save-r1-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 21388,
        "output_tokens": 79,
        "status": "known"
      },
      "f573f5b1291b4af396d0e41513f7f2ac": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-c/editor-save-r1-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 23878,
        "output_tokens": 208,
        "status": "known"
      },
      "0fb7ac3998894f689e203d8776006c79": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-c/editor-save-r1-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 24148,
        "output_tokens": 36,
        "status": "known"
      },
      "934c6d7db0a447328cc4bac71b7322be": {
        "trial": "/private/tmp/tank-m6-editor-save-20260925-live/trials/editor-save-r1-c/editor-save-r1-c/trials/editor-save/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 26562,
        "output_tokens": 173,
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
