from collections import Counter
import base64
import json
from pathlib import Path
from report_common import ROOT, OUT, e, link, table, section, cards, code, document

P = 'docs/发布/2.0.0-rc.1/'
W = P+'工作目录/'
A = 'audit/2026-11-21-release-2.0.0/'


def read(name):
    return json.loads((ROOT/name).read_text())


def build():
    build = read(W+'011-语音与综合发布门控/final-build-v8-verified-proof.json')['build_result']
    native = read(W+'006-写作交付与严格格式/native-result-v15.json')
    review = read(W+'006-写作交付与严格格式/native-source-span-review-v15.json')
    soak = read(W+'011-语音与综合发布门控/installed-soak-v6-proof.json')['summary']
    asr = read(W+'011-语音与综合发布门控/public-asr-cpu-v5.json')['summary']
    gate = read(A+'工作目录/002-发布门控/release-gate-v1.json')
    modes = Counter(row['generation_mode'] for row in review['rows'] if row['arm']=='candidate')
    body = section('identity', '版本身份与发行边界', table(['对象','精确身份','解释'],[
        ['包/应用版本','<code>2.0.0</code>','pyproject、运行时、前端包及发行元数据一致；不是2.0.0-rc.1。旧候选目录名作为历史保留。'],
        ['Git注释标签','<code>v2.0.0</code>','指向批准提交 <code>7eaafdc3af93c4acee6f7fe66da4af9401f1d474</code>；标签对象 <code>d7d8f48c285e432c4373a6df643c8e76c8b6c5f6</code>。'],
        ['构建源','<code>'+e(build['source_ref'])+'</code>','bfa956e6固定代码/前端输入；其后的批准/报告提交不伪装为包构建源。'],
        ['交付记录','<code>ef6053bf3776fa980f291c0cc33c962bca5bc2ef</code>','补记录远端refs/本地稳定分发；新三份报告属于追加文档，不移动标签。'],
        ['交付方式','Git版本标签＋服务器wheel/sdist','未上传GitHub Release二进制附件，也未发布PyPI；不能直接假设pip从公共索引取得2.0.0。'],
        ['适用部署','本机单用户、127.0.0.1绑定、token鉴权','不是账号隔离、多租户或公网生产部署批准。'],
    ])+'<div class="callout warn"><b>界面遗留标识：</b>AppShell侧栏仍有“认知管理 · v0.1”字样。这是旧外壳文案，不能用来判定包版本；本次报告如实披露，未修改已批准代码。用<code>hhu-avatar --version</code>和标签/包元数据核验。</div><p class="sources">'+
        link('批准文件',A+'工作目录/002-发布门控/release-gate-v1.json')+' · '+link('分发与推送证明',A+'工作目录/002-发布门控/发布推送与分发证明-v1.json')+' · '+link('侧栏源码','frontend/src/app/AppShell.tsx')+'</p>', '01 / RELEASE IDENTITY')
    body += section('architecture', '架构：将来源、权限和交付纳入一条可审计链',
        '<div class="diagram" role="img" aria-label="功能结构：标准入口、来源与权限、认知与记忆、受验交付、语音形象和持久历史"><div><strong>入口</strong><small>CLI / Web / 显式SDK</small></div><div><strong>来源与权限</strong><small>用户行 · speaker · revision</small></div><div><strong>认知与记忆</strong><small>分析 / PAD / SQLite</small></div><div><strong>受验交付</strong><small>来源约束 / 有界修正</small></div><div><strong>声音与形象</strong><small>TTS / PCM / media clock</small></div><div><strong>历史与退役</strong><small>依赖 / 去重 / 释放</small></div></div>'
        '<p class="meta">上图是职责关系，不表示每个分支都调用模型或严格经过同一执行顺序。专用查询在认知、自动认领、联网等普通路径之前分流；程序直接交付可零生成调用。</p>'+table(
        ['边界','本版设计','不能推导的结论'],[
            ['标准入口','<code>release_options()</code>统一开启capability_contract_enabled和role_state_enabled；text/web及hhu-avatar复用。底层Avatar/create_server保留显式配置兼容。','旧SDK直接调用不自动等同标准产品配置。'],
            ['来源帧','用户行/根稿件/说话者/session/revision/隐私代际核验；多次checkpoint与提交依赖追踪。','字节引用不是通用语义理解；已发送的第三方请求不能追溯撤回。'],
            ['来源数值与资料','有限已确认画像、正负偏好、两项同单位预算及更正；Decimal有界计算。','不声称基础模型学会任意算术、任意实体或任意自然语言归属。'],
            ['写作交付','要求、正文来源、字面/句数/签名、未同意状态与常见请假背景检查；最多一次修正或有限来源模板。','诚实拒绝/原文保留不等于自然润色已充分；未知材料不凭空补具体值。'],
            ['操作能力','本地提醒有真实事务/回执；无发送器时，有限外发/递交/代答应/身体承诺不得当现实执行。','没有短信/邮件/电话/提交功能；聊天存档不等于向他人承诺或投递。'],
            ['提醒查询与历史','独立只读服务；缺编号/混合目标澄清；观测时间/计划时间/ACK三态与当前状态分离。历史仅重建经验证快照。','历史记录有效不证明现在未变化；completed或ACK不证明真人执行/已读。'],
            ['角色/PAD','可信角色控制与来源恢复，角色状态跨OS持久化并衰减；隐私代际变化清自动状态，手动override独立。','不恢复旧用户观测当新输入；持久化工程不等于真人情感认同。'],
            ['可取消/隐私','生成/认知/工具后续派发/SDK返回/TTS发布设阶段屏障；来源删改失效派生记录与当前页面缓存。','取消不撤销合法已提交事实/提醒，也不是擦除用户下载副本或物理介质。'],
        ])+'<p class="sources">'+link('标准配置','src/avatar/release_options.py')+' · '+link('来源帧','src/avatar/brain/response_frames.py')+' · '+link('历史核验','src/avatar/brain/release_history.py')+' · '+link('口型渲染','frontend/src/features/chat/threeAvatar.ts')+'</p>')
    gate_rows = [
        ['Python完整v22','3143通过 / 1跳过，实际0；889源码输入保持','缺torch的可选PEFT训练集成跳过；不将其视作本版运行功能失败。',W+'006-写作交付与严格格式/python-writing-v22-binding.json'],
        ['前端v6','typecheck/lint/unit/build四步实际0；199单元/38文件','Vite包体积提示仍是提示；不等同目标设备性能验收。',W+'008-正式形象与统一媒体时钟/frontend-development-v6.json'],
        ['原生v15',f'{native["completed_trials"]}试次 / {native["completed_turns"]}轮 / {native["actual_generate_calls"]}真实generate；worker/provider均0','SDK/native消息、格式/schema/原始输出逐条对齐，PID/GPU退役。',W+'006-写作交付与严格格式/native-result-v15.json'],
        ['内容复核','候选0/129、对照39/129登记关键错配；258轮全审','68题全部暴露；同代理非人工来源/span审阅，相关回合不当独立样本。',W+'006-写作交付与严格格式/native-source-span-review-v15.json'],
        ['综合浏览器v4','13组实际0；默认19过/16可选跳过；必要可选组另零跳过','受控HTTP/SSE、隐私/导航/历史/投递/恢复，不代表通用模型语言。',W+'011-语音与综合发布门控/browser-final-batch-v4-result.json'],
        ['正式Three/时钟','1440×1000、390×844；seek/rate/pause/stop/上下文恢复/释放','真实Chromium软件ANGLE/SwiftShader；不是物理显示硬件验收。',W+'008-正式形象与统一媒体时钟/formal-browser-v9.json'],
        ['分段播放','固定480 RAF帧，段序[1,2,3]；时钟p95≤50ms、max≤100ms和实际几何通过','R01-020原漏首段失败保留；只改采样起点，不放松硬阈值。',W+'011-语音与综合发布门控/browser-playback-v6.json'],
        ['独立安装v11','482文件对应wheel；两个真实CLI、7个HTTP UI资源、旧库升级/备份回退','脱离仓库 -I 运行，pip check；仅3.10.12实际验，不外推全部声明解释器。',W+'011-语音与综合发布门控/install-smoke-v11-proof.json'],
        ['短程v6',f'60固定事件 / 120受控请求；总{soak["actual_seconds_including_startup_cleanup"]:.6f}s，P95 {soak["p95_seconds"]:.6f}s','BLAS/OMP=4；三个真实退出0/-9/0，重启不重复执行；不是多日。',W+'011-语音与综合发布门控/installed-soak-v6-proof.json'],
        ['公开ASR v5',f'40条/20人，567字，41编辑错；CER {asr["cer_on_successful_samples"]:.6%}，0失败','CPU int8；中位推理1.426604s、RTF0.312891。已知公开朗读，不是自由对话/物理采集。',W+'011-语音与综合发布门控/public-asr-cpu-v5.json'],
        ['信号v5','240解析配对、22整数PCM时钟含120秒，4子进程实际0','五锚区帧标签82.9167%/92.1429%，F2缺失50/12；不冒称真人音素准确率。',W+'011-语音与综合发布门控/signal-regression-v5.json'],
        ['真实语音服务补充','固定已知WAV→本地ASR→受控文本模型→真实Edge-TTS→浏览器，1项通过','原包v7 UI范围；此后仅采证观察器改变。不是原生LLM/真人整链质量。',W+'011-语音与综合发布门控/browser-real-voice-v1.json'],
        ['旧证据/报告','55 seal / 12737项、255问题原文不变；报告1440/390、40链接、实际0','不删除旧候选、部分执行、模型与失败；独立程序不当独立人评。',A+'工作目录/002-发布门控/report-qa-v1.json'],
    ]
    body += section('gates', '门控矩阵：每个数字都带适用范围', table(['门控','实际结果','解释边界','原始证明'],[[name,e(value),e(scope),link('证据',path)] for name,value,scope,path in gate_rows]), '02 / VALIDATION MATRIX')
    body += section('native', '原生实验的可复现身份与贡献分账', table(['配置','固定值/实际记录'],[
        ['注册模型','qwen3-4b-q4_k_m / GGUF；revision <code>bc640142c66e1fdd12af0bd68f40445458f3869b</code>'],
        ['模型SHA-256','<code>7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5</code>'],
        ['后端/输入','llama-cpp-python 0.3.19；54个native运行文件绑定，SDK/传输与官方模板留证。'],
        ['推理设置','temperature=0；seed=42；n_ctx=8192；max_tokens=512；thinking=False；单序列；n_gpu_layers=-1。'],
        ['实际设备','按余量选择GPU0，UUID <code>GPU-81550800-367d-1855-0f35-c61c274edfdf</code>；启动40441MiB余量/0%利用率，不固定后续卡号。'],
        ['配对与预算','68题×两臂=136试次、每臂129轮；最多600generate，实际359（对照213、候选146）。无整轮墙钟截止，保留单请求/readiness/清理边界。'],
        ['实际总采证时间',f'{native["elapsed_seconds"]:.6f}s，含环境/加载/审计与退役，不能当纯推理延迟。'],
    ])+'<p>候选开来源/角色契约，对照关闭；模型/权重未训练或替换。最后一轮与v14候选原文仅查询观测时间变化，其他源/SQL逐一核验；对照原生自然回复有变化，因此对照问题轮数40→39也照实保留。</p>'+table(
        ['候选最终generation_mode','回合数'],[[e(name),str(count)] for name,count in sorted(modes.items())])+
        '<p>这些模式直接来自129个候选回合：规则源交付、模型受约束重写/格式修正、模型自然回复分开。<b>零登记关键错配属于最终整链交付，不是基础模型自己零错误。</b>某些程序模板保留原句而非充分润色；不能用模式数量换算人类质量分。</p><p class="sources">'+
        link('冻结输入',W+'006-写作交付与严格格式/native-freeze-v15.json')+' · '+link('逐请求逻辑对齐',W+'006-写作交付与严格格式/native-alignment-v15.json')+' · '+link('运行时预检',W+'006-写作交付与严格格式/native-preflight-v15.json')+'</p>')
    rows = []
    result_paths = list((ROOT/(W+'006-写作交付与严格格式')).glob('native-result-v*.json'))+[ROOT/(W+'005-实际能力与来源答复修复/native-result-v1.json')]
    for path in sorted(result_paths,key=lambda p:int(p.stem.split('-v')[-1])):
        n = int(path.stem.split('-v')[-1]); value=json.loads(path.read_text());rp=path.with_name(f'native-source-span-review-v{n}.json');r=json.loads(rp.read_text()) if rp.exists() else {}
        rows.append(['v'+str(n),str(value.get('actual_generate_calls',value.get('actual_client_native_calls','未记'))),str(value.get('completed_turns','见原件')),e(r.get('failed_turns_by_arm', '见原审阅')), '通过注册范围' if r.get('content_approved') is True else '拒绝或需查原审阅',link('原始结果',path.relative_to(ROOT))])
    body += section('failures', '放行前返工：成功不能覆盖旧失败',
        '<p>下表仅列实际存在完成结果文件的原生版本。v7—v10等登记文件不能凭编号补造成额外成功实验；实验准备、未启动/退役状态与完成结果分别保留。不同版本题目数变化，不可跨行计算统一错误率。</p>'+table(['版本','实际generate','完成轮','关键错配（按臂）','内容决定','证据'],rows)+cards([
            ('新增问题闭环','R01-001—020涉及构建来源、查询历史、晚期隐私状态、真实退出码、流式缓冲、稿件/提醒/角色、版本元数据、浏览器编排、线程资源和播放采样。20项含采证缺陷，不能全称产品漏洞。'),
            ('覆盖缺口也算失败','53题阶段通过后，逐项复查原台账发现C02身体与原C37完整序列遗漏；保留受控复现，扩到68题后v13暴露三项残留，继续修复至v14/v15。'),
            ('元数据勘误追加，不回写','最初v8证明复制了旧build_result_sha256，产物SHA本身正确；追加verified-proof作为正式输入。v15托管context系列标记仍14，实际版本由v15路径/冻结SHA/全Git字节识别。'),
            ('旧实验继续隔离','C52/C55训练adapter、C15/16身体lab、C31只读提速、C38通用计划、C47—50历史表示候选的失败结论不因本次有限修复而追认通过。'),
        ])+'<p class="sources">'+link('构建新增20项台账',P+'发布构建新增问题台账.json')+' · '+link('原242项最终处置',P+'既有问题处置台账.json')+' · '+link('完整过程',P+'进展.md')+'</p>')
    portrait = Path('/data/Users/zrh/data/hhu-ai-avatar/artifacts/release/formal-browser-v9/avatar-1440.png')
    image = '<figure><img width="240" height="209" alt="真实浏览器正式形象截图：蓝色头发与服饰的程序三维人物小海" src="data:image/png;base64,'+base64.b64encode(portrait.read_bytes()).decode()+'"><figcaption>正式浏览器v9验收截图；程序生成Three形象，软件WebGL。不是目标物理设备或真人视觉评审。</figcaption></figure>'
    body += section('media', '渲染与故障行为', image+cards([
        ('一个实际播放时钟','口型帧由整数样本时间定位；Three与SVG消费同一媒体时钟。seek、倍速、暂停、停止和结束必须对齐，不能用墙钟振荡伪造语音口型。'),
        ('资源身份与释放','owned音频src和真实媒体状态核验，迟到事件/预取完成不能复活停止资源。GL丢失后同canvas恢复，卸载停止RAF并dispose几何/材质。'),
        ('显示与性能解释','逐帧通道避免聊天父树随每帧重渲染；历史诊断折叠后不做隐藏序列化。结构计数改进不是GPU帧率、CPU百分比或真人输入延迟保证。'),
        ('服务/进程边界','四个明确provider启动边有父死亡保护；实际GPU正常和硬杀生命周期均验证。硬杀manager的provider原父wait缺失保留null，以PID/GPU退役另证，不能捏造退出0。'),
    ])+'<p class="sources">'+link('provider链实际修复',W+'002-provider进程链修复/provider链修复结论.md')+'</p>')
    body += section('distribution', '发行、安装、数据和升级', table(['发行物','SHA-256'],[[e(Path(name).name),'<code>'+sha+'</code>'] for name,sha in build['artifacts'].items()])+
        '<p>稳定目录：<code>/data/Users/zrh/data/hhu-ai-avatar/releases/2.0.0</code>。含wheel/sdist、SHA256SUMS、README和distribution.json；原final-build-v8保留。源码、模型、缓存、环境、原始实验不混进发行包；包中包含7项UI资源、运行时来源和第三方声明。</p>'+code(
        'sha256sum -c SHA256SUMS\n# 在已安装2.0.0的独立环境\nhhu-avatar --version\nhhu-avatar doctor --require-ui\nOPENBLAS_NUM_THREADS=4 OMP_NUM_THREADS=4 hhu-avatar web --port 8765 --db /absolute/private/avatar.db')+
        '<p>安装实测使用全新环境、仓库外cwd与<code>-I</code>隔离导入；源码初始schema来自<code>349160c2</code>，真实种两项画像，经SQLite backup、升级、同DB两个CLI和旧源读取回滚副本核验。备份SHA不变。<code>doctor</code>仅离线检查，不等于网络模型/音频服务/设备可用。</p>'+table(
            ['短程状态','实际终态'],[[e(k),str(v)] for k,v in soak['final_sql']['counts'].items()])+
        '<p>三epoch各20事件，第二个进程在提交后SIGKILL（真实-9）；同进程重复请求不增加模型请求，跨重启历史request_id返回既有去重终态而不重跑。最终60账本completed、120消息、60结果、0动作回执/0提醒、1角色状态、SQLite integrity ok。</p>')
    body += section('limits', '发布接受的限制与未批准范围', table(['项目','当前事实','后续边界'],[
        ['一般语言与泛化','68题已暴露开发复验，有限解析、规则与模板参与结果。','没有独立盲测/人类自然度、充分性和任意措辞完备性结论。'],
        ['中文口型','五个锚区和解析信号存在误判/漏峰；ü/声调未实现或校准。','已留真人音素/ü声调校准待办，不把82.9%等说成人声准确率。'],
        ['物理设备','真实播放器/公开音频/模拟麦克风已测，目标麦克风/听感/物理AV尚未验。','按用户授权延期，不能宣传真实设备全链体验通过。'],
        ['持续使用','60事件约8.2秒短程、历史其他百轮另有范围；不是多日。','真实多日、多人并发与公众部署未获批准。'],
        ['依赖服务','外部LLM/Edge-TTS依赖配置与可用性；ASR默认不加载。','配置存在不等于连通，音频扩展与模型须显式准备。'],
        ['UI版本文案','侧栏v0.1旧标识仍在；核心/包/前端元数据2.0.0。','文案遗留如实记入本报告，未静默改已批准代码。'],
    ])+'<p class="sources">'+link('用户延期授权',P+'用户延期验收授权.json')+' · '+link('下次启动待办',P+'下次启动待办.md')+'</p>')
    body += section('reproduce', '如何独立复核这次发布',
        '<p>采用已提交清单而不是仅看汇总“通过”字段。校验器验证冻结Git字节、当前输入、原始请求/SQL、安装文件、旧seal与报告SHA，并以14个失败注入确保门控会拒绝坏证据。实际已核15671个文件、34份证明。新文档追加不改变获验输入。</p>'+code(
        './scripts/project-python -B \\\n  audit/2026-11-21-release-2.0.0/工作目录/002-发布门控/verify_release.py \\\n  --manifest audit/2026-11-21-release-2.0.0/工作目录/002-发布门控/release-manifest-v1.json \\\n  --output /data/Users/zrh/data/hhu-ai-avatar/artifacts/release/your-fresh-verification.json')+
        '<p>输出必须是新的文件路径；不要覆盖原批准证明。旧源码/冻结或二进制变动后，先重新登记相应测试与来源，不能拿旧门控认证新版本。14个已拒绝负控：</p>'+table(['门控负控'],[[e(name)] for name in gate['negative_controls_rejected']])+
        '<p class="sources">'+link('精确发布清单',A+'工作目录/002-发布门控/release-manifest-v1.json')+' · '+link('只读校验器',A+'工作目录/002-发布门控/verify_release.py')+' · '+link('完整系统审计',A+'系统审计与发布报告.html')+'</p>')
    toc=[('identity','版本与交付身份'),('architecture','架构与契约'),('gates','完整门控矩阵'),('native','原生实验与分账'),('failures','失败与返工'),('media','渲染/生命周期'),('distribution','分发与升级'),('limits','限制与延期'),('reproduce','独立复核入口')]
    return document('technical','2.0.0<br>技术发布报告','ENGINEERING RELEASE / VERIFIED SCOPE',
        '<p>有来源的交付、可恢复的角色与历史、实际媒体时钟和可独立安装的分发。这里描述工程实现、实验配置、门控证据及接受的限制，不把程序兜底当基础模型升级。</p>',toc,body,
        '<span class="badge">v2.0.0 / 有限软件与非人工范围获批</span>',
        [('3143 / 1','Python通过 / 可选跳过'),('359','真实CUDA生成调用'),('0 / 129','候选登记关键错配轮'),('13','综合浏览器门控组')])
