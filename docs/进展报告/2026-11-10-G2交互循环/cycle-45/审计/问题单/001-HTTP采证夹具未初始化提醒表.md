# C45-001 HTTP采证夹具未初始化提醒表

优先级P3｜首次失败已保留，待仅修夹具后新目录重采

预写探测脚本4f81bb74启动真实create_server后直接向新MemoryStore的memory_reminders插行。该表由ReminderStore启动创建，create_server本身不创建它；脚本漏掉初始化，实际sqlite3.OperationalError: no such table: memory_reminders，在第一条业务播种前停止。0实际查询/0模型，不能把本次当HTTP交付失败或通过。

原[首日志](../工作目录/001-真实入口调查/http-probe-first.log)与[失败声明](../工作目录/003-真实HTTP与上下文/first-failure.json)保留，原脚本精确Git4f81bb74。本轮13真实HTTP控制与完整2396/1、19/16并未失败。只修采证夹具：播种前显式ReminderStore初始化，新输出子目录v2，不改生产算法/测试材料/评分。复测须完整采得10 HTTP查询及5SSE、真实SQL重建和后续模型消息，之后才限定关闭。

复测：显式初始化仅改变审计脚本2240bbed，新v2完整10真实HTTP查询/5SSE、单次来源20消息/业务投影一致、配置捕获模型0调用，后续普通Web1分析/1生成，完整原件见[HTTP回执](../工作目录/003-真实HTTP与上下文/v2/http-evidence.json)；001在采证夹具范围关闭，不作为生产算法修复。
