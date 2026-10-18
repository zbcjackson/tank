# S5 owned 单击：v2 fake 实机验收

> 状态：2026-10-16 同签名fake实机通过；完整验证6043/E2E18及lint/type/docs通过，第1轮独立评审通过，无可操作问题或源码修复；12项针对性离线回归复核通过，结论补记由评审者自检。0外部请求/模型费用，真实GUI设置、单击和清理已发生。

签名 `47d5e4f540a1858375b555f186bbd73e239d43b9efefdcd2024cc9bdd32efc4b`，对应[真实执行预览](../20261016-s5-owned-seven-v2-live/README.md)。

复用 owned Calculator 及输入清理；真实 SDK 走本地 MockTransport，只有模型HTTP为fake。
fake响应使用本地AX按钮7中心生成，不能作为视觉准确率或模型稳定性证据。
新建应用、移动到可见位置并清零后，护栏绑定新截图；单击点(274,371)，AX独立读回
`result=7`。passed=true、verdict=fake_wiring_only、1本地HTTP、0外部HTTP；
input_cleanup.confirmed、application_cleanup.confirmed、position_restored、frontmost_restored
均为true。lease内先清理输入再关闭应用，不触碰已有Calculator会话。

账本为合成9tokens/2475nano，reserved=0；这不是实际费用，不计入历史真实费用总额。
[result.json](result.json) SHA256：
`d62e263e45abe00886835471bec856a36559f995bb26700a5526216e10c4ab17`。
截图、AX标注、请求摘要、SDK chunks、账本与原始结果仅本地归档，不提交截图/原始载荷。

首份fake后的截止时间缺口已先红后绿修复：总任务deadline直接取消尚在等待的模型调用，
即使单请求180s尚未耗尽，也不得继续等到其超时；未知用量仍保留预留，取消后join清理。
新目录重新freeze并完成本次实机验收，原始历史目录不覆盖。

12项新增离线回归通过，包含真实SDK fake HTTP到护栏/读回/清理，以及拒绝/未知/
取消/截止时间/隔离/结果落盘。完整验证与评审结论同步记录到[主计划](../../../../../docs/plans/done/computer-use-strategy-ladder.md)。
