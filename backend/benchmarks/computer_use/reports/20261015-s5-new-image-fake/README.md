# S5 新图片案例：离线接线验收

> 状态：2026-10-15 revision 3 fake3/3完成，0外部模型/新GUI；完整验证5991/E2E18通过，新数据接线第1轮独立评审通过（无问题、无修改，立即结束）。

[新图片与标注来源](../20261015-s5-new-image-source/README.md)已固定，
[真实执行预览](../20261015-s5-new-image-live/README.md)使用同一图片、case和源码。
签名`905c58ce3e652984708ef4af13224e385853417b17362f84b35e087e0e1c67b4`。

新增prepare --case阶段，case内容进入冻结，图片SHA不匹配/标注缺失或漂移在client前拒绝。
数据字段只有image_sha256和annotation(center/radius/provenance)，仍为1920×1080/目标7，
不加入model/endpoint/生成参数等可变入口。SDK只接收原图、共同提示与目标文本，
标注仅本地评分；真实SDK/fake HTTP回归用新中心和TRUTH_PRIVATE标记证明无truth泄漏，
不靠猴补丁全局FRAME_SHA/ANNOTATION来切换真实数据案例。

本地[result.json](result.json)、[freeze.json](freeze.json)、[case.json](case.json)、
[spend.jsonl](spend.jsonl)、[execution.log](execution.log)保留：3行finished、3次fake HTTP，
0外部模型请求/0新GUI，最终usage已知，合成known7425nano-USD/reserved0、stop_reason=null。
fake回复仍为固定旧测试点(165,387)，映射(316,417)，距新中心823.383px，
3项within_annotation=false；这是预期的错误点接线检查，不能描述为模型定位0/3。
另有SDK回归返回新图正确点(643,731)，新标注下三项都命中，原标注不会命中。
两者只证明数据绑定和评分生效，fake接线完成不代表实际模型定位质量。

17项新增回归先红（缺prepare case入口），实现后相关219项通过；包含case字段/类型/
边界/缺失/漂移及SDK图SHA/新标注评分/无truth泄漏，原格式/单位/超时/未知用量回归保持。
backend/CLIruff、修改文件pyright0、web lint/tsc-b、E2E18场景/71steps通过，
runtime error检查为空。完整后端5991 passed/1 skipped/21 warnings（422.27秒）、docs51/diff通过；
协议未改，sync不适用，本数据接线第1轮独立评审通过（无actionable/unresolved finding，未改代码，立即结束），
日志见[validation](validation/)。上一解析器scope三轮已结束，本片不重开其评审。

没有新真实调用，也没有改旧批result/费用/未知预留。case支持改变源码后旧revision2
配方不能续跑；此图案例只做独立三请求配置诊断，不能替换原生产A或S5统计分母。
