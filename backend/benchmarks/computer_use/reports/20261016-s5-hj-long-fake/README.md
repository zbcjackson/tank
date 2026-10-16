# S5 独立 H/J 长任务：fake 实机验收

> 状态：2026-10-16 配方已冻结，40项fake实机全部通过；完整6053/E2E18及lint/type/docs通过，第1轮独立评审无可操作问题、无源码修复即结束，10项针对性回归复核通过（评审状态补记由评审者自检）。0外部模型请求/费用，真实GUI任务及清理已执行。

签名 `c8a4ae42d113035c6b42c5c7b9256e12cffdb0ca5c9684c5bbd922a68ca05e5b`，与[真实预览](../20261016-s5-hj-long-live/README.md)一致。
真实owned Calculator、AX/Quartz派发、独立AX读回和清理；只替换Jev/Qwen HTTP。
fake响应按冻结目标和候选脚本生成，因此只验证接线、资源及计量，不产生模型质量、
费用/耗时优势或L1–L3结论。原始过程和结果保存在本目录，不提交原始载荷。


## 实机结果

40/40 finished且passed，H/J各20/20 strict，0规则违规，所有输入及owned应用清理确认。
H为200次本地文本HTTP；J为140次本地Jev+80次文本HTTP，共420次，与单共享账本准入
一致。420份模型调用记录中image_url/assets字段为0，无截图上传；未创建A驱动或A行。

完整20对，两个通道各10对，时间/费用long_family按repeat形成10个block；仅有J-H比较。
L1/L2/L3/h4均为null，conclusion=fake_wiring_only_no_adoption_conclusion。
fake合成6440tokens/1548960nano，reserved=0，不是实际模型费用，不加入历史真实账目。

[result.json](result.json) SHA256：
`4538afa9becaa54f88e72de2c7df09414e75ab6a64e867bae3ee95312622be51`。
冻结、结果、rows/audit/spend和模型记录在本目录本地保留；仅提交本说明，不提交原始载荷。
10项新增回归及原有相关回归共157项通过，包括跨track拒绝、无A驱动、独立门槛边界、
环境停批保留40行、关闭账本失败降为incomplete并保留结果；旧三臂行为回归通过。
本片共享源码扩展令旧签名不再匹配当前源文件，历史目录/原始结果保留，不改旧freeze补跑。
