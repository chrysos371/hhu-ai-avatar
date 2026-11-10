"""Build a reproducible evidence-linked cycle snapshot; no service calls."""
from pathlib import Path
from html import escape
from hashlib import sha256
import json
import re

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE.parent / '实验'


def build():
    soak = json.loads((EVIDENCE / 'real-turn-soak100.json').read_text())
    paired = json.loads((EVIDENCE / 'literal-template-48-4b.json').read_text())
    assert soak['passed'] and soak['completed_rounds'] == 100
    assert len(paired['rows']) == 96 and all(r['passed'] for r in paired['rows'])
    tests = (EVIDENCE / 'python-full-soak.log').read_text().strip().splitlines()[-1]
    issues = [
        ('001', '预热失败导致整次实验无结果', '已修复：预热失败记录并继续固定样本'),
        ('002', '模型初审误放行/无效证据', '未通过：4B/14B均不接入默认回复'),
        ('003', '修正前错误草稿先发出', '已修复：任务交付先缓冲'),
        ('004', '修正阶段同步请求吞取消', '已修复：实际SDK传输可取消'),
        ('005', '来源删除后缓冲仍发送', '已修复：每次发送前检查来源版本'),
        ('006', '引用原文漏约束、写提醒误作动作', '有限语法修复；超范围自然语言未验收'),
        ('007', '自由修正漏原文且引入回归', 'v2有界模板改善已测样例；非通用语义通过'),
        ('008', '来源失效后仍发修正、复用旧任务', '已修复：各阶段屏障及来源版本清理'),
        ('009', '画像纠正覆盖合法第一人称代写', '已修复：活动写作合同定义视角'),
        ('010', '槽位全过却重复、断句和编造', 'v1不放行；v2已知8对复查，充分性仍开放'),
        ('011', '新问题/寒暄继承旧写作任务', '已修复：限定明确编辑跟进'),
    ]
    lines = ['# 第三轮系统审计与推进报告', '', '日期：2026-11-11（上海时间）。本报告为第三轮归档快照；后续循环独立留痕。', '',
        '## 结论与推进方向', '',
        '本轮形成可追溯的实验性交付链：用户约束→缓冲→一次有界修正→来源检查→可见回复。原文模板v2、隐私屏障、可取消传输和真实网页入口已有代码及实测。所有新增候选继续默认关闭；未达到通用陪伴质量或项目远期目标验收。', '',
        'P0：继续排查跨轮说话者归属与记忆污染，已复现明确角色扮演被存成真人资料；下一循环修复并重新做真实模型/网页验证。P1：用新的独立对话与自然度审查检验交付充分性，扩大来源删除、并发和持久运行测试。P2：真实设备语音、正式形象与音画校准沿用第二轮未完成项，不能用本轮文本结果代替。', '',
        '## 真实实验与负面结果', '',
        '- 初审v1：14B有效40/40、精确25/40，16个原明确违例9个错误放行；4B仅3/40符合严格说明协议，其余37不可评分。v2在已知16条开发回归4B12/16、14B9/16，仍失败。原标签两处一致性问题有单独澄清，未改写原始结果；没有独立人工金标或通用语义批准。',
        '- 自由文本修正：旧12场景11→12，新16两组均14/16且出现新回归。槽位v1后续36/36机械全过，但8次组合中6个样例出现重复、断裂或未知具体值，不能视作质量成功。',
        '- 完整模板v2对照v1：36已知回归+12新冻结场景，两组各48/48机械通过、各8次组合；8对代理复查未再见同样6项问题。部分v2为最小片段；新12本身未触发修正。结果不是模型原生能力，也不是独立自然度/充分性批准。',
        '- 浏览器真实4B：五轮写作、编辑、替换和新问题，1测试通过，观察2次v2组合；截图和实际可见文字归档。',
        f'- 真实HTTP/SSE耐久：100回合全部通过，用时{soak["seconds"]:.3f}秒；10次首个原生增量后取消、10次重复请求、45/95轮后来源删除。最终100用户/90助手/10提醒/100账本，SQLite完整性ok、缓存≤32。后续模型请求未观察到已删名字；取消未发文字或持久化助手回复。',
        '- RSS第10轮78.45→第100轮83.21MiB，最终收尾84.10MiB（包含审计采集）；线程2、FD6。未设多日或内存泄漏通过门槛，135秒不能证明多日稳定。', '',
        '## 单项审计', '', '| 编号 | 问题 | 当前结论 |', '| --- | --- | --- |']
    lines += [f'| [G2C3-{n}](issues/G2C3-{n}.md) | {title} | {status} |' for n, title, status in issues]
    lines += ['', '## 回归与证据边界', '', tests + '；前端33通过，lint/build通过；离线浏览器15通过/3可选跳过，真实模板浏览器另1通过。初版构建失败和修复后日志共同留存。', '',
        '原生4B使用已固定Qwen3-4B-Q4_K_M、temperature=0、seed=42、512 token上限，启动与实际GPU0信息见原始报告provider。14B仅用于初审校准，已退出。GPU根据当时余量选择，未固定后续索引。没有训练或自动部署，trace.verifier.available仍为False。第二轮009/016一般归属与身体边界仍开放；ASR、真人输入、物理设备、正式渲染等没有本轮新证据，不重复宣称通过。', '',
        '## 原始资料', '']
    names = ['review-calibration-14b.json', 'review-calibration-4b-v1-complete.json', 'review-evidence-first-dev-4b.json', 'review-evidence-first-dev-14b.json', 'literal-delivery-4b.json', 'literal-slots-36-4b.json', 'literal-template-48-4b.json', 'literal-template-paired-review.json', 'real-delivery-browser.json', 'real-delivery-browser.png', 'real-turn-soak100.json', 'python-full-soak.log', 'frontend-tests.log', 'frontend-build.log', 'frontend-build-fixed.log', 'browser-offline-final.log', 'real-template-browser.log']
    lines += [f'- [{name}](../实验/{name})' for name in names]
    lines += ['', '[全过程记录](../进展.md)；[100回合协议](真实回合耐久协议.md)。', '']
    md = '\n'.join(lines)
    (HERE / '系统审计与推进报告.md').write_text(md)
    def inline(s):
        return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', escape(s))
    body = []
    for line in lines:
        if line.startswith('# '): body.append('<h1>' + inline(line[2:]) + '</h1>')
        elif line.startswith('## '): body.append('<h2>' + inline(line[3:]) + '</h2>')
        elif line.startswith('| ---'): continue
        elif line.startswith('|'): body.append('<div class="row">' + inline(line.strip('| ').replace(' | ', ' · ')) + '</div>')
        elif line: body.append('<p>' + inline(line.removeprefix('- ')) + '</p>')
    html = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>第三轮系统审计与推进报告</title><style>body{margin:0;background:#f2f5fa;color:#192b40;font:16px/1.8 system-ui,sans-serif}main{max-width:1000px;margin:auto;padding:32px}h1{font-size:30px}h2{border-bottom:2px solid #c7d6e8;padding-top:24px}p,.row{overflow-wrap:anywhere}.row{padding:12px;background:white;border-bottom:1px solid #dee7ee}a{color:#155aa7} @media(max-width:600px){main{padding:16px}h1{font-size:25px}}</style><main>' + '\n'.join(body) + '</main></html>'
    (HERE / '系统审计与推进报告.html').write_text(html)
    paths = list(EVIDENCE.iterdir()) + list((HERE / 'issues').glob('*.md'))
    manifest = {p.relative_to(HERE.parent).as_posix(): sha256(p.read_bytes()).hexdigest() for p in sorted(paths) if p.is_file()}
    (HERE / '证据清单.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    for href in re.findall(r'href="([^"]+)"', html):
        assert (HERE / href).exists(), href
    print(f'{len(manifest)} evidence files; local links valid')


if __name__ == '__main__':
    build()
