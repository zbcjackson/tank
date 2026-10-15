# S5 跨图候选门：图片来源

> 状态：2026-10-15 两个预选位置各一次实际owned Calculator采集/AX与目视核对完成，清理全确认，0模型请求。

在任何模型结果前固定两位置(180,160)/(1400,600)，同一主屏1920×1080，
目标均为Calculator按钮7。拒绝已有用户Calculator，验证新进程/唯一窗口/基本模式、
目标曝光与截图前后AX框/前台不变，复用既有点分辨率截图管线，include_cursor=false。

- [图1](image-1/frame.png)：SHA `7b9c5d15c7af0d1c78cc29d8fa83a47dbc3c6e385b34047da05bd61e221590f1`；
  AX框[190,347,48,48]，中心(214,371)，半径20px。
- [图2](image-2/frame.png)：SHA `cb4dc27c36a3bc719775a4e30a554875576741de1c09cd211e3243acf063ae8a`；
  AX框[1410,787,48,48]，中心(1434,811)，半径20px。

assistant用view_image查看两张原图，按钮位置与AX一致，非真人验收。
case副本为[图1标注](../../fixtures/s5-static/cross-image-1.json)及
[图2标注](../../fixtures/s5-static/cross-image-2.json)，模型不得接收标注。
完整图包含背景应用会话正文/侧栏，准备阶段只本地保存，尚未外发。
两图背景近似，仅窗口位置变化，不是跨应用/广泛布局holdout。

每实例都有真实setup动作move_owned_window/clear_owned_calculator，因此采集不是0 GUI；
0模型驱动输入/算式执行/模型请求。PID69352/69363均终止，位置/前台恢复confirmed。
[capture.json](capture.json)、[capture.py](capture.py)、[日志](capture.log)及各图visual-qa.json
本地保留，原始PNG/AX/脚本不提交。两张均为预选位置新采集，不按模型结果换图或加工旧图。
