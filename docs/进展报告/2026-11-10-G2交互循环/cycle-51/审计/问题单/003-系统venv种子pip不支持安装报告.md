# 003 系统venv种子pip不支持安装报告

状态：限定关闭。首失败保留，实际v4及独立当前准入通过；无模型/训练。

首次实际venv创建成功，但种子pip22.0.2不支持--report，Torch安装在参数解析阶段返回2，未下载安装Torch。首源、environment-v1.json和原日志保留于003工作目录。

修后v2在独立目录留新日志，严格确认目标仅有pip/setuptools且属于已失败v1，再从官方PyPI取固定pip25.3 wheel、核API给出的SHA，离线安装该wheel后再使用--report。不重建或删除失败环境，不改变普通/原生两个环境。待实际v2完整安装、pip check与CPU导入成功后限定关闭。

实际闭合来源是v4，并非把失败v2/v3改成成功：pip25.3受SHA约束bootstrap后已在实际local安装和其余依赖安装生成报告，pip check/独立CPU导入及原环境未改通过；独立完整环境分词同字节通过。v3因相同完整payload已可用而显式退役，failed/原日志保持。见003/environment-admission.json与005/training-tokenizer-crosscheck-v1.json。
