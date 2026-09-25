# computer_use benchmark

- Run label: `drag-file-r3-c`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| drag-file | 0/1 | 0% | 0%–79% | 15 | 7 | 20 | 15 | 64 | 251503 | 9 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| drag-file | 20 | 2.6 | 3.3 | 64 | 0.0 |

- API calls total: 20, mean 3.2s/call, median streamed ttft 2.6, LLM time total 64s

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
      "charged_tokens": 251503,
      "charged_nano_usd": 0,
      "known_tokens": 251503,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 31,
      "admitted_requests": 20
    },
    "trials": {
      "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-c/drag-file-r3-c/trials/drag-file/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 251503,
        "charged_nano_usd": 0,
        "known_tokens": 251503,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "7906716643d148e2a4d1bfd2eb8b98c9": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-c/drag-file-r3-c/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 3840,
        "output_tokens": 54,
        "status": "known"
      },
      "70f301bd32894425bb47255d6f224f08": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-c/drag-file-r3-c/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6308,
        "output_tokens": 142,
        "status": "known"
      },
      "8948a3418973416ebf516cdb9e3b9082": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-c/drag-file-r3-c/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2522,
        "output_tokens": 52,
        "status": "known"
      },
      "ba0f66cf2bee47249a21448017ca1080": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-c/drag-file-r3-c/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6544,
        "output_tokens": 86,
        "status": "known"
      },
      "7d94aafd343849ddadb072ec1982bf84": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-c/drag-file-r3-c/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8971,
        "output_tokens": 123,
        "status": "known"
      },
      "8f60e50c485342578bb2b480c854fc14": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-c/drag-file-r3-c/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8975,
        "output_tokens": 22,
        "status": "known"
      },
      "269da52f800044058efc47692d169c28": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-c/drag-file-r3-c/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11387,
        "output_tokens": 152,
        "status": "known"
      },
      "ad156161dc9a492693abede9c3bb5d3c": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-c/drag-file-r3-c/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2521,
        "output_tokens": 52,
        "status": "known"
      },
      "ac2e680d3256407b8644144a0cfb54ac": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-c/drag-file-r3-c/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11633,
        "output_tokens": 86,
        "status": "known"
      },
      "757b5cbaa87e4f4fb782fe3cbd7381d9": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-c/drag-file-r3-c/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 14188,
        "output_tokens": 76,
        "status": "known"
      },
      "4da57c663cef4a4487e270b3cd4b216f": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-c/drag-file-r3-c/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 16686,
        "output_tokens": 123,
        "status": "known"
      },
      "35df3ca154b745df92d1827f72474d43": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-c/drag-file-r3-c/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2508,
        "output_tokens": 52,
        "status": "known"
      },
      "d29920624ebf4f38896db4c13c43e5f0": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-c/drag-file-r3-c/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 16904,
        "output_tokens": 74,
        "status": "known"
      },
      "f121f34f53274afca9e8a357599089de": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-c/drag-file-r3-c/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 19404,
        "output_tokens": 111,
        "status": "known"
      },
      "6658e4e3842d44dd9c5679d937619d6a": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-c/drag-file-r3-c/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 19439,
        "output_tokens": 29,
        "status": "known"
      },
      "b069971fb8474b6ab2e4cdf9777b79ef": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-c/drag-file-r3-c/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 21859,
        "output_tokens": 117,
        "status": "known"
      },
      "c7e2f9df5272406a88696c8af9321fab": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-c/drag-file-r3-c/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2513,
        "output_tokens": 52,
        "status": "known"
      },
      "5977b260ec16449193f862894a16e0ea": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-c/drag-file-r3-c/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 22067,
        "output_tokens": 75,
        "status": "known"
      },
      "5e9958d1a73c438593775487e7fa13e8": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-c/drag-file-r3-c/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 24564,
        "output_tokens": 53,
        "status": "known"
      },
      "7a1b151744fc4036b713298e4ca623fd": {
        "trial": "/private/tmp/tank-m6-drag-file-20260925-live/trials/drag-file-r3-c/drag-file-r3-c/trials/drag-file/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 27033,
        "output_tokens": 106,
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
    "locator": 4,
    "total": 20,
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
