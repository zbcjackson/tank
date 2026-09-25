# computer_use benchmark

- Run label: `small-text-code-r1-a`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| small-text-code | 0/1 | 0% | 0%–79% | 15 | 14 | 16 | 15 | 45 | 155360 | 5 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| small-text-code | 16 | 1.5 | 2.6 | 45 | 0.0 |

- API calls total: 16, mean 2.8s/call, median streamed ttft 1.5, LLM time total 45s

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
      "charged_tokens": 155360,
      "charged_nano_usd": 0,
      "known_tokens": 155360,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 16,
      "admitted_requests": 16
    },
    "trials": {
      "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r1-a/small-text-code-r1-a/trials/small-text-code/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 155360,
        "charged_nano_usd": 0,
        "known_tokens": 155360,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "5720d9280e8a475591727c5861bd3ff6": {
        "trial": "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r1-a/small-text-code-r1-a/trials/small-text-code/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5149,
        "output_tokens": 43,
        "status": "known"
      },
      "edd73bdb89b841eba58d54bd61928e8d": {
        "trial": "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r1-a/small-text-code-r1-a/trials/small-text-code/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5223,
        "output_tokens": 121,
        "status": "known"
      },
      "bd0d0a7033534a76a838fb12e2a55273": {
        "trial": "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r1-a/small-text-code-r1-a/trials/small-text-code/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7582,
        "output_tokens": 96,
        "status": "known"
      },
      "547409516f2641e1831c54eb4df41c63": {
        "trial": "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r1-a/small-text-code-r1-a/trials/small-text-code/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8693,
        "output_tokens": 137,
        "status": "known"
      },
      "0307ebe776c34d148068468d307fd492": {
        "trial": "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r1-a/small-text-code-r1-a/trials/small-text-code/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8586,
        "output_tokens": 108,
        "status": "known"
      },
      "965b207dbae74aa29dfae346af562617": {
        "trial": "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r1-a/small-text-code-r1-a/trials/small-text-code/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8723,
        "output_tokens": 54,
        "status": "known"
      },
      "57859d039be44cd3b590e8ec5baa4421": {
        "trial": "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r1-a/small-text-code-r1-a/trials/small-text-code/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8072,
        "output_tokens": 77,
        "status": "known"
      },
      "68e56449429b44ac8813e66386dd2cdd": {
        "trial": "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r1-a/small-text-code-r1-a/trials/small-text-code/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8197,
        "output_tokens": 48,
        "status": "known"
      },
      "18c9addb13ff41538d7defd727ca8f6d": {
        "trial": "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r1-a/small-text-code-r1-a/trials/small-text-code/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8288,
        "output_tokens": 77,
        "status": "known"
      },
      "afce597032e8418b894e8fe7cb12ce65": {
        "trial": "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r1-a/small-text-code-r1-a/trials/small-text-code/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8413,
        "output_tokens": 25,
        "status": "known"
      },
      "b6834f9016fa4e208a4df27221347471": {
        "trial": "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r1-a/small-text-code-r1-a/trials/small-text-code/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10578,
        "output_tokens": 145,
        "status": "known"
      },
      "eed0aa056bfc4d2c8e87370302a32b91": {
        "trial": "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r1-a/small-text-code-r1-a/trials/small-text-code/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 12602,
        "output_tokens": 149,
        "status": "known"
      },
      "da0b518f79934c12ad3be68296a54238": {
        "trial": "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r1-a/small-text-code-r1-a/trials/small-text-code/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 12799,
        "output_tokens": 48,
        "status": "known"
      },
      "332302b483074e389156f4af80ea147e": {
        "trial": "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r1-a/small-text-code-r1-a/trials/small-text-code/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 12890,
        "output_tokens": 75,
        "status": "known"
      },
      "a090982981754d2c9eecc62aaf20389f": {
        "trial": "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r1-a/small-text-code-r1-a/trials/small-text-code/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 13013,
        "output_tokens": 25,
        "status": "known"
      },
      "5b6027d149484212baa700a5d366b82a": {
        "trial": "/private/tmp/tank-m6-small-text-code-20260925-live/trials/small-text-code-r1-a/small-text-code-r1-a/trials/small-text-code/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 15190,
        "output_tokens": 134,
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
      "task": "small-text-code",
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
      "task": "small-text-code",
      "tool_call_limit": 15,
      "timeout_s": 180,
      "gui_only": true
    }
  ]
}
```
