"""Render the completed directory migration; old experimental records stay intact."""
import json
from pathlib import Path
import sys

WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[2]
OLD = ROOT / 'docs/进展报告/2026-11-10-G2交互循环/cycle-33/审计'
sys.path.insert(0, str(OLD))
from render_report import render


def read(name):
    return json.loads((WORK / name).read_text())


proof = read('最终迁移核验.json')
manifest = read('迁移清单.json')
assert proof['verified'] and len(manifest['entries']) == 19
worktrees = [row for row in manifest['entries'] if row['kind'] == 'git_worktree']
sections = [
    {'title': '结果与范围', 'paragraphs': [
        '本项目配套数据已统一到/data/Users/zrh/data/hhu-ai-avatar。主代码、版本化文档和Git对象仍在/data/Users/zrh/repo/hhu-ai-avatar。repo根原envs/runtime/npm-cache和7个旧工作树条目均消失，没有留下这些同名兼容别名。',
        '19项主要迁移逐批记录。7工作树用git worktree move迁移，HEAD/干净状态及Git关联一致；同卷rename保留实际内容，Python环境未重装依赖。原模型、SQL、音频、语料和失败实验均保留，未用清理替代迁移。',
        '独立仓库local-qwen-multi-tier、其他项目及其全局模型/环境不属于本次范围，未迁移。用户暂停的远期研发Goal仍paused，未接入C35页面屏障，也未进行新模型推理、训练或GPU实验。'],
     'links': [('完整19项旧→新清单', '迁移清单.json'), ('只读总核验', '最终迁移核验.json'),
               ('当前本机布局与运行命令', '../../本机数据布局.md')]},
    {'title': '集中目录与兼容入口',
     'table': (['原内容', '集中根下位置', '迁移与后续写入'], [
        ['两个Python环境', 'envs/hhu-ai-avatar、envs/hhu-ai-avatar-llm', '27605项元数据迁前迁后一致；48入口/激活路径修复'],
        ['Node/浏览器/CUDA工具及旧临时实验', 'runtime/', '同卷迁移；字体路径与当前启动器修复'],
        ['npm及其他新缓存', 'cache/npm、pip、xdg、huggingface、torch等', '统一project_env；不改HOME或借用其他项目缓存'],
        ['本项目GGUF/ASR模型', 'models/', '29文件33005691978字节迁前迁后指纹一致，3登记模型SHA一致'],
        ['原主仓库data', 'artifacts/', '3329文件12286262370字节指纹一致，原数据入口为相对链接'],
        ['前端依赖/构建/浏览器结果', 'frontend/', '显式Vite/Playwright输出目录，代码内仅相对链接'],
        ['测试临时数据及隐藏.runtime', 'tmp/', '正常测试后仍外置，不重建repo真实目录'],
        ['打包元数据和20处旧字节码缓存', 'cache/build-metadata、cache/legacy-pycache', '既有数据保留，后续pycache使用集中前缀'],
        ['7个历史工作树', 'worktrees/', '逐项迁移及独立提交，没有删除分支或重写历史']]),
     'paragraphs': ['主仓库9个标准入口（data/models、前端3项、pytest缓存、test-tmp、.runtime、egg-info）及20处旧pycache仅为相对软链接。最终ignored资产扫描确认无实际运行数据留在代码目录；版本化证据和Git本身保留。',
        'Playwright正常删除重建结果目录，当前inode可变化；批次13保留迁移瞬间inode证明，最终核验确认重建仍在集中frontend。其他18个主要目录当前inode仍与迁前一致。'],
     'links': [('9入口检查', '全部九个兼容入口检查.json'), ('环境迁移及48处修复', '批次记录/10-python_environments.json'),
               ('隐藏目录补迁', '批次记录/15-hidden-runtime-and-package-metadata.json')]},
    {'title': '工作树逐项核验',
     'table': (['原目录名', '保留分支', '原HEAD', '迁后状态'], [
         [Path(row['source']).name, row['branch'].removeprefix('refs/heads/'), row['head'][:12], '干净；HEAD不变；main祖先']
         for row in worktrees]),
     'paragraphs': ['每个工作树分别提交迁移记录并串行推送。gitdir/common-dir已指向新位置，旧repo入口不存在；没有把7份目录作为独立Git克隆重新复制，也没有丢弃候选历史。']},
    {'title': '实际回归与内容身份',
     'table': (['检查', '最终实测', '范围与版本'], [
        ['完整Python', '1835 passed /1 skipped，125.65s', '监督器路径修复后relocated轮；423源码当前/Git历史一致'],
        ['完整前端', '183 passed', '不只定向30项，完整当前单元测试'],
        ['类型/Lint/生产构建', '通过；5份dist与C34实际包字节相同', '当前页面功能未改变；输出真实目录为集中frontend'],
        ['默认浏览器', '15 passed /16可选跳过，37.8s', '实际新venv prefix、7模块、5dist一致；受控本地提供方'],
        ['原生库与模型', '54文件和3登记权重SHA匹配', '只校验/导入，无模型构造或推理调用'],
        ['路径守卫', '新增10正负控，相关26 passed', '允许受控生成物外置，拒穿越/链接逃逸，协议仍须代码根'],
        ['历史封存与链接', 'C3–C34共32份seal字节未变，149当前MD链接有效', '原实验记录不改写成新地址，不伪造迁后新执行']]),
     'paragraphs': ['首轮1825/1通过后，隐藏目录补迁使旧监督器拒绝真实外置路径，verified轮出现1824过/1失败/1跳过。原失败、稳定源和修复定向日志均保留，新增10项后最终1835/1；没有覆盖前轮或筛选有利重复。',
        '每个最终模式分别绑定423项已提交源码，运行产物另记SHA；不把ignored的frontend/dist根路径冒称Git文件。原生文件与模型的迁前登记SHA未改写，新增迁后路径身份及原清单SHA。'],
     'links': [('最终Python执行', 'relocated-python-final-binding.json'), ('Python原日志', 'relocated-python-final.log'),
               ('完整前端执行', 'relocated-frontend-final-binding.json'), ('构建执行', 'relocated-build-final-binding.json'),
               ('默认浏览器执行', 'relocated-browser-final-binding.json'), ('浏览器实际运行身份', 'relocated-browser-final-runtime.json'),
               ('原生库/模型迁移证明', '原生库与模型迁移证明.json'), ('迁后原生身份', '迁后原生运行库身份.json')]},
    {'title': '问题修复、文档与版本管理',
     'table': (['事项', '处置', '状态'], [
        ['监督器旧路径边界', 'freeze/output接受受控数据根，协议保留代码根要求和SHA交接；10新正负控', '已修并完整复测'],
        ['迁前已有3处提醒测试Lint警告', '证明与760e774原字节一致；显式消费typed mock参数，不改响应/断言', 'Lint及8提醒用例通过'],
        ['旧封存记录绝对地址', '原字节与32清单保留；resolve_project_path读取新旧映射', '按历史保留，可解析新位置'],
        ['复发散落目录', 'project-python/frontend/companion统一数据根，9入口与20缓存链接核验', '已集中，repo根旧条目无别名'],
        ['研发暂停', '只做目录/路径兼容与验证，不宣称C35缓存问题已解决', '继续暂停，等待用户恢复']]),
     'paragraphs': [f'总核验时已检查{proof["author_checked_commit_count"]}次本任务提交作者均spinner-bot；7工作树、工具、环境、模型、运行数据、路径修复和各闭合实验分别小步提交。原失败和后续修复分开，推送串行等待，未强推或改写历史。报告、显示核验与归档继续独立提交。',
        'README、AGENTS、backend、网页说明、风格实验说明及.env示例已更新；数据根有独立README。当前入口用scripts/project-python及scripts/frontend.sh，可用HHU_AVATAR_DATA_ROOT覆盖。其他机器使用各自数据根，历史一次性实验脚本/JSON地址只作当时记录。'],
     'links': [('监督器问题与修复', '问题记录/001-监督器拒绝迁后外置描述与输出.md'),
               ('迁前Lint问题', '问题记录/002-迁前提醒测试Lint未使用参数.md'), ('全过程进展', '进展.md'),
               ('原始迁移计划', '计划.md')]},
]
metadata = render(WORK, '项目数据集中迁移报告',
    '2026-11-12 · spinner-bot · 数据根/data/Users/zrh/data/hhu-ai-avatar · 研发继续暂停',
    '迁移完成：配套目录及未纳管数据集中存放，当前入口/文档已更新，旧审计证据保持原字节。',
    sections, OLD / '系统审计与推进报告.html')
for extension in ('md', 'html'):
    (WORK / ('系统审计与推进报告.' + extension)).rename(WORK / ('迁移报告.' + extension))
(WORK / '报告生成记录.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
print(metadata)
