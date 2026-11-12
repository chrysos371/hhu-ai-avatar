# C36-001 Playwright收集阶段JSON模块导入失败

P3测试兼容，修正后通过并关闭。

首targeted调用未收集到用例：Node22 ESM要求JSON import attribute，虽然tsc/Vite已通过，Playwright直接加载e2e模块时抛TypeError。见[原log](../工作目录/001-日常浏览器回归/first-browser_targeted-final.log)、[426源码绑定](../工作目录/001-日常浏览器回归/first-browser_targeted-final-binding.json)。在测试执行前失败，没有实际Avatar回合或质量结果，不能当两个通过/失败的产品案例。

目标使用Node fs/URL显式读取已提交JSON协议，继续由回归绑定协议SHA，避免不同模块加载器契约差异。保留原空收集失败，再新标签执行。

修后[witness-fixed绑定](../工作目录/001-日常浏览器回归/witness-fixed-browser_targeted-final-binding.json)严格运行身份/426源码稳定/两页实际2 passed（6.6秒）通过。原空收集失败、原整体身份缺字段失败及独立侧证均保留；新执行不覆盖旧记录。
