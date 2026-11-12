# C40-002 SDK工具回合缺失content导致模板中断

状态：限定关闭；优先级P2；仅显式opt-in研究provider。

## 原始反例

实际core SDK＋native Jinja/HTTP、脚本模型，无真实推理或GPU。默认400拒绝/普通正控成功；opt-in首调用解析为真实SDK tool_calls成功。LLMEngine.chat_tools的exclude_none=True会省略assistant content，而GGUF模板assistant分支直接读取message.content，followup在推理前UndefinedError/断连接，未进入旧trace finally。另研究worker收尾误索引不存在的第二条prompt，退出1。

[原worker log](../工作目录/002-受控HTTP交接/opt-in/worker.log)、[唯一首选择trace](../工作目录/002-受控HTTP交接/opt-in/provider-trace.jsonl)、[源字节与分母](../工作目录/002-受控HTTP交接/template-followup-red-source.json)。合计2次脚本completion（default1/opt1），0真实native。不能把85纯适配控制当完整HTTP roundtrip通过。

## 优化目标

只在合法assistant工具历史中把缺失/null content转为模板所需空串，保留原始wire消息；其它缺少合法文本的消息受控400。准备/模板错误也明确响应与记录，不断连接。新tag跑同材料，核SDK roundtrip、default兼容、非法输出/截断拒绝、源码和子进程清理；不涉及业务执行或默认产品。

## 新tag复测

content-fixed阶段真实core SDK→native Jinja/HTTP受控往返通过，default1/opt-in5共6脚本completion、5个推理前拒绝；此前阶段2次另计，全程0真实native/GPU。53新纯控制＋旧相关共93 passed。原生stop与适配tool_calls分开；混合原稿/length均500且raw保留，缺少普通文本/禁用/stream/schema均400且request_rejected明确无推理。两个子进程退出0、模型/server关闭；[default](../工作目录/002-受控HTTP交接/content-fixed/default/evaluation.json) / [opt-in](../工作目录/002-受控HTTP交接/content-fixed/opt-in/evaluation.json)。这是工程门槛，不是原生质量或真实业务读取批准。
