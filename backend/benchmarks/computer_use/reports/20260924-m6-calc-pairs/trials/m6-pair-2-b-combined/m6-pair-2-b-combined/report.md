# computer_use benchmark

- Run label: `m6-pair-2-b-combined`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| calc-open | 0/1 | 0% | 0%–79% | 15 | 6 | 16 | 15 | 85 | 285140 | 9 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| calc-open | 16 | 2.2 | 3.6 | 76 | 0.0 |

- API calls total: 16, mean 4.7s/call, median streamed ttft 2.2, LLM time total 76s

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
    "variant": "B-combined",
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
      "charged_tokens": 285140,
      "charged_nano_usd": 0,
      "known_tokens": 285140,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 16,
      "admitted_requests": 16
    },
    "trials": {
      "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-b-combined/m6-pair-2-b-combined/trials/calc-open/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 285140,
        "charged_nano_usd": 0,
        "known_tokens": 285140,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "aa1c8f6c600a4a9c9af04afdb252e779": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-b-combined/m6-pair-2-b-combined/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 4740,
        "output_tokens": 54,
        "status": "known"
      },
      "7ee9e9fd5814463c8fcf3b2e8351bddd": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-b-combined/m6-pair-2-b-combined/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7209,
        "output_tokens": 354,
        "status": "known"
      },
      "21f3679ab09044148ec97387d63f1ec5": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-b-combined/m6-pair-2-b-combined/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8862,
        "output_tokens": 138,
        "status": "known"
      },
      "7194e9c554fb45909164b74e0d724d6e": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-b-combined/m6-pair-2-b-combined/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11509,
        "output_tokens": 820,
        "status": "known"
      },
      "6f244aac03a64942b9869ec0dd266b21": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-b-combined/m6-pair-2-b-combined/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 12358,
        "output_tokens": 110,
        "status": "known"
      },
      "63127c74d437402e8e886247fe7ffb90": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-b-combined/m6-pair-2-b-combined/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 14906,
        "output_tokens": 132,
        "status": "known"
      },
      "8a0ef55ea78948a4add57a94b968cd4b": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-b-combined/m6-pair-2-b-combined/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 17274,
        "output_tokens": 895,
        "status": "known"
      },
      "0511e1684d764b4493684e72b5e9616c": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-b-combined/m6-pair-2-b-combined/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 18194,
        "output_tokens": 37,
        "status": "known"
      },
      "bfc338c2aa6a4790a530cce248d5e039": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-b-combined/m6-pair-2-b-combined/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 20616,
        "output_tokens": 155,
        "status": "known"
      },
      "4485ed28dc8a425a9d8a9d34e7f3466a": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-b-combined/m6-pair-2-b-combined/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 20823,
        "output_tokens": 84,
        "status": "known"
      },
      "76a2f4182b33452481be86cd2ef20610": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-b-combined/m6-pair-2-b-combined/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 20959,
        "output_tokens": 124,
        "status": "known"
      },
      "228a14bb910a40de8604a33d94082aa8": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-b-combined/m6-pair-2-b-combined/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 21139,
        "output_tokens": 67,
        "status": "known"
      },
      "f71d4e36347c464eb45e052ea9863729": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-b-combined/m6-pair-2-b-combined/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 23709,
        "output_tokens": 256,
        "status": "known"
      },
      "40cffad9e98a48eabd0ad576d4a84897": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-b-combined/m6-pair-2-b-combined/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 24026,
        "output_tokens": 45,
        "status": "known"
      },
      "e2bb6046521d4588ae93e7c1952b2ab9": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-b-combined/m6-pair-2-b-combined/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 26459,
        "output_tokens": 101,
        "status": "known"
      },
      "0c243e526011427e80ddad82d364934a": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-2-b-combined/m6-pair-2-b-combined/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 28931,
        "output_tokens": 54,
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
    "protocol": "point",
    "nullable_style": "integer",
    "strict": false,
    "detail": "auto",
    "status_field": false,
    "mode": "integrated",
    "host_restore": true
  },
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
          "result": "7"
        },
        "last_screenshot": {
          "sha256": "012fbce013908085f665bb426bbebd943e2c57ab5ec688b62dce1f8b26765be5",
          "file": "screenshots/shot_009.png",
          "captured_at": 1790261019.8887308,
          "http_serialized_at": 1790261019.924758
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
