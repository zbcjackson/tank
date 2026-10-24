> 日期：2026-10-24；结论：resolved（原始DOM闭环资格的宿主缺口已复现；缺口未修复，真实模型实测0/6）。

# 原始DOM业务核验阻塞了六任务实测准入

## 结论与范围

真实AgentRunner、显式jev-action-vision、原版sqlite-web 0.8.1与普通DOM通道，
尚不能为本片「保存指定记录标题并核验」提供足够的业务完成证据。正确执行参考动作后，
数据库已改对，宿主仍保留effect_unknown；不能靠换模型解决这个已知观察/核验缺口。
没有启动六项真实模型实测，也没有读取真实模型密钥或调用真实模型API。

这是定向宿主契约诊断，不是Jev/Gemini准确率比较，也不证明其他页面不能闭环。
此前benchmark的完整记录补强没有进入生产；其36/24次实测与本片证据各自保持。
六项仅保留意图清单，视觉需求尚未完成原产品资格；未冻结真实调用输入/接收方/预算，
全部6项未运行，不计模型失败。中性名称拒绝泛化仍未验证。

## 实际证据

产品只打开自建fixture.db，种子为两条合成记录Nora/Keep A、Tavi/Keep B；
无个人浏览器、账户或数据库。原产品模板/JS/CSS未修改，通道、Controller与工厂未替换。
参考UI操作仅在测量外执行：勾选chk_title、填Miro、点Update。

`raw-probe/database-after.json`和写入见证确认目标1标题Nora→Miro，只有一次update，
notes、记录2与schema保持。实际HTML与PNG有成功提示和Miro行。
`raw-probe/list-snapshot.json`为完整观察，Miro在控件的row祖先上下文中；事实列表没有
对应业务值，Controller允许的status:*事实仅status:Page URL。
这不是图片看不见、记录没保存或模型选错；原始观察未提供可用于此任务完成的事实。

三个独立Runner诊断各使用新数据库，外部HTTP由项目现有双SDK适配器替换；
只按公开候选选固定参考答案，不修改选择器/执行器/读取返回。按最终证据逐项得到：

- `runner/textbox/report.json`：声明已有textbox:title事实作完成条件，得到
  needs_input/unsupported_completion_evidence；0派发、0 SDK、0写入。
- `runner/business-status/report.json`：声明业务条件status:Saved title=Miro，
  该键为诊断用业务条件，普通通道并不产出。按完整候选执行启用title、填Miro、Update，
  3次sent、3次假SDK；事后DB确认正确保存且只有一次update，宿主仍为
  unknown/effect_unknown、pending_effect=true。保持原unknown，不向宿主注入DB结论。
- `runner/url-only/report.json`：刻意将声明条件弱化为返回列表URL，固定答案只选Content，
  1派发、1次假SDK、0写入，宿主completed/goal_verified。宿主正确证明了声明的URL条件，
  这不能被当作自然语言改标题目标已完成，也不是正常完整业务契约下的误报证据。

三项独立诊断全部清理确认，产品服务退出，最终4次假SDK的capture/started/finished/
response完整相符，返回用量已知；最终诊断非回环connect拒绝计数为空。
没有视觉SDK调用，不能由此评价视觉接管效果。

## 根因与修复入口

现行[DOM通道](../../backend/plugins/agent-computer-use/src/agent_computer_use/channels/dom.py)
将唯一命名控件值和部分状态转为事实，行文本主要保留在控件祖先上下文中。
[Controller](../../backend/plugins/agent-computer-use/src/agent_computer_use/controller.py)
在普通浏览器路径仅接受status:开头的completion，完成/效果判定按事实键值匹配。
[候选构造器](../../backend/plugins/agent-computer-use/src/agent_computer_use/action_builder.py)
对submit直接使用goal.completion作为效果条件。因此，本产品可见行、可声明的业务条件
与保存后的效果证据没有接通；扩大允许的字符串前缀本身不能证明持久化。

下一修复片应让GoalContract能声明公开DOM可核验的唯一目标/字段结果，并由原始DOM
提供有范围、完整性和新鲜度约束的保存后读回；将其接入原效果、进展及完成核验。
至少保留「只填未保存」「只回列表」「改错行」「同名/缺失」「未改字段/其他记录」反例。
不把编辑框当前值或URL到达升级为保存成功，不将数据库评分oracle搬入模型状态。
该能力通过最小真产品/假HTTP验收后，重新资格并冻结六任务真实调用。

## 准备失败与验证边界

早期脚本遗漏字段启用、错用复选框name、访问不存在的runtime.closed、遗漏default
profile，以及没有完整选择fill候选的尝试均保留，不能作为宿主/模型能力结果。
初次HTTP替换遗漏SDK使用的httpx2适配器，两次SDK尝试连接保留域名offline.invalid后失败；
没有真实服务地址或密钥，不能把整轮准备写成「零网络尝试」。修正后复用现有适配器，
最终4次假SDK正常；另一次早期不完整参考流程有4次假SDK，未纳入最终诊断计数。

`verify.py`不导入执行配方，独立核对SQL/HTML/DOM、实际Runner结果、动作/模型调用及
清理，五组断言通过。`probe-red.log`保留缺少业务完成事实的预期失败复现。
本片未修改生产或测试源码；仓库仅docs，按docs-only规则检查文档及差异，不将上一片
6769项回归或任何旧实测冒充本片新增验证。原74工件和默认配置SHA均保持。
第1轮review-and-refactor独立审查无可操作或遗留发现，无修复即结束。审查者另行核对
268成员、75源码、654产品环境文件、原始SQLite与Runner证据；独立副本五组断言、
115文档及完整diff检查通过，3个端口明确ECONNREFUSED。原始审查全文及SHA在manifest，
协调者对该绑定与计划迁移做闭合自检，不另称独立审查。宿主缺口与0/6限制保持。

## 封存

[证据包](artifacts/jev-runtime-acceptance-20261024.tar.xz)共268个成员，SHA256
`45dbce246348a05a5a52a6fcaac8541b45ff5326f50c332593a2221ec3f13666`；
[逐成员清单](artifacts/jev-runtime-acceptance-20261024-manifest.json)包含数据库、原始快照/
HTML/PNG、Runner/capture/事件/审计、当前及失败脚本、75份运行来源快照、产品环境
清单、独立验证与六项未运行意图。该封存摘要用于已完成诊断的完整性，不是实测准入摘要。
