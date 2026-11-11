# 独立SDK与语音文件修复报告

日期：2026-11-12。作者：spinner-bot。分支fix/sdk-tts-privacy-cycle21；归档时尚未合入运行固定CPU模型研究的主树。当前合并状态以主进展记录为准，本报告保留阶段快照，远期Goal继续active。

## 已验证改动

003：默认SDK在assistant事务提交后、TTS选择/执行后、解码后和最终返回前核验原回合revision/取消；不会用更新后的可变任务版本授权旧结果。原生cancellable接口接收原token，默认Edge还接收本轮checkpoint，未提供用户token时也核验来源。
004：Edge合成到同目录随机自有暂存文件，非空及token/来源检查通过才原子替换最终目标；失败清理自身暂存，保留旧输出，也不删除另一调用已经成功发布的结果。最终路径、voice/rate/pitch和synthesize-only接口兼容。

| 受控交错 | 修前默认SDK | 修后SDK/默认Edge |
| --- | --- | --- |
| 正常 | TTS1，result | TTS1，完整文件/result |
| 提交后取消 | TTS1，仍返旧result | TTS0，Cancelled，无新文件 |
| 提交后独立forget | TTS1，rev1仍返旧姓名 | TTS0，Cancelled，无旧result/新文件 |
| 默认Edge保存中forget | SDK不返result但可能先发布文件（6项补充红测） | save已调用1次，token未取消仍因rev1阻止发布 |

前述模型/Communicate.save/TTS-only组件均为受控夹具，文件为静音WAV或哨兵字节。实际执行的是SDK、Edge适配器、SQLite独立连接和文件生命周期；不是原生模型语义、真实Edge网络、语音内容或物理播放验收。

| 文件边界 | 修前受控结果 | 修后受控结果 |
| --- | --- | --- |
| 正常/旧或新目标 | 最终可成功，但写中可见partial | 完整结果才可见，参数/最终路径保留 |
| 异常/取消/超时 | 覆盖旧文件或留下新partial | 旧字节保持，新目标不出现，暂存清理 |
| save空返回 | 返回旧文件或不存在的路径且标成功 | 明确失败，保旧/无新文件 |
| 并发后取消 | 新增所有权验证 | 不损害另一调用已成功结果，不留暂存 |

## 原始失败与验证版本

| 阶段 | 实际结果 | 源码/测试绑定 |
| --- | --- | --- |
| SDK首次反控 | 14失败/2通过，1.24s | 原字节后来入230c32b |
| SDK首修 | 97相关1.84s；完整1352/1，87.39s | dadcdc2 |
| 文件矩阵红测 | 12失败/2通过，0.28s | 原字节后来入d334757 |
| 原子文件首修/并发 | 87相关1.95s；33相关1.75s；完整1367/1，86.41s | b79ce57实现；全量f71ed28 |
| 合成中来源失效补充 | 6失败，0.90s；修后94相关2.13s | 原字节后来入7389fa9；修复c2cb128 |
| 最终完整Python | 1373通过/1跳过，87.04s | 源/测试/入口c2cb128 |
| 默认浏览器 | 15通过/11显式跳过，36.8s | dad阶段；Edge后续改动后未重跑，待合并统一检查 |

各次全量是不同实现/测试阶段，不相加成独立样本。红测当时未提交的文件按后续相同字节入Git的阶段ref留证，不冒称该ref就是执行入口；实际当前源/测试与最终日志逐项绑定。中途一次进展误记并发耗时1.17s已53a61f2据原日志更正为1.75s，旧修订保留。

当前核验203个不同路径/SHA源版本、三个完整阶段和三个红测阶段；源版本可由不可变Git对象复核。

## 范围与后续

| 已覆盖 | 实际限制/下一步 |
| --- | --- |
| 原生Edge来源检查与同token | 最后检查后的新竞争/已发送远端请求不具有追溯撤回保证 |
| 自有暂存与原子发布 | 不声明断电持久化、完整语音格式校准或已发布历史导出随SQLite忘记自动擦除 |
| 自定义synthesize-only兼容 | 只有SDK外层检查，其内部导出/网络行为不自动采用原生checkpoint |
| 合法assistant先于取消已提交 | 不强行回滚有效历史；forget继续按既有来源依赖失效 |
| 独立树与固定研究隔离 | 主树254冻结实验保持；收尾后合并/默认浏览器复测/全轮审计另行记录 |

本报告不批准通用语义、真人设备、多日可靠性或任何能力提示候选，也不把分支通过当主树已上线。继续推进受实验支持的操作/回执与记忆、声音闭环。

## 单项与原始资料

[003当前单项](issues/003-SDK提交后取消遗忘仍合成并返回旧回复.md)、[004当前单项](issues/004-TTS失败取消覆盖已有输出.md)、[来源核验](工作目录/003-SDK提交后隐私/实验/修复来源核验.json)。当前单项状态可随合并更新，单项归档快照与下列阶段证据封存。
- [../实验/sdk-tts-commit-before.json](../实验/sdk-tts-commit-before.json)
- [../实验/sdk-tts-commit-before.log](../实验/sdk-tts-commit-before.log)
- [工作目录/003-SDK提交后隐私/单项归档快照.md](工作目录/003-SDK提交后隐私/单项归档快照.md)
- [工作目录/003-SDK提交后隐私/实验/browser-sdk-fixed.log](工作目录/003-SDK提交后隐私/实验/browser-sdk-fixed.log)
- [工作目录/003-SDK提交后隐私/实验/edge-source-publication-before.log](工作目录/003-SDK提交后隐私/实验/edge-source-publication-before.log)
- [工作目录/003-SDK提交后隐私/实验/edge-source-publication-fixed.log](工作目录/003-SDK提交后隐私/实验/edge-source-publication-fixed.log)
- [工作目录/003-SDK提交后隐私/实验/full-source-binding.json](工作目录/003-SDK提交后隐私/实验/full-source-binding.json)
- [工作目录/003-SDK提交后隐私/实验/native-edge-source-after.json](工作目录/003-SDK提交后隐私/实验/native-edge-source-after.json)
- [工作目录/003-SDK提交后隐私/实验/native-edge-source-after.log](工作目录/003-SDK提交后隐私/实验/native-edge-source-after.log)
- [工作目录/003-SDK提交后隐私/实验/native-publication-full-source-binding.json](工作目录/003-SDK提交后隐私/实验/native-publication-full-source-binding.json)
- [工作目录/003-SDK提交后隐私/实验/python-full-native-publication-final.log](工作目录/003-SDK提交后隐私/实验/python-full-native-publication-final.log)
- [工作目录/003-SDK提交后隐私/实验/python-full-sdk-fixed.log](工作目录/003-SDK提交后隐私/实验/python-full-sdk-fixed.log)
- [工作目录/003-SDK提交后隐私/实验/report-browser.json](工作目录/003-SDK提交后隐私/实验/report-browser.json)
- [工作目录/003-SDK提交后隐私/实验/report-build-first.log](工作目录/003-SDK提交后隐私/实验/report-build-first.log)
- [工作目录/003-SDK提交后隐私/实验/sdk-after.json](工作目录/003-SDK提交后隐私/实验/sdk-after.json)
- [工作目录/003-SDK提交后隐私/实验/sdk-after.log](工作目录/003-SDK提交后隐私/实验/sdk-after.log)
- [工作目录/003-SDK提交后隐私/实验/sdk-before.log](工作目录/003-SDK提交后隐私/实验/sdk-before.log)
- [工作目录/003-SDK提交后隐私/实验/sdk-fixed-first.log](工作目录/003-SDK提交后隐私/实验/sdk-fixed-first.log)
- [工作目录/003-SDK提交后隐私/实验/修复来源核验.json](工作目录/003-SDK提交后隐私/实验/修复来源核验.json)
- [工作目录/003-SDK提交后隐私/计划.md](工作目录/003-SDK提交后隐私/计划.md)
- [工作目录/003-SDK提交后隐私/进展.md](工作目录/003-SDK提交后隐私/进展.md)
- [工作目录/004-TTS文件原子发布/单项归档快照.md](工作目录/004-TTS文件原子发布/单项归档快照.md)
- [工作目录/004-TTS文件原子发布/实验/full-source-binding.json](工作目录/004-TTS文件原子发布/实验/full-source-binding.json)
- [工作目录/004-TTS文件原子发布/实验/publication-after.json](工作目录/004-TTS文件原子发布/实验/publication-after.json)
- [工作目录/004-TTS文件原子发布/实验/publication-after.log](工作目录/004-TTS文件原子发布/实验/publication-after.log)
- [工作目录/004-TTS文件原子发布/实验/publication-before.json](工作目录/004-TTS文件原子发布/实验/publication-before.json)
- [工作目录/004-TTS文件原子发布/实验/publication-before.log](工作目录/004-TTS文件原子发布/实验/publication-before.log)
- [工作目录/004-TTS文件原子发布/实验/publication-concurrency.log](工作目录/004-TTS文件原子发布/实验/publication-concurrency.log)
- [工作目录/004-TTS文件原子发布/实验/publication-fixed-first.log](工作目录/004-TTS文件原子发布/实验/publication-fixed-first.log)
- [工作目录/004-TTS文件原子发布/实验/publication-red.log](工作目录/004-TTS文件原子发布/实验/publication-red.log)
- [工作目录/004-TTS文件原子发布/实验/python-full-tts-final.log](工作目录/004-TTS文件原子发布/实验/python-full-tts-final.log)
- [工作目录/004-TTS文件原子发布/计划.md](工作目录/004-TTS文件原子发布/计划.md)
- [工作目录/004-TTS文件原子发布/进展.md](工作目录/004-TTS文件原子发布/进展.md)
