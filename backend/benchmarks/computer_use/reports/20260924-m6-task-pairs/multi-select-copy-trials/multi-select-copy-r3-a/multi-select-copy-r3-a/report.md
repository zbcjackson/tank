# computer_use benchmark

- Run label: `multi-select-copy-r3-a`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| multi-select-copy | 0/1 | 0% | 0%–79% | 15 | 12 | 16 | 15 | 40 | 129809 | 3 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| multi-select-copy | 16 | 1.5 | 2.2 | 40 | 0.0 |

- API calls total: 16, mean 2.5s/call, median streamed ttft 1.5, LLM time total 40s

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
      "charged_tokens": 129809,
      "charged_nano_usd": 0,
      "known_tokens": 129809,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 16,
      "admitted_requests": 16
    },
    "trials": {
      "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r3-a/multi-select-copy-r3-a/trials/multi-select-copy/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 129809,
        "charged_nano_usd": 0,
        "known_tokens": 129809,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "df3653142b3347aaa3f9f1d6984ec452": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r3-a/multi-select-copy-r3-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5138,
        "output_tokens": 53,
        "status": "known"
      },
      "f31d9f7d75d64c309768ee8c49ce98f6": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r3-a/multi-select-copy-r3-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5221,
        "output_tokens": 13,
        "status": "known"
      },
      "a8a1d64688ea45fab0ae201808e25b56": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r3-a/multi-select-copy-r3-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 4841,
        "output_tokens": 13,
        "status": "known"
      },
      "7cd6e7e27ebf4665ac9d8442aafda9e2": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r3-a/multi-select-copy-r3-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 4929,
        "output_tokens": 49,
        "status": "known"
      },
      "b6c3de410cac4745a4109adc2137a778": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r3-a/multi-select-copy-r3-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5003,
        "output_tokens": 13,
        "status": "known"
      },
      "251579ba5ff042c49cc721e0e3882d10": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r3-a/multi-select-copy-r3-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7166,
        "output_tokens": 65,
        "status": "known"
      },
      "e0c3231f813d4b07b1d20d547dd688f3": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r3-a/multi-select-copy-r3-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7251,
        "output_tokens": 14,
        "status": "known"
      },
      "1a9525205cc74a5b95a7b470e059021b": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r3-a/multi-select-copy-r3-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9425,
        "output_tokens": 140,
        "status": "known"
      },
      "01f56706643b4aa1a4614ba96a86f2d9": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r3-a/multi-select-copy-r3-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8873,
        "output_tokens": 52,
        "status": "known"
      },
      "e6e56e06fe724bc7b24f771574ffe619": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r3-a/multi-select-copy-r3-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8972,
        "output_tokens": 69,
        "status": "known"
      },
      "48f5c7551f2346d4b9f089a5e5ed0dae": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r3-a/multi-select-copy-r3-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9065,
        "output_tokens": 50,
        "status": "known"
      },
      "555fc8469c2240ff93e458cb9be3180b": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r3-a/multi-select-copy-r3-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9162,
        "output_tokens": 49,
        "status": "known"
      },
      "87a9e83dbd194bd1bae4ddf37277cdfb": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r3-a/multi-select-copy-r3-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9259,
        "output_tokens": 32,
        "status": "known"
      },
      "c7728a0a44b5474ea81907753887252a": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r3-a/multi-select-copy-r3-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11435,
        "output_tokens": 99,
        "status": "known"
      },
      "36e29945f6e8415b9ec5644d8e79275d": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r3-a/multi-select-copy-r3-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11581,
        "output_tokens": 53,
        "status": "known"
      },
      "d1a8c2a93f2f426fa61a382542d06b82": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r3-a/multi-select-copy-r3-a/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11655,
        "output_tokens": 69,
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
