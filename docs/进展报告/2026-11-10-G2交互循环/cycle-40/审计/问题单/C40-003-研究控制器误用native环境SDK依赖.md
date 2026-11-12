# C40-003 研究控制器误用native环境SDK依赖

状态：限定关闭；优先级P3；仅研究启动。

首脚本在native环境import OpenAI，缺少依赖启动失败，ae026591留原源及[log](../工作目录/001-工具调用调查/controlled-http-first.log)。0HTTP/0模型。改为core SDK控制器与native Jinja/provider子进程，不混装环境后已实际进入HTTP首工具选择；但完整控制受独立C40-002阻断，待新tag完整通过后限定关闭。需要保留进程退出/清理及两环境身份。

## 新tag复测

content-fixed阶段真实core SDK→native Jinja/HTTP受控往返通过，default1/opt-in5共6脚本completion、5个推理前拒绝；此前阶段2次另计，全程0真实native/GPU。53新纯控制＋旧相关共93 passed。原生stop与适配tool_calls分开；混合原稿/length均500且raw保留，缺少普通文本/禁用/stream/schema均400且request_rejected明确无推理。两个子进程退出0、模型/server关闭；[default](../工作目录/002-受控HTTP交接/content-fixed/default/evaluation.json) / [opt-in](../工作目录/002-受控HTTP交接/content-fixed/opt-in/evaluation.json)。这是工程门槛，不是原生质量或真实业务读取批准。
