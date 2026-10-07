# Goal-contract DOM fixtures

These 15 local scenarios use schema-version 2 goals, explicit observed navigation effects,
and independent expected results. They replace the runtime dependency on archived v1 goals
in `reports/20261003-s3-dom-multilayout/raw`; that archive is unchanged. Source HTML is the
same current fixture used in `test_dom.py`. The `s3-dom-live-goal-2` freeze records this file's
case-data hash and current code hashes. The refusal follow-up derives from that new freeze.

Tests use real isolated Chromium and fake external HTTP. No paid batch is authorized by
preparing these inputs. Results are a new experiment revision, not a reproduction of S3.
