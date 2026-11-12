# 002 迁前已有的提醒测试Lint警告

已修。迁后执行完整Lint发现useReminderDeliveries.test.tsx有3处_options未使用；比较760e774可确认原文件与迁移前完全相同，见[来源证明](../迁前Lint问题来源.json)。这不是目录迁移产生的业务回归。

参数保留是为了让typed mock的calls保留第二参数类型供请求body断言。修复显式消费_options，不更改模拟返回、调用参数或断言，不删除验证。Lint复测通过，提醒8项测试通过；原[首轮Lint](../迁后前端Lint.log)、[修后Lint](../迁后前端Lint修复后.log)、[定向测试](../提醒测试Lint修复回归.log)均保留。
