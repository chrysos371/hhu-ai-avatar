# C40-003 研究控制器误用native环境SDK依赖

状态：开放；优先级P3；仅研究启动。

首脚本在native环境import OpenAI，缺少依赖启动失败，ae026591留原源及[log](../工作目录/001-工具调用调查/controlled-http-first.log)。0HTTP/0模型。改为core SDK控制器与native Jinja/provider子进程，不混装环境后已实际进入HTTP首工具选择；但完整控制受独立C40-002阻断，待新tag完整通过后限定关闭。需要保留进程退出/清理及两环境身份。
