# computer_use benchmark

- Run label: `multi-select-copy-r1-a`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| multi-select-copy | 0/1 | 0% | 0%–79% | 15 | 10 | 16 | 15 | 44 | 168139 | 4 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| multi-select-copy | 16 | 1.7 | 2.3 | 44 | 0.0 |

- API calls total: 16, mean 2.8s/call, median streamed ttft 1.7, LLM time total 44s

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
      "charged_tokens": 168139,
      "charged_nano_usd": 0,
      "known_tokens": 168139,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 16,
      "admitted_requests": 16
    },
    "trials": {
      "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-a/multi-select-copy-r1-a/trials/multi-select-copy/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 168139,
        "charged_nano_usd": 0,
        "known_tokens": 168139,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "f092da26ea09497aa21f5cce7071f352": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-a/multi-select-copy-r1-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5138,
        "output_tokens": 52,
        "status": "known"
      },
      "479c938decbb46de85750a84bb915142": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-a/multi-select-copy-r1-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5220,
        "output_tokens": 13,
        "status": "known"
      },
      "bed317f920aa489b8bc7c06efdbeaa6d": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-a/multi-select-copy-r1-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7395,
        "output_tokens": 109,
        "status": "known"
      },
      "c09db5b4afb34139b00030eba6bb3a3d": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-a/multi-select-copy-r1-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9475,
        "output_tokens": 77,
        "status": "known"
      },
      "b33e58c3fe8b45f7b0fe4681b117e82f": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-a/multi-select-copy-r1-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9599,
        "output_tokens": 57,
        "status": "known"
      },
      "e563345037c44d8d99d1b67a8ece15db": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-a/multi-select-copy-r1-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8998,
        "output_tokens": 61,
        "status": "known"
      },
      "27b2b486f72a4ac99c0db4997323d966": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-a/multi-select-copy-r1-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8958,
        "output_tokens": 39,
        "status": "known"
      },
      "bf11d00c731941fcae5766527e0ea87a": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-a/multi-select-copy-r1-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9018,
        "output_tokens": 14,
        "status": "known"
      },
      "0fd66a55c4c2461ca88e03210f2cd7c7": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-a/multi-select-copy-r1-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11180,
        "output_tokens": 153,
        "status": "known"
      },
      "e5034e94eb6f40ce8ddba43f11c24c7b": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-a/multi-select-copy-r1-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11376,
        "output_tokens": 47,
        "status": "known"
      },
      "e275658cf14e495ab12aff9254d819e0": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-a/multi-select-copy-r1-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11444,
        "output_tokens": 14,
        "status": "known"
      },
      "10c9809f412f48569ca2e2cf202cc5ca": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-a/multi-select-copy-r1-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 13614,
        "output_tokens": 81,
        "status": "known"
      },
      "b3f025ec6633443ebed0d0c4f7e85a26": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-a/multi-select-copy-r1-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 13715,
        "output_tokens": 78,
        "status": "known"
      },
      "5f7e5e88eaa84441a62115d82d029cfb": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-a/multi-select-copy-r1-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 13877,
        "output_tokens": 111,
        "status": "known"
      },
      "061078cce291400db45f06756c84376f": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-a/multi-select-copy-r1-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 14009,
        "output_tokens": 43,
        "status": "known"
      },
      "f61fe8476ff44c8dad077c08f02f491d": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r1-a/multi-select-copy-r1-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 14128,
        "output_tokens": 46,
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
      "task": "multi-select-copy",
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
      "task": "multi-select-copy",
      "tool_call_limit": 15,
      "timeout_s": 180,
      "gui_only": true
    }
  ]
}
```
