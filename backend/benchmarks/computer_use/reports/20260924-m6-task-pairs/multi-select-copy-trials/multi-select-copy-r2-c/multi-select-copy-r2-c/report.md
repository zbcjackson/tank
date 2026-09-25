# computer_use benchmark

- Run label: `multi-select-copy-r2-c`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **0/1** (0%, 95% CI 0%–79%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| multi-select-copy | 0/1 | 0% | 0%–79% | 15 | 7 | 20 | 15 | 62 | 257769 | 8 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| multi-select-copy | 20 | 2.3 | 3.0 | 62 | 0.0 |

- API calls total: 20, mean 3.1s/call, median streamed ttft 2.3, LLM time total 62s

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
      "charged_tokens": 257769,
      "charged_nano_usd": 0,
      "known_tokens": 257769,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 31,
      "admitted_requests": 20
    },
    "trials": {
      "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-c/multi-select-copy-r2-c/trials/multi-select-copy/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 257769,
        "charged_nano_usd": 0,
        "known_tokens": 257769,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "61e7ff80bc80446591eb16905b37d538": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-c/multi-select-copy-r2-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 3871,
        "output_tokens": 53,
        "status": "known"
      },
      "b80cfb54e1244138a79dc6c1772334c5": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-c/multi-select-copy-r2-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6335,
        "output_tokens": 95,
        "status": "known"
      },
      "0f35f5bbf5744d2aa1a10d9270c29ba7": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-c/multi-select-copy-r2-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8886,
        "output_tokens": 138,
        "status": "known"
      },
      "bd1191afbc5c49969f401c98c3cd9f84": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-c/multi-select-copy-r2-c/trials/multi-select-copy/1",
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
      "38a8fba9275d4ca8b58104588a12b73e": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-c/multi-select-copy-r2-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 9116,
        "output_tokens": 75,
        "status": "known"
      },
      "edb65de4c21d43d29947b3aaed1c3523": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-c/multi-select-copy-r2-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11539,
        "output_tokens": 160,
        "status": "known"
      },
      "68086bcdf5814d90bf95794ac57c55bf": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-c/multi-select-copy-r2-c/trials/multi-select-copy/1",
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
      "5c2734f53ec0401eab22940475ecc0d6": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-c/multi-select-copy-r2-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11794,
        "output_tokens": 81,
        "status": "known"
      },
      "f7eb443bf8464276a20534c9d9c56ed5": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-c/multi-select-copy-r2-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 14309,
        "output_tokens": 78,
        "status": "known"
      },
      "2a475a35033840da9553b220fc306584": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-c/multi-select-copy-r2-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 16805,
        "output_tokens": 123,
        "status": "known"
      },
      "9c32ca00fa574174b873f89ef205eea1": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-c/multi-select-copy-r2-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 16852,
        "output_tokens": 89,
        "status": "known"
      },
      "6c0f41cdb03c4e25ac2fdfec8720297a": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-c/multi-select-copy-r2-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2507,
        "output_tokens": 48,
        "status": "known"
      },
      "f5756386b6914f98829bcdba2678963a": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-c/multi-select-copy-r2-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 17000,
        "output_tokens": 71,
        "status": "known"
      },
      "32d9c510009d460fafb900e9ff2a6331": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-c/multi-select-copy-r2-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 17021,
        "output_tokens": 24,
        "status": "known"
      },
      "a79a227e5dfa44088a7f85b1e9325ae6": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-c/multi-select-copy-r2-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 19419,
        "output_tokens": 87,
        "status": "known"
      },
      "9927f40725da4afbb62c3960b00bef04": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-c/multi-select-copy-r2-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 21922,
        "output_tokens": 83,
        "status": "known"
      },
      "b5729b6d8ea3439dbaec2848d3faddb4": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-c/multi-select-copy-r2-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 22036,
        "output_tokens": 24,
        "status": "known"
      },
      "084b0615bbfe40029b4acffb3291dc96": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-c/multi-select-copy-r2-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 24449,
        "output_tokens": 194,
        "status": "known"
      },
      "88ccb1ae17984e74affaf2b2aaf7228a": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-c/multi-select-copy-r2-c/trials/multi-select-copy/1",
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
      "e815a0604c414fd4810c1d4f1747503e": {
        "trial": "/private/tmp/tank-m6-multi-select-copy-20260925-live/trials/multi-select-copy-r2-c/multi-select-copy-r2-c/trials/multi-select-copy/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 24735,
        "output_tokens": 69,
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
      "task": "multi-select-copy",
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
      "task": "multi-select-copy",
      "tool_call_limit": 15,
      "timeout_s": 180,
      "gui_only": true
    }
  ]
}
```
