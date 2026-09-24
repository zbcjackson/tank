# computer_use benchmark

- Run label: `m6-pair-3-d`
- Scoring: trial-token-gui-grounding-v5 (historical reports use a different scoring revision)
- Smoke (excluded from strict score): 0/0
- Overall: **1/1** (100%, 95% CI 21%–100%)

| task | pass | rate | 95% CI | tool calls (med) | actions (med) | turns (med) | call limit | wall s (med) | tokens (med) | shots (med) |
|---|---|---|---|---|---|---|---|---|---|---|
| calc-open | 1/1 | 100% | 21%–100% | 10 | 5 | 15 | 15 | 53 | 119307 | 5 |

## LLM latency (per call)

| task | calls (med) | stream ttft s (med) | call s (med) | total s | nonstream RTT s |
|---|---|---|---|---|---|
| calc-open | 15 | 1.5 | 2.9 | 43 | 0.0 |

- API calls total: 15, mean 2.9s/call, median streamed ttft 1.5, LLM time total 43s

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
    "variant": "D",
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
      "charged_tokens": 119307,
      "charged_nano_usd": 0,
      "known_tokens": 119307,
      "known_nano_usd": 0,
      "reserved_tokens": 0,
      "reserved_nano_usd": 0,
      "limit_requests": 31,
      "admitted_requests": 15
    },
    "trials": {
      "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-d/m6-pair-3-d/trials/calc-open/1": {
        "limit_tokens": 300000,
        "limit_nano_usd": 8000000000,
        "charged_tokens": 119307,
        "charged_nano_usd": 0,
        "known_tokens": 119307,
        "known_nano_usd": 0,
        "reserved_tokens": 0,
        "reserved_nano_usd": 0
      }
    },
    "stop_reason": null,
    "requests": {
      "dc36b248e413464bafdf01ce2443cb54": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-d/m6-pair-3-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 3828,
        "output_tokens": 95,
        "status": "known"
      },
      "afe57dc6cf6941798b62127d79dca73f": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-d/m6-pair-3-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6332,
        "output_tokens": 173,
        "status": "known"
      },
      "bfd9a1eb525d425d8b5589be19e9415f": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-d/m6-pair-3-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2558,
        "output_tokens": 81,
        "status": "known"
      },
      "713faa2fc66247ba9693d523454aa542": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-d/m6-pair-3-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6589,
        "output_tokens": 122,
        "status": "known"
      },
      "6d556b40831642558d41dd5f7232400d": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-d/m6-pair-3-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 6036,
        "output_tokens": 86,
        "status": "known"
      },
      "8ba0d483749c417f93bf64ebd1824abe": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-d/m6-pair-3-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8545,
        "output_tokens": 115,
        "status": "known"
      },
      "6207f882369f407b93be9aa4eb87e4e4": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-d/m6-pair-3-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2561,
        "output_tokens": 81,
        "status": "known"
      },
      "04237a1d294a4b4ba323da165320d987": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-d/m6-pair-3-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 8750,
        "output_tokens": 69,
        "status": "known"
      },
      "d4eab444b2ce41b68ef217f21bf7c923": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-d/m6-pair-3-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11256,
        "output_tokens": 116,
        "status": "known"
      },
      "926a2d28dd1f4dc0a87cb22191ea129c": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-d/m6-pair-3-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2558,
        "output_tokens": 81,
        "status": "known"
      },
      "01a88f56b5034808a97556f85cb85c61": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-d/m6-pair-3-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 11466,
        "output_tokens": 76,
        "status": "known"
      },
      "47861b5d81054427a070c4fae956f891": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-d/m6-pair-3-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 13976,
        "output_tokens": 122,
        "status": "known"
      },
      "92be7e51af50432a82cc4c50bfcda292": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-d/m6-pair-3-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 2561,
        "output_tokens": 81,
        "status": "known"
      },
      "e9cf10cfcbda4d85abd23fe36a444f2f": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-d/m6-pair-3-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 14188,
        "output_tokens": 65,
        "status": "known"
      },
      "0790cf1683da478bbf978640f1254140": {
        "trial": "/private/tmp/tank-m6-calc-20260924-live/trials/m6-pair-3-d/m6-pair-3-d/trials/calc-open/1",
        "allowance": {
          "input_tokens": 0,
          "output_tokens": 0,
          "input_nano_usd": 0,
          "output_nano_usd": 0
        },
        "input_tokens": 16678,
        "output_tokens": 62,
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
    "planner": 11,
    "locator": 4,
    "total": 15,
    "blocked": false
  },
  "request_limits": {
    "planner": 16,
    "locator": 15,
    "total": 31
  },
  "grounding": {
    "profile": "locator",
    "fallback_profile": null,
    "protocol": "bbox",
    "nullable_style": "integer",
    "strict": false,
    "detail": "auto",
    "status_field": false,
    "mode": "split",
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
          "sha256": "0832faf6ced4040b4429791c23a1c4a23536309b14cb19c7cb03211fb389a049",
          "file": "screenshots/shot_005.png",
          "captured_at": 1790261321.182125,
          "http_serialized_at": 1790261321.195841
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
