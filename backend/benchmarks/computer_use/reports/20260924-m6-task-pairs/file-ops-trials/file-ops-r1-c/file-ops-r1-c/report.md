# computer_use benchmark

- Run label: `file-ops-r1-c`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| file-ops | 0/1 | 0% | 0%–79% | 15 | 9 | 18 | 15 | 64 | 264503 | 9 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| file-ops | 18 | 2.1 | 3.3 | 64 | 0.0 |

- API calls total: 18, mean 3.5s/call, median streamed ttft 2.1, LLM time total 64s

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
      "charged_tokens": 264503,
      "charged_nano_usd": 0,
      "known_tokens": 264503,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 31,
      "admitted_requests": 18
    },
    "trials": {
      "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-c/file-ops-r1-c/trials/file-ops/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 264503,
        "charged_nano_usd": 0,
        "known_tokens": 264503,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "cdca2d2b251d450fb25199108a27f0a3": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-c/file-ops-r1-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 3857,
        "output_tokens": 114,
        "status": "known"
      },
      "19518f908d15437989e6f310e00e39de": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-c/file-ops-r1-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6386,
        "output_tokens": 81,
        "status": "known"
      },
      "50f09bdc35fb4d0287eee2233c3c84d0": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-c/file-ops-r1-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6364,
        "output_tokens": 35,
        "status": "known"
      },
      "8466793d7f5e4fe2947b447d115eb15b": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-c/file-ops-r1-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8788,
        "output_tokens": 103,
        "status": "known"
      },
      "192b1018abf343f0bab14cd8a741634e": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-c/file-ops-r1-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2503,
        "output_tokens": 52,
        "status": "known"
      },
      "4dcdacfc6b714050a8bc10502460d79c": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-c/file-ops-r1-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8986,
        "output_tokens": 82,
        "status": "known"
      },
      "8113b00ec3bb4dd1b8d9161190a412b9": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-c/file-ops-r1-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11496,
        "output_tokens": 108,
        "status": "known"
      },
      "9e6060bcc9a2453d8feacea95ae8413d": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-c/file-ops-r1-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 14018,
        "output_tokens": 95,
        "status": "known"
      },
      "81026ebbb8c5419ba434fe78dd6b7ba3": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-c/file-ops-r1-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 16526,
        "output_tokens": 94,
        "status": "known"
      },
      "7b62852d244c4184ab85f0ce8a08694f": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-c/file-ops-r1-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 19034,
        "output_tokens": 97,
        "status": "known"
      },
      "ba996e5223374c97b5d13111fd97526c": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-c/file-ops-r1-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 19162,
        "output_tokens": 38,
        "status": "known"
      },
      "5024b65d45ed465488a909c340b31c27": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-c/file-ops-r1-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 21576,
        "output_tokens": 209,
        "status": "known"
      },
      "dbae08b7d4e54b53ad108409b2dce549": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-c/file-ops-r1-c/trials/file-ops/1",
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
      "bcd122b0744246358d9ca993a1123005": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-c/file-ops-r1-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 21836,
        "output_tokens": 71,
        "status": "known"
      },
      "addb3681fc7a43d0a11b91dc49c96930": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-c/file-ops-r1-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 24765,
        "output_tokens": 94,
        "status": "known"
      },
      "5dacae6409084b5ebb315f4f181e9844": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-c/file-ops-r1-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 24188,
        "output_tokens": 60,
        "status": "known"
      },
      "ede9f43d425d45ff91231a910b08e934": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-c/file-ops-r1-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 24306,
        "output_tokens": 27,
        "status": "known"
      },
      "323e28eb240a460dafefeacbffc21c0a": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-c/file-ops-r1-c/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 26716,
        "output_tokens": 80,
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
    "locator": 2,
    "total": 18,
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
  "git_revision": "91877d76c39906ffcd486b37f4c077c32d2587af",
  "task_revision": "9442074589754111c1b5273dc1048298b42e78f3b0d48695373c30fe975004ee",
  "scoring_revision": "trial-token-gui-grounding-v5",
  "aborted_cleanup": false,
  "outcomes": [
    {
      "task": "file-ops",
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
      "task": "file-ops",
      "tool_call_limit": 15,
      "timeout_s": 180,
      "gui_only": true
    }
  ]
}
```
