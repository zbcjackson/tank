# computer_use benchmark

- Run label: `links-history-r2-a`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| links-history | 0/1 | 0% | 0%–79% | 15 | 15 | 16 | 15 | 41 | 190730 | 6 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| links-history | 16 | 1.4 | 2.1 | 41 | 0.0 |

- API calls total: 16, mean 2.5s/call, median streamed ttft 1.4, LLM time total 41s

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
      "charged_tokens": 190730,
      "charged_nano_usd": 0,
      "known_tokens": 190730,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 16,
      "admitted_requests": 16
    },
    "trials": {
      "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r2-a/links-history-r2-a/trials/links-history/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 190730,
        "charged_nano_usd": 0,
        "known_tokens": 190730,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "c24507b4e2ff45278582b87024bbdbeb": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r2-a/links-history-r2-a/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5172,
        "output_tokens": 43,
        "status": "known"
      },
      "198db8066ff84450aac9e2fca04b0585": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r2-a/links-history-r2-a/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 5246,
        "output_tokens": 13,
        "status": "known"
      },
      "af596cd21e8742298af165517cf3a5a1": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r2-a/links-history-r2-a/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7421,
        "output_tokens": 199,
        "status": "known"
      },
      "a00aa8d6687c43b48e012a379e1f7285": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r2-a/links-history-r2-a/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7665,
        "output_tokens": 75,
        "status": "known"
      },
      "3ab34c773d0144b585460eb1a6193347": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r2-a/links-history-r2-a/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7825,
        "output_tokens": 29,
        "status": "known"
      },
      "143dfe57ca0943de96241944c8359f9a": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r2-a/links-history-r2-a/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 7874,
        "output_tokens": 14,
        "status": "known"
      },
      "fce34f0256684d6b92d4e38f16a94fa4": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r2-a/links-history-r2-a/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10040,
        "output_tokens": 211,
        "status": "known"
      },
      "f3afbc0fa30b43c2a77fcd31bdd83cdb": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r2-a/links-history-r2-a/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 10298,
        "output_tokens": 41,
        "status": "known"
      },
      "354aa4997ef44b2c9e4a79e789426986": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r2-a/links-history-r2-a/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 12499,
        "output_tokens": 80,
        "status": "known"
      },
      "d663588fb6954083b988ca27202f07ff": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r2-a/links-history-r2-a/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 12600,
        "output_tokens": 40,
        "status": "known"
      },
      "c1988982e847436383b6dfb6028b65a5": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r2-a/links-history-r2-a/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 14800,
        "output_tokens": 79,
        "status": "known"
      },
      "37bf67d4b6454e099b9a9bc28feab1d2": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r2-a/links-history-r2-a/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 14926,
        "output_tokens": 42,
        "status": "known"
      },
      "b96c0b680a324f7b8f567ce54395ef5e": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r2-a/links-history-r2-a/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 17128,
        "output_tokens": 59,
        "status": "known"
      },
      "dd6a554e41c04661bf327fbadc63ce7c": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r2-a/links-history-r2-a/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 17208,
        "output_tokens": 40,
        "status": "known"
      },
      "8d1ee5433d7c4e92906883d499e11503": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r2-a/links-history-r2-a/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 19408,
        "output_tokens": 79,
        "status": "known"
      },
      "fad3f07e877b49548b6c181882765001": {
        "trial": "/private/tmp/tank-m6-links-history-20260925-live/trials/links-history-r2-a/links-history-r2-a/trials/links-history/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 19534,
        "output_tokens": 42,
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
