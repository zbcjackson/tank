# computer_use benchmark

- Run label: `terminal-write-r1-a`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **1/1** (100%, 95% CI 21%–100%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| terminal-write | 1/1 | 100% | 21%–100% | 10 | 10 | 11 | 15 | 28 | 93155 | 3 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| terminal-write | 11 | 1.7 | 2.2 | 27 | 0.0 |

- API calls total: 11, mean 2.5s/call, median streamed ttft 1.7, LLM time total 27s

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
      "charged_tokens": 93155,
      "charged_nano_usd": 0,
      "known_tokens": 93155,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 16,
      "admitted_requests": 11
    },
    "trials": {
      "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r1-a/terminal-write-r1-a/trials/terminal-write/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 93155,
        "charged_nano_usd": 0,
        "known_tokens": 93155,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "9bbbbb82c01345cead7ad1516e85ca75": {
        "trial": "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r1-a/terminal-write-r1-a/trials/terminal-write/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5100,
        "output_tokens": 43,
        "status": "known"
      },
      "77cc5d4989694d3387c895961c91c423": {
        "trial": "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r1-a/terminal-write-r1-a/trials/terminal-write/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5173,
        "output_tokens": 13,
        "status": "known"
      },
      "3de9f4221dcb4b259565744c07dbf87c": {
        "trial": "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r1-a/terminal-write-r1-a/trials/terminal-write/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7348,
        "output_tokens": 66,
        "status": "known"
      },
      "99ca64cde4814d8f843ffde6ef4f5c05": {
        "trial": "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r1-a/terminal-write-r1-a/trials/terminal-write/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7462,
        "output_tokens": 47,
        "status": "known"
      },
      "9795d467780145c38d3e1eadc325b8ac": {
        "trial": "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r1-a/terminal-write-r1-a/trials/terminal-write/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7556,
        "output_tokens": 38,
        "status": "known"
      },
      "6647a09c415e476cb5e7bc11544896b6": {
        "trial": "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r1-a/terminal-write-r1-a/trials/terminal-write/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7614,
        "output_tokens": 33,
        "status": "known"
      },
      "008ee309a779498db0a9a206805b17f6": {
        "trial": "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r1-a/terminal-write-r1-a/trials/terminal-write/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9799,
        "output_tokens": 110,
        "status": "known"
      },
      "6cc1bd31dba24d64aa8d8021ff2b6878": {
        "trial": "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r1-a/terminal-write-r1-a/trials/terminal-write/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9957,
        "output_tokens": 72,
        "status": "known"
      },
      "0be9d107bacf48a4ad40726187758522": {
        "trial": "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r1-a/terminal-write-r1-a/trials/terminal-write/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10076,
        "output_tokens": 38,
        "status": "known"
      },
      "00a82e9d59874048ad223a395505d73b": {
        "trial": "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r1-a/terminal-write-r1-a/trials/terminal-write/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10134,
        "output_tokens": 33,
        "status": "known"
      },
      "5495039498af4354aa2e3ef54aa60996": {
        "trial": "/private/tmp/tank-m6-terminal-write-20260925-live/trials/terminal-write-r1-a/terminal-write-r1-a/trials/terminal-write/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 12319,
        "output_tokens": 124,
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
    "planner": 11,
    "locator": 0,
    "total": 11,
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
      "task": "terminal-write",
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
      "task": "terminal-write",
      "tool_call_limit": 15,
      "timeout_s": 120,
      "gui_only": true
    }
  ]
}
```
