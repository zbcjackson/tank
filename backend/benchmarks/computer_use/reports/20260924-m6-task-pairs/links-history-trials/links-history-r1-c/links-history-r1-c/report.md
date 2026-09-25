# computer_use benchmark

- Run label: `links-history-r1-c`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| links-history | 0/1 | 0% | 0%–79% | 13 | 8 | 18 | 15 | 50 | 225361 | 9 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| links-history | 18 | 1.8 | 2.6 | 50 | 0.0 |

- API calls total: 18, mean 2.8s/call, median streamed ttft 1.8, LLM time total 50s

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
      "charged_tokens": 225361,
      "charged_nano_usd": 0,
      "known_tokens": 225361,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 31,
      "admitted_requests": 18
    },
    "trials": {
      "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r1-c/links-history-r1-c/trials/links-history/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 225361,
        "charged_nano_usd": 0,
        "known_tokens": 225361,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "446273611abf489bb3ba21b79374e3c0": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r1-c/links-history-r1-c/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 3902,
        "output_tokens": 61,
        "status": "known"
      },
      "835c71d8348745c7be47c656b7e907b9": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r1-c/links-history-r1-c/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6377,
        "output_tokens": 95,
        "status": "known"
      },
      "dcba3eb31b5a4730ad0a9a2f29729220": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r1-c/links-history-r1-c/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8214,
        "output_tokens": 161,
        "status": "known"
      },
      "84aa3c39742f4cb2bac1a10d48a6fbfc": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r1-c/links-history-r1-c/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2504,
        "output_tokens": 52,
        "status": "known"
      },
      "5352cd7ad4504ef397ca7619cd04fa38": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r1-c/links-history-r1-c/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8467,
        "output_tokens": 61,
        "status": "known"
      },
      "94d1e820102b4c809407c21b947312ca": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r1-c/links-history-r1-c/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10957,
        "output_tokens": 73,
        "status": "known"
      },
      "2bdcc7a6a0274cb49e56c23347aee656": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r1-c/links-history-r1-c/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 13449,
        "output_tokens": 93,
        "status": "known"
      },
      "dd8a9f88d89e481ba7b3c1b893711d00": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r1-c/links-history-r1-c/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2505,
        "output_tokens": 52,
        "status": "known"
      },
      "ff6f92c4bca04eea9ae4e69193626d9b": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r1-c/links-history-r1-c/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 13634,
        "output_tokens": 65,
        "status": "known"
      },
      "c62eab3fce79472cbf72f8fe9111acba": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r1-c/links-history-r1-c/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 16124,
        "output_tokens": 61,
        "status": "known"
      },
      "fb620a866e354ea49b57f44c8f637a4e": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r1-c/links-history-r1-c/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 18590,
        "output_tokens": 94,
        "status": "known"
      },
      "e51e97a0ab9241fda930a050dcf2e5c3": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r1-c/links-history-r1-c/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2505,
        "output_tokens": 52,
        "status": "known"
      },
      "9bd3380c98c540749ff9a712c99a2434": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r1-c/links-history-r1-c/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 18777,
        "output_tokens": 65,
        "status": "known"
      },
      "b47c5e10e290435a96d793a13b917c0e": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r1-c/links-history-r1-c/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 21263,
        "output_tokens": 72,
        "status": "known"
      },
      "63079dea5dd04d3ea8acec84b5944465": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r1-c/links-history-r1-c/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 23752,
        "output_tokens": 96,
        "status": "known"
      },
      "6ac84718bab14f20a68ceae9e9b903b6": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r1-c/links-history-r1-c/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2500,
        "output_tokens": 52,
        "status": "known"
      },
      "49137987e75843a8a7391a756dc3ae8a": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r1-c/links-history-r1-c/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 23942,
        "output_tokens": 68,
        "status": "known"
      },
      "e468535ba82640ef933345641fa335cf": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r1-c/links-history-r1-c/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 26434,
        "output_tokens": 192,
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
    "planner": 14,
    "locator": 4,
    "total": 18,
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
      "task": "links-history",
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
      "task": "links-history",
      "tool_call_limit": 15,
      "timeout_s": 180,
      "gui_only": true
    }
  ]
}
```
