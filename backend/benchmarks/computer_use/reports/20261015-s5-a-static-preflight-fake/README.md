# S5 A 单目标静态定位：离线验收

> 状态：2026-10-15 fake接线3/3完成，0外部模型请求/0新GUI操作；不作质量或采用结论。

签名`59f44c3b28bd327a0d11c372b6c7a402178bd91a0b0c42a5aacee7f7fc8cad4c`，
与[真实执行预览](../20261015-s5-a-static-preflight-live/README.md)相同。
使用既存原图副本；官方SDK+TaskModelCallRunner+BenchmarkModelPolicy+SpendLedger，
fake仅使用MockTransport/trust_env=false和offline-probe凭据，未访问桌面或真实provider。

3行finished、3次fake HTTP、所有最终usage已知；usage-only/no-think/output-cap的
共同提示与图SHA保持。预设假回复点为(165,387)，映射(316,417)，距人工中心1px，
仅验证正常评分/尾部usage链路，不是模型识别或真实点击证据。
账本known7425nano-USD为合成计量，不是费用；reserved0、stop_reason=null。

本地[freeze.json](freeze.json)、[result.json](result.json)、[spend.jsonl](spend.jsonl)、
SDK请求与chunks及[验证日志](validation/)保留，不提交原始载荷。
重复目录不能重跑；后续源码改变则必须另冻结目录，不能补改本批结果。

新增执行器第1轮独立评审通过，无actionable/unresolved finding，未修改源码；
重跑69项定向测试、docs51/diff通过。完整后端5944/1skip/21warnings及E2E18/71已核对，
旧词表缓存和沙箱端口失败及修复环境后的全绿日志保留在validation目录。
