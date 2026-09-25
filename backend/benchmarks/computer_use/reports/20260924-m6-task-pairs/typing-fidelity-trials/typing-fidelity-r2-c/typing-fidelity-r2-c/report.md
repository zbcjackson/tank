# computer_use benchmark

- Run label: `typing-fidelity-r2-c`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| typing-fidelity | 0/1 | 0% | 0%–79% | 8 | 5 | 12 | 15 | 32 | 104096 | 5 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| typing-fidelity | 12 | 1.7 | 2.4 | 32 | 0.0 |

- API calls total: 12, mean 2.7s/call, median streamed ttft 1.7, LLM time total 32s

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
      "charged_tokens": 104096,
      "charged_nano_usd": 0,
      "known_tokens": 104096,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 31,
      "admitted_requests": 12
    },
    "trials": {
      "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r2-c/typing-fidelity-r2-c/trials/typing-fidelity/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 104096,
        "charged_nano_usd": 0,
        "known_tokens": 104096,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "00e5f167ac5a482e93c710bc1742361e": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r2-c/typing-fidelity-r2-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 3931,
        "output_tokens": 43,
        "status": "known"
      },
      "1163b941a2d14704874b401dd47e50dd": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r2-c/typing-fidelity-r2-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6396,
        "output_tokens": 35,
        "status": "known"
      },
      "addc12d958344762bfe0066bb9e12b75": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r2-c/typing-fidelity-r2-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8825,
        "output_tokens": 156,
        "status": "known"
      },
      "e26fb56ecf8945449477f38a54ec6ffc": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r2-c/typing-fidelity-r2-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2504,
        "output_tokens": 48,
        "status": "known"
      },
      "5525fcba66ac46c4ad361b4f475b4af7": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r2-c/typing-fidelity-r2-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9036,
        "output_tokens": 89,
        "status": "known"
      },
      "35bcc8a6e2744cca9493e3c4782cb51f": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r2-c/typing-fidelity-r2-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2509,
        "output_tokens": 52,
        "status": "known"
      },
      "7131d8e000e94f879c0523d6af5a4a9f": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r2-c/typing-fidelity-r2-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9216,
        "output_tokens": 80,
        "status": "known"
      },
      "c757d364f72441878b2d3c46d71dc3f4": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r2-c/typing-fidelity-r2-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11718,
        "output_tokens": 189,
        "status": "known"
      },
      "f2b37c75b5fa47669ff6974a3d3176bf": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r2-c/typing-fidelity-r2-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 14407,
        "output_tokens": 187,
        "status": "known"
      },
      "fde0611889ba430a90f6b5e4f3fcbf7a": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r2-c/typing-fidelity-r2-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2507,
        "output_tokens": 52,
        "status": "known"
      },
      "2cafe954bb3642b7be66317a12a5223b": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r2-c/typing-fidelity-r2-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 14685,
        "output_tokens": 72,
        "status": "known"
      },
      "403f7f529db541d6a727b79de0ae37a1": {
        "trial": "/private/tmp/tank-m6-typing-fidelity-20260925-live/trials/typing-fidelity-r2-c/typing-fidelity-r2-c/trials/typing-fidelity/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 17184,
        "output_tokens": 175,
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
    "planner": 9,
    "locator": 3,
    "total": 12,
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
      "task": "typing-fidelity",
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
      "task": "typing-fidelity",
      "tool_call_limit": 15,
      "timeout_s": 180,
      "gui_only": true
    }
  ]
}
```
