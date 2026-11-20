# C56-003 多级provider形状的孙进程未受保护

P1，OPEN，真实CPU链复现；实际GPU provider尚未验证。

源码scripts/run_native_output_models.py的provider通过再次Popen启动serve_local_model_eval.py，当前直接worker内核保护不能自动沿fork传递。已登记CPU三层形状实测：manager PR_GET_PDEATHSIG=9、其新会话payload=0；SIGKILL顶层监督器后manager身份退出，payload仍活，原子wait为null。无关自建CPU对照存活，全部自建残留精确清理，0模型/GPU。见004/chain-cpu-v1.json与完整日志；这不是实际GPU泄漏或主机断电测试。

目标：下一轮针对项目明确的manager→provider边安装同样源码/SHA/父身份保护，验证fork后重新安装、exec身份及正常provider生命周期；先CPU同形状红→绿和完整回归，再在必要的实模研究中核实际GPU分配/退役。不要把任意第三方孙进程树或凭据变化纳入未经验证的保证。
