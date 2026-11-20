# R01-005 定向pytest退出码缺少独立采集

P3过程采证，开放转统一采集。部分本轮定向命令以tail结尾，外层状态是tail的返回码；手工JSON actual_returncode按pytest摘要/常规返回约定填写，没有单独绑定子进程退出证据。日志断言、数量和SHA真实，不将此说成测试没有执行或全量/实模返回码无效。

原字段/原件不回写，逐文件SHA见退出码来源勘误。全量Python与native jobs实际捕获状态不受影响。新增统一runner先核Git历史/当前全部执行输入（含自身），直接subprocess.run采集pytest实际状态，区分预期红测与控制器状态，结束核输入保持并保留原log。material-late-epoch-v2已实际退出1、4失败和855源稳定；修复后须新标签实际退出0，再限定关闭采集流程。
