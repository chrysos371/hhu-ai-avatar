# 003 系统venv种子pip不支持安装报告

状态：开放，环境准备工具失败；无模型/训练。

首次实际venv创建成功，但种子pip22.0.2不支持--report，Torch安装在参数解析阶段返回2，未下载安装Torch。首源、environment-v1.json和原日志保留于003工作目录。

修后v2在独立目录留新日志，严格确认目标仅有pip/setuptools且属于已失败v1，再从官方PyPI取固定pip25.3 wheel、核API给出的SHA，离线安装该wheel后再使用--report。不重建或删除失败环境，不改变普通/原生两个环境。待实际v2完整安装、pip check与CPU导入成功后限定关闭。
