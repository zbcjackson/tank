# computer_use benchmark

- Run label: `local-form-r3-a`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **1/1** (100%, 95% CI 21%–100%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| local-form | 1/1 | 100% | 21%–100% | 14 | 14 | 15 | 15 | 38 | 136822 | 3 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| local-form | 15 | 1.7 | 2.4 | 38 | 0.0 |

- API calls total: 15, mean 2.5s/call, median streamed ttft 1.7, LLM time total 38s

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
      "charged_tokens": 136822,
      "charged_nano_usd": 0,
      "known_tokens": 136822,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 16,
      "admitted_requests": 15
    },
    "trials": {
      "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-a/local-form-r3-a/trials/local-form/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 136822,
        "charged_nano_usd": 0,
        "known_tokens": 136822,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "2caa7b5454f140fcb2bc23ab21b56059": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-a/local-form-r3-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5146,
        "output_tokens": 28,
        "status": "known"
      },
      "d41542248d194e85bef0dbb0d82b50ce": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-a/local-form-r3-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5205,
        "output_tokens": 13,
        "status": "known"
      },
      "baefc34b8fb84815886dc716e9fa7cce": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-a/local-form-r3-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7380,
        "output_tokens": 140,
        "status": "known"
      },
      "cdd6b5c1052d4d2ebac1f1dec75c8051": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-a/local-form-r3-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7565,
        "output_tokens": 67,
        "status": "known"
      },
      "507328fe6de3493f9a01b6b8b38601ec": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-a/local-form-r3-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7711,
        "output_tokens": 26,
        "status": "known"
      },
      "39a71fc16f3c4c2fb98e0f24f45aead9": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-a/local-form-r3-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7757,
        "output_tokens": 14,
        "status": "known"
      },
      "ed0937d4e576400c9b4c908a8f325d57": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-a/local-form-r3-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9923,
        "output_tokens": 129,
        "status": "known"
      },
      "a71e42f3aef64424923116aef3684c00": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-a/local-form-r3-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10098,
        "output_tokens": 33,
        "status": "known"
      },
      "7ae7b466f7004bab9a7947a9b1d125f9": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-a/local-form-r3-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10169,
        "output_tokens": 52,
        "status": "known"
      },
      "e02be143da45420c8aa072b9f7077c77": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-a/local-form-r3-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10268,
        "output_tokens": 35,
        "status": "known"
      },
      "910c8b77d6cf4b69bd7f223236dc160e": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-a/local-form-r3-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10345,
        "output_tokens": 52,
        "status": "known"
      },
      "cca81b57734748c9b46acea82c7a0646": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-a/local-form-r3-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10444,
        "output_tokens": 40,
        "status": "known"
      },
      "67a26a75d24a49e9a888a0c5ed312bb0": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-a/local-form-r3-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10531,
        "output_tokens": 52,
        "status": "known"
      },
      "71ffeb04dd7d4de080b9bbf47cb8e209": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-a/local-form-r3-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10630,
        "output_tokens": 25,
        "status": "known"
      },
      "1a1880481b4b4d8e8630865483c5d0da": {
        "trial": "/private/tmp/tank-m6-local-form-20260925-live/trials/local-form-r3-a/local-form-r3-a/trials/local-form/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 12791,
        "output_tokens": 153,
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
    "planner": 15,
    "locator": 0,
    "total": 15,
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
  "git_revision": "91877d76c39906ffcd486b37f4c077c32d2587af",
  "task_revision": "9442074589754111c1b5273dc1048298b42e78f3b0d48695373c30fe975004ee",
  "scoring_revision": "trial-token-gui-grounding-v5",
  "aborted_cleanup": false,
  "outcomes": [
    {
      "task": "local-form",
      "trial": 1,
      "stop_reason": null,
      "cleanup": "confirmed",
      "scoring": "strict",
      "success": true,
      "unknown_calls": 0,
      "assessment": {}
    }
  ],
  "limits": [
    {
      "task": "local-form",
      "tool_call_limit": 15,
      "timeout_s": 180,
      "gui_only": true
    }
  ]
}
```
