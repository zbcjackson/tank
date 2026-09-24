# computer_use benchmark

- Run label: `m6-pair-2-a`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **1/1** (100%, 95% CI 21%–100%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| calc-open | 1/1 | 100% | 21%–100% | 9 | 8 | 10 | 15 | 42 | 106357 | 4 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| calc-open | 10 | 2.1 | 2.5 | 33 | 0.0 |

- API calls total: 10, mean 3.3s/call, median streamed ttft 2.1, LLM time total 33s

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
      "charged_tokens": 106357,
      "charged_nano_usd": 0,
      "known_tokens": 106357,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 16,
      "admitted_requests": 10
    },
    "trials": {
      "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-a/m6-pair-2-a/trials/calc-open/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 106357,
        "charged_nano_usd": 0,
        "known_tokens": 106357,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "30a51668bb754a81bebb54f72bc12d9a": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-a/m6-pair-2-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5095,
        "output_tokens": 27,
        "status": "known"
      },
      "7cd3ba29310a45d299cc893865dd15c9": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-a/m6-pair-2-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5152,
        "output_tokens": 13,
        "status": "known"
      },
      "d990a1c388c143c8a8e90eb6551a4e24": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-a/m6-pair-2-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7327,
        "output_tokens": 249,
        "status": "known"
      },
      "8850a6c300074fbe9c0845849256b1b8": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-a/m6-pair-2-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9544,
        "output_tokens": 96,
        "status": "known"
      },
      "9663076bd70b42688ea5bf0838a49b6b": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-a/m6-pair-2-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 12056,
        "output_tokens": 488,
        "status": "known"
      },
      "c3ee13c69bac4979a0619eabde6109b9": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-a/m6-pair-2-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 12592,
        "output_tokens": 57,
        "status": "known"
      },
      "a513492c03d842f3af906b276ac6a5dc": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-a/m6-pair-2-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 12697,
        "output_tokens": 53,
        "status": "known"
      },
      "df3e64420266475e9ae3cf8795a538eb": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-a/m6-pair-2-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 12798,
        "output_tokens": 55,
        "status": "known"
      },
      "7e9c8e83610044cbb262f9bf175bfe7b": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-a/m6-pair-2-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 12901,
        "output_tokens": 24,
        "status": "known"
      },
      "c8ccd15ec3484fa9adf3223be26f5a90": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-a/m6-pair-2-a/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 15073,
        "output_tokens": 60,
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
    "planner": 10,
    "locator": 0,
    "total": 10,
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
  "git_revision": "b6a04c23be5f835822ab25486b81df84df67379b",
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
      "success": true,
      "unknown_calls": 0,
      "assessment": {
        "revision": "calc-evidence-v1",
        "strict_expression": true,
        "business": null,
        "mouse_only": null,
        "pixels": "unknown",
        "reset_verified": true,
        "input_trace_complete": false,
        "display": {
          "expression": "7×8",
          "result": "56"
        },
        "last_screenshot": {
          "sha256": "adf890c0ed8d18db0e8f74753c9d80c11e7e40021fab9c747a1b796f3684391b",
          "file": "screenshots/shot_004.png",
          "captured_at": 1790261198.119595,
          "http_serialized_at": 1790261198.134597
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
