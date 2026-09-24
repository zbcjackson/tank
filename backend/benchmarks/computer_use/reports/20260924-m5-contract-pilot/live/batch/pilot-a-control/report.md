# computer_use benchmark

- Run label: `pilot-a-control`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| calc-open | 0/1 | 0% | 0%–79% | 15 | 17 | 16 | 15 | 85 | 398902 | 12 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| calc-open | 16 | 2.5 | 5.0 | 75 | 0.0 |

- API calls total: 16, mean 4.7s/call, median streamed ttft 2.5, LLM time total 75s

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
    "variant": "A-control",
    "freeze_dir": "/Users/zbcjackson/src/tank/backend/benchmarks/computer_use/reports/20260924-m5-contract-runtime"
  },
  "input_cleanup": true,
  "budget_record_only": true,
  "configured_token_budget": 300000,
  "spend_budget": {
    "record_only": true,
    "cost_status": "unpriced",
    "batch": {
      "limit_tokens": 300000,
      "limit_nano_usd": 8000000000,
      "charged_tokens": 398902,
      "charged_nano_usd": 0,
      "known_tokens": 398902,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 16,
      "admitted_requests": 16
    },
    "trials": {
      "/private/tmp/tank-m5-a-control-20260924-contract-live/batch/pilot-a-control/trials/calc-open/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 398902,
        "charged_nano_usd": 0,
        "known_tokens": 398902,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "9ed3e68e26a0410baa5e82310ad5252c": {
        "trial": "/private/tmp/tank-m5-a-control-20260924-contract-live/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7178,
        "output_tokens": 54,
        "status": "known"
      },
      "707067ffcd6744b8b05b96243ff44d77": {
        "trial": "/private/tmp/tank-m5-a-control-20260924-contract-live/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9645,
        "output_tokens": 397,
        "status": "known"
      },
      "e81d05a170fd442591eaf034949d4aff": {
        "trial": "/private/tmp/tank-m5-a-control-20260924-contract-live/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 12681,
        "output_tokens": 42,
        "status": "known"
      },
      "febb59e5105b4d56a1ed3d6788c2d9c1": {
        "trial": "/private/tmp/tank-m5-a-control-20260924-contract-live/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 15115,
        "output_tokens": 49,
        "status": "known"
      },
      "6bc3c0b886f94b98999741020dde99ba": {
        "trial": "/private/tmp/tank-m5-a-control-20260924-contract-live/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 17581,
        "output_tokens": 411,
        "status": "known"
      },
      "3b5bfaee597d4c828dacad00b28c32db": {
        "trial": "/private/tmp/tank-m5-a-control-20260924-contract-live/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 20631,
        "output_tokens": 62,
        "status": "known"
      },
      "3f3738ae9e8a40ddab9e373f9fc73dce": {
        "trial": "/private/tmp/tank-m5-a-control-20260924-contract-live/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 23110,
        "output_tokens": 97,
        "status": "known"
      },
      "93dd31cd7d5340d584392576f71919f9": {
        "trial": "/private/tmp/tank-m5-a-control-20260924-contract-live/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 26086,
        "output_tokens": 460,
        "status": "known"
      },
      "37ccdb6d3c3b466f830a7d5d5bb4faed": {
        "trial": "/private/tmp/tank-m5-a-control-20260924-contract-live/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 26085,
        "output_tokens": 24,
        "status": "known"
      },
      "553581d118ae4975bbe912e0354fe19e": {
        "trial": "/private/tmp/tank-m5-a-control-20260924-contract-live/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 28504,
        "output_tokens": 120,
        "status": "known"
      },
      "412734041ef34b4d8654a3bbaba18d9c": {
        "trial": "/private/tmp/tank-m5-a-control-20260924-contract-live/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 30995,
        "output_tokens": 56,
        "status": "known"
      },
      "c4a0a34dd7834cb2a7b57b70f49dd0ec": {
        "trial": "/private/tmp/tank-m5-a-control-20260924-contract-live/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 33474,
        "output_tokens": 131,
        "status": "known"
      },
      "d64bb388d67546f487e8327014d965fa": {
        "trial": "/private/tmp/tank-m5-a-control-20260924-contract-live/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 33630,
        "output_tokens": 25,
        "status": "known"
      },
      "8d80f6954e0147319766969514815fbb": {
        "trial": "/private/tmp/tank-m5-a-control-20260924-contract-live/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 36038,
        "output_tokens": 164,
        "status": "known"
      },
      "4b648e0524d149f49724899b8d9b6005": {
        "trial": "/private/tmp/tank-m5-a-control-20260924-contract-live/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 36254,
        "output_tokens": 78,
        "status": "known"
      },
      "7294d48dd81440449830e82a19b01d10": {
        "trial": "/private/tmp/tank-m5-a-control-20260924-contract-live/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 39206,
        "output_tokens": 519,
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
  "grounding": {
    "profile": null,
    "fallback_profile": null,
    "protocol": "legacy",
    "nullable_style": "integer",
    "strict": false,
    "detail": "auto",
    "status_field": false,
    "mode": "integrated",
    "host_restore": false
  },
  "token_budget": 0,
  "platform": "macos",
  "git_revision": "76fb99e53d57879af33eaa167671e9960e91d311",
  "task_revision": "a4cdec43b05afd51461bbb2dd695a77f79d71ea87bfb785634d0b8c0092647c8",
  "scoring_revision": "trial-token-gui-grounding-v5",
  "aborted_cleanup": false,
  "outcomes": [
    {
      "task": "calc-open",
      "trial": 1,
      "stop_reason": null,
      "cleanup": "confirmed",
      "scoring": "strict",
      "success": false,
      "unknown_calls": 0,
      "assessment": {
        "revision": "calc-evidence-v1",
        "strict_expression": false,
        "business": null,
        "mouse_only": null,
        "pixels": "unknown",
        "reset_verified": true,
        "input_trace_complete": false,
        "display": {
          "result": "0"
        },
        "last_screenshot": {
          "sha256": "2ac0715a6b6b0ba0e76099c4b5cf1d67849c9943c2971e724ec8a643793076db",
          "file": "screenshots/shot_012.png",
          "captured_at": 1790218736.966463,
          "http_serialized_at": 1790218736.998801
        }
      }
    }
  ],
  "limits": [
    {
      "task": "calc-open",
      "tool_call_limit": 15,
      "timeout_s": 120,
      "gui_only": true
    }
  ]
}
```
