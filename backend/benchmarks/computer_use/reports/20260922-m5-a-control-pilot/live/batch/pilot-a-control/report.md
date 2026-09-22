# computer_use benchmark

- Run label: `pilot-a-control`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| calc-open | 0/1 | 0% | 0%–79% | 15 | 11 | 16 | 15 | 72 | 295443 | 11 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| calc-open | 16 | 2.3 | 3.2 | 63 | 0.0 |

- API calls total: 16, mean 3.9s/call, median streamed ttft 2.3, LLM time total 63s

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
    "freeze_dir": "/Users/zbcjackson/src/tank/backend/benchmarks/computer_use/reports/20260922-m5-record-only-runtime"
  },
  "budget_record_only": true,
  "configured_token_budget": 300000,
  "spend_budget": {
    "record_only": true,
    "cost_status": "unpriced",
    "batch": {
      "limit_tokens": 5100000,
      "limit_nano_usd": 8000000000,
      "charged_tokens": 295443,
      "charged_nano_usd": 0,
      "known_tokens": 295443,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 16,
      "admitted_requests": 16
    },
    "trials": {
      "/private/tmp/tank-m5-live-a-control-20260922/batch/pilot-a-control/trials/calc-open/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 295443,
        "charged_nano_usd": 0,
        "known_tokens": 295443,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "6502073b20ca4a86878e6035c904462d": {
        "trial": "/private/tmp/tank-m5-live-a-control-20260922/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7067,
        "output_tokens": 52,
        "status": "known"
      },
      "7fd860fe1db34ab0af5f6ce0d650ccf0": {
        "trial": "/private/tmp/tank-m5-live-a-control-20260922/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9540,
        "output_tokens": 348,
        "status": "known"
      },
      "d073cc0a11494516b939ca6850e914ea": {
        "trial": "/private/tmp/tank-m5-live-a-control-20260922/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7489,
        "output_tokens": 95,
        "status": "known"
      },
      "32428b2de75a494da38589b714284788": {
        "trial": "/private/tmp/tank-m5-live-a-control-20260922/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7125,
        "output_tokens": 23,
        "status": "known"
      },
      "5f0671a6849b40a89573975836bc9a2a": {
        "trial": "/private/tmp/tank-m5-live-a-control-20260922/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9525,
        "output_tokens": 54,
        "status": "known"
      },
      "c11d4decad144adbb842f80fe8fde498": {
        "trial": "/private/tmp/tank-m5-live-a-control-20260922/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11992,
        "output_tokens": 44,
        "status": "known"
      },
      "7c6d49965ecd42a69a714bbf3b2ecd52": {
        "trial": "/private/tmp/tank-m5-live-a-control-20260922/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 14455,
        "output_tokens": 49,
        "status": "known"
      },
      "09d3e1862c044460b870cc16d0271b43": {
        "trial": "/private/tmp/tank-m5-live-a-control-20260922/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 16921,
        "output_tokens": 96,
        "status": "known"
      },
      "a1762df613e4420d8887b641aaf75ab4": {
        "trial": "/private/tmp/tank-m5-live-a-control-20260922/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 19432,
        "output_tokens": 70,
        "status": "known"
      },
      "bcd0ceb542f541d985b01c21a27edf51": {
        "trial": "/private/tmp/tank-m5-live-a-control-20260922/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 21924,
        "output_tokens": 58,
        "status": "known"
      },
      "c29186d1a12f41f6845cb343c857c063": {
        "trial": "/private/tmp/tank-m5-live-a-control-20260922/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 24399,
        "output_tokens": 144,
        "status": "known"
      },
      "915e3cfcd8ec47a7b255ccb02470eca0": {
        "trial": "/private/tmp/tank-m5-live-a-control-20260922/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 24571,
        "output_tokens": 22,
        "status": "known"
      },
      "06154d457e90498384c47b9f47ced811": {
        "trial": "/private/tmp/tank-m5-live-a-control-20260922/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 26983,
        "output_tokens": 73,
        "status": "known"
      },
      "b986ac756cee4e10be572d6cdd6cd7bd": {
        "trial": "/private/tmp/tank-m5-live-a-control-20260922/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 29575,
        "output_tokens": 476,
        "status": "known"
      },
      "93261036f6d94422b3404ad50f3fcd11": {
        "trial": "/private/tmp/tank-m5-live-a-control-20260922/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 30103,
        "output_tokens": 28,
        "status": "known"
      },
      "9f5ba11c5ae14183a08d48f5be873b86": {
        "trial": "/private/tmp/tank-m5-live-a-control-20260922/batch/pilot-a-control/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 32520,
        "output_tokens": 190,
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
  "git_revision": "5ace038d92d4ecbe37f325b7429405bcb27d2678",
  "task_revision": "a4cdec43b05afd51461bbb2dd695a77f79d71ea87bfb785634d0b8c0092647c8",
  "scoring_revision": "trial-token-gui-grounding-v5",
  "aborted_cleanup": false,
  "outcomes": [
    {
      "task": "calc-open",
      "trial": 1,
      "stop_reason": null,
      "cleanup": "unknown",
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
          "sha256": "d28491a446925498cba09b18cc0379a0ff3a4484fc404a5f13c77ad0afe0ca47",
          "file": "screenshots/shot_011.png",
          "captured_at": 1790074221.8164968,
          "http_serialized_at": 1790074221.84693
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
