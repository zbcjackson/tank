# computer_use benchmark

- Run label: `file-ops-r1-a`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| file-ops | 0/1 | 0% | 0%–79% | 15 | 13 | 16 | 15 | 37 | 116361 | 2 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| file-ops | 16 | 1.3 | 1.8 | 37 | 0.0 |

- API calls total: 16, mean 2.3s/call, median streamed ttft 1.3, LLM time total 37s

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
      "charged_tokens": 116361,
      "charged_nano_usd": 0,
      "known_tokens": 116361,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 16,
      "admitted_requests": 16
    },
    "trials": {
      "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-a/file-ops-r1-a/trials/file-ops/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 116361,
        "charged_nano_usd": 0,
        "known_tokens": 116361,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "c7ac45dfe1a74830a1b98d8bd52a42ac": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-a/file-ops-r1-a/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5124,
        "output_tokens": 107,
        "status": "known"
      },
      "b88c673f5663406bbabd48c6511494d9": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-a/file-ops-r1-a/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5261,
        "output_tokens": 29,
        "status": "known"
      },
      "b46c9a96a6f246c4a03313b7360e0b4d": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-a/file-ops-r1-a/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5315,
        "output_tokens": 32,
        "status": "known"
      },
      "db14ec9152c7492891f2549844fa3bae": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-a/file-ops-r1-a/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5393,
        "output_tokens": 25,
        "status": "known"
      },
      "2f00bee1422c42eb8d4510ecaca53717": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-a/file-ops-r1-a/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5439,
        "output_tokens": 13,
        "status": "known"
      },
      "a7950920691c457db4179984d403d322": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-a/file-ops-r1-a/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7602,
        "output_tokens": 84,
        "status": "known"
      },
      "9b65f13eeaeb4154aa14706aa1fa543a": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-a/file-ops-r1-a/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7734,
        "output_tokens": 27,
        "status": "known"
      },
      "39db6657cecd4b71bd762fcdcd1ba16d": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-a/file-ops-r1-a/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7782,
        "output_tokens": 27,
        "status": "known"
      },
      "0112c236c994468c87538bde94f46509": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-a/file-ops-r1-a/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7830,
        "output_tokens": 68,
        "status": "known"
      },
      "c2bc07b4f7be406495da201a0f8c9c12": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-a/file-ops-r1-a/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7193,
        "output_tokens": 50,
        "status": "known"
      },
      "3d1799e865c24b0ba4b9811453eb5eef": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-a/file-ops-r1-a/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7287,
        "output_tokens": 27,
        "status": "known"
      },
      "5ab9f54c148149cc873aa741a3a3a1c6": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-a/file-ops-r1-a/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7335,
        "output_tokens": 27,
        "status": "known"
      },
      "2ed6d2231fab49529d956ab76a864a73": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-a/file-ops-r1-a/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7383,
        "output_tokens": 14,
        "status": "known"
      },
      "572d825af12447cb917028621ba50a53": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-a/file-ops-r1-a/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9533,
        "output_tokens": 55,
        "status": "known"
      },
      "b3d94a6b147f4a1dbc42142b8fad9d30": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-a/file-ops-r1-a/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9670,
        "output_tokens": 60,
        "status": "known"
      },
      "29134708705a4e0cbeadbc8c29fb1056": {
        "trial": "/private/tmp/tank-m6-file-ops-20260925-live/trials/file-ops-r1-a/file-ops-r1-a/trials/file-ops/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9778,
        "output_tokens": 57,
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
