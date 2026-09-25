# computer_use benchmark

- Run label: `drag-file-r1-a`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| drag-file | 0/1 | 0% | 0%–79% | 15 | 13 | 16 | 15 | 37 | 129498 | 3 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| drag-file | 16 | 1.6 | 2.2 | 37 | 0.0 |

- API calls total: 16, mean 2.3s/call, median streamed ttft 1.6, LLM time total 37s

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
      "charged_tokens": 129498,
      "charged_nano_usd": 0,
      "known_tokens": 129498,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 16,
      "admitted_requests": 16
    },
    "trials": {
      "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r1-a/drag-file-r1-a/trials/drag-file/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 129498,
        "charged_nano_usd": 0,
        "known_tokens": 129498,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "599492b1e4f74c4ba42d336088b29e05": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r1-a/drag-file-r1-a/trials/drag-file/1",
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
      "10fa8330376f4a049ece01893dd5fe4b": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r1-a/drag-file-r1-a/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5196,
        "output_tokens": 28,
        "status": "known"
      },
      "1619603737264a39a043fc2e7bfd9019": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r1-a/drag-file-r1-a/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5248,
        "output_tokens": 29,
        "status": "known"
      },
      "1306d8b711c54ac383f94ebe676f8751": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r1-a/drag-file-r1-a/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5302,
        "output_tokens": 32,
        "status": "known"
      },
      "875a925b21374af595fe1aeb808ff472": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r1-a/drag-file-r1-a/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5380,
        "output_tokens": 25,
        "status": "known"
      },
      "13d91b11fd7e4154a8375c2d8b2b1349": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r1-a/drag-file-r1-a/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5426,
        "output_tokens": 13,
        "status": "known"
      },
      "e157bca311a04110b7a5e83cb7a99729": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r1-a/drag-file-r1-a/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7585,
        "output_tokens": 68,
        "status": "known"
      },
      "99152e8c695143c49eb8551f85dde09a": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r1-a/drag-file-r1-a/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7677,
        "output_tokens": 35,
        "status": "known"
      },
      "c4c32ba00722489fa2a2df2e488a589c": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r1-a/drag-file-r1-a/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7757,
        "output_tokens": 28,
        "status": "known"
      },
      "a22e5faf139a44978e86a4b8da607aa2": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r1-a/drag-file-r1-a/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7805,
        "output_tokens": 17,
        "status": "known"
      },
      "e04fe60965ec4104b56c3cd3fa8808b7": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r1-a/drag-file-r1-a/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9974,
        "output_tokens": 82,
        "status": "known"
      },
      "2d95fc9265504202a80680c67db14407": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r1-a/drag-file-r1-a/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9364,
        "output_tokens": 41,
        "status": "known"
      },
      "af44cb3e805244288a9f76512b3aecac": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r1-a/drag-file-r1-a/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11565,
        "output_tokens": 80,
        "status": "known"
      },
      "6bc795c01c7342d0ac217eed2cb938cf": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r1-a/drag-file-r1-a/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11724,
        "output_tokens": 56,
        "status": "known"
      },
      "2816baed6da3433895a67abc53debe74": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r1-a/drag-file-r1-a/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11801,
        "output_tokens": 55,
        "status": "known"
      },
      "5c6fddea2d2144cdbbe308718db113e7": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r1-a/drag-file-r1-a/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11901,
        "output_tokens": 38,
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
