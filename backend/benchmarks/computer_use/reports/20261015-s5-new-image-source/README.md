# S5 新位置Calculator图片来源

> 状态：2026-10-15 一次实际owned-app采集完成，AX/图像目视复核与清理确认，0外部模型请求。

为新独立定位配方采集，不根据模型回复挑图。位置在采集前固定为(1100,300)，
目标仍为Calculator按钮7，主屏原点(0,0)，点空间1920×1080/背板3840×2160。
复用s5_paired.OwnedApplication及原AX/Quartz曝光、截图管线：拒绝已有Calculator，
验证新进程/唯一窗口、基本模式和目标曝光；截图前后目标AX框及前台保持一致。
原捕获管线按点分辨率保存PNG，include_cursor=false，无新图像编辑。

[frame.png](frame.png) SHA256
`95713a7b61fd046c2bf330044daa5aa840484796311c7b6b78b63a737748820e`，1920×1080。
同期AX按钮7框[1110,487,48,48]，中心(1134,511)，预设判读半径20px；
[visual-qa.json](visual-qa.json)记录assistant对固定图的目视复核，非真人验收或模型定位结果。
[标注case](../../fixtures/s5-static/calculator-right.json)仅图片SHA及评分annotation，
不得进入模型请求。图片中Calculator居右，背景包含其他可见应用中的会话/侧栏内容。
本阶段图片只存本地，没有发送provider；后续执行预览明确整图范围。

本地采集有真实setup动作：move_owned_window、clear_owned_calculator；抓取1张，
没有模型驱动任务输入、算式执行或付费请求。此阶段不能称为0 GUI；静态fake/live
模型诊断自身则不创建应用/抓图/输入。owned进程已终止，position_restored与
frontmost_restored和confirmed均true，见[capture.json](capture.json)。

[capture.py](capture.py)及[capture-2.log](capture-2.log)本地保留；只在采集时将既有
setup_position替换为预先检查的固定位置，无评分/预算/模型猴补丁。
初次脚本入口在import前失败（benchmarks不在path），0应用/截图；改为backend的
runpy入口后完成唯一一次实际采集。原[capture.log](capture.log)失败日志保留。

这张图不是既存旧图或其裁剪副本，尚未用于模型调用；但场景仍仅单个Calculator，
不是泛化holdout或完整真实GUI任务验收。不据截图/AX位置声称模型会正确定位。
原始图片/AX细节/脚本不提交，只跟踪此README及非敏感图片SHA/标注JSON。
