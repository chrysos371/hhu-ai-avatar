# C56-002 worker直接重入覆盖已有终态

P1，OPEN，真实CPU新增复现。普通launch目录独占能拒绝重复，但手工再次调用--worker和同配置SHA会先重写status；随后experiment.log以xb打开失败，旧completed/return_code0变成failed/return_codenull，CLI还退出0。原payload实际只执行一次，不能误称重复执行；问题是不可变终态回执被破坏。原成功状态已在红测日志完整保留。

目标：监督器入口独占claim，第二次在任何status/log/config写入前非零拒绝；完整原文件字节保持，成功/失败/中断终态均不被重入改写。独占锁与实际退出结果分开，保留缺失/损坏描述符拒绝及正常生命周期控制。
