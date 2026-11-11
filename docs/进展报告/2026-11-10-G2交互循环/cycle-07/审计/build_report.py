"""Rebuild software-clock audit, explicitly distinct from device synchrony."""
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
EVIDENCE=HERE.parent/'实验'


def build():
    read=lambda name:json.loads((EVIDENCE/name).read_text())
    before=read('timeline-baseline-final.json');after=read('timeline-combined-final.json')
    cosmetic_before=read('cosmetic-before.json');cosmetic_after=read('cosmetic-after.json')
    compatibility=read('fractional-compatibility.json')
    assert not before['sample_clock_gate_passed'] and after['sample_clock_gate_passed']
    assert not cosmetic_before['passed'] and cosmetic_after['passed']
    assert compatibility['passed'] and len(compatibility['rows'])==160
    tests=(EVIDENCE/'python-full-final.log').read_text().strip().splitlines()[-1]
    longest_old=before['rows'][-1];longest_new=after['rows'][-1]
    changes=sum(not row['timestamps_preserved'] for row in compatibility['rows'])
    lines=['# 第七轮系统审计与推进报告','','日期：2026-11-11（上海时间）。作者：spinner-bot。承接069d6ce。','',
        '## 当前结果','',
        '默认口型时间戳按真实整数样本跳步计算，与frame_signal窗口起点一致。分帧数量、频谱、元音/能量和默认开口没有改变；非整数hop不再用名义毫秒累积时钟。参数尺寸验证也使用分帧相同的运算表达式。',
        '显式装饰闭口改为每个绝对目标k×period分别映射最近真实帧，取消周期先取整后重复造成的相位漂移。极小周期最多一次/帧，分配量不超过帧数；第一帧不强制闭口。默认close_every仍为None，装饰事件不是自然停顿检测。','',
        '## 先失败后的实测','',
        '| 检查 | 旧结果 | 修复后 |', '| --- | --- | --- |',
        f'| 21短配置+1个120秒固定例 | {sum(row["sample_clock_passed"] for row in before["rows"])}/22通过 | 22/22通过 |',
        f'| 22050Hz、10ms、120秒末帧误差 | {longest_old["max_error_ms"]:.6f}ms | {longest_new["max_error_ms"]:.3g}ms（浮点残差） |',
        f'| 同例末帧标记 | {longest_old["last_time"]:.6f}s，超过音频结束 | {longest_new["last_time"]:.6f}s，完整窗口在音频内 |',
        f'| 实际Avatar本机WAV TTS文件接口误差 | {before["file_api"]["max_error_ms"]:.6f}ms | {after["file_api"]["max_error_ms"]:.3g}ms |',
        '| 显式35ms周期、2秒音频 | 目标56次，实际65次 | 56次，逐个目标相位误差≤半hop（浮点容差） |',
        '| 显式0.3秒周期、22050Hz | 13次但量化间隔累计偏离目标 | 13次，按绝对目标分别量化 |','',
        '时钟实验用零PCM隔离几何，未据此评价语音自然度；实际文件API另注入相同的本机生成正弦WAV，前后音频SHA256相同，确实经过Avatar.respond(use_tts=True)与解码分析，没有远程LLM/TTS或麦克风。软件帧起点误差不是物理设备播放延迟。',
        '固定矩阵覆盖8000/11025/16000/22050/24000/44100/48000Hz及10/7.5/12.3ms跳步；另有120秒22050Hz固定长度，无实验墙钟截止。修复前后均以实际int(sr×hop_ms/1000)样本偏移作判据，误差门槛1e-6样本。','',
        '## 不应被修复改变的行为','',
        f'复用第六轮已执行的160条路线作已知回归，新增未见样本数为0：全部波形哈希、帧数及mouth_open/vowel/energy精确一致。{changes}条非整数hop路线时间按样本修正；其余{160-changes}条保留包括时间在内的全部字段。另有冻结正弦参考与整数hop样例精确比较。',
        '显式装饰模式的开口事件相位属于本轮有意修复，不要求保留旧错误事件位置；元音、能量和实际帧时间不因装饰改变。常规整数周期的既有测试保持通过。','',
        '## 单项审计','',
        '| 编号 | 处理 |', '| --- | --- |',
        '| [G2C7-001](issues/G2C7-001.md) | 累积样本时钟漂移；新26项先13败/13过，真实文件接口也失败，修复后22配置与文件接口通过 |',
        '| [G2C7-002](issues/G2C7-002.md) | 显式装饰周期预量化漂移；2个实验失败，新7项先2败/5过，绝对目标和极小周期边界修复 |','',
        '## 回归与版本范围','',tests+'。音频/取消/时钟关联105通过；语音浏览器9通过（27.6秒）为001修复后、002修复前快照，002仅显式装饰分支且网页默认关闭。前端产品代码无本轮修改，不伪称重新跑了前端构建/单测。',
        f'最终完整时钟实测HEAD：{after["source_head"]}，显式周期实测HEAD：{cosmetic_after["source_head"]}，兼容性回归HEAD：{compatibility["source_head"]}；源码哈希均保留。第六轮2.493倍分析性能及相对旧输出一致仅对应其归档源码，本轮独立修正非整数时间，不回写旧数据。',
        '历史第六轮研究评测要求相对旧时钟不变，复现应使用它记录的源码HEAD；当前时钟评估以样本位置和非时间三字段为准，不把有意修正误标为识别质量变化。第六轮失败的补峰候选继续隔离lab，没有因时钟修复启用。','',
        '## 下一循环与未验证范围','',
        'P1：在真实播放时钟下量化音画延迟、段间切换、暂停/恢复和设备采样边界，并继续来源删除/实际动作回归。P1：口型识别仍需独立真人音素标注和新的质量候选；不得继续用第六轮验证参数追调。P2：正式形象适配与真人设备体验。',
        '本轮没有物理麦克风/扬声器闭环、真人嘴型标注、ü/声调或正式渲染验收；旧一般归属/身体边界、模板充分性、多日稳定等限制仍开放，没有宣布项目远期目标完成。CPU执行，没有启动GPU任务。','',
        '## 原始资料','']
    names=['timeline-before.json','sample-clock-before.log','timeline-baseline-final.json','timeline-combined-final.json','rounding-probe.json','cosmetic-before.json','cosmetic-after.json','cosmetic-tests-before.log','cosmetic-tests-after.log','fractional-compatibility.json','python-full-final.log','browser-audio.log']
    lines += [f'- [{name}](../实验/{name})' for name in names]
    lines += ['','[全过程记录](../进展.md)；[计划](../计划.md)。','']
    (HERE/'系统审计与推进报告.md').write_text('\n'.join(lines))
    def inline(s):return re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'<a href="\2">\1</a>',escape(s))
    body=[];table=False
    for line in lines:
        if line.startswith('| ---'):continue
        if line.startswith('|'):
            cells=line.strip('| ').split(' | ')
            if not table:body.append('<div class="table-wrap"><table>');table=True;tag='th'
            else:tag='td'
            body.append('<tr>'+''.join(f'<{tag}>'+inline(cell)+f'</{tag}>' for cell in cells)+'</tr>');continue
        if table:body.append('</table></div>');table=False
        if line.startswith('# '):body.append('<h1>'+inline(line[2:])+'</h1>')
        elif line.startswith('## '):body.append('<h2>'+inline(line[3:])+'</h2>')
        elif line:body.append('<p>'+inline(line.removeprefix('- '))+'</p>')
    html='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>第七轮系统审计与推进报告</title><style>body{margin:0;background:#f2f5fa;color:#192b40;font:16px/1.8 system-ui,sans-serif}main{max-width:1080px;margin:auto;padding:32px}h1{font-size:30px}h2{border-bottom:2px solid #c7d6e8;padding-top:24px}p{overflow-wrap:anywhere}table{width:100%;border-collapse:collapse;background:white}td,th{padding:10px;border:1px solid #dee7ee;text-align:left;vertical-align:top}th{background:#e4edf7}.table-wrap{overflow:auto}a{color:#155aa7}@media(max-width:600px){main{padding:16px}h1{font-size:25px}table{font-size:14px}}</style><main>'+'\n'.join(body)+'</main></html>'
    (HERE/'系统审计与推进报告.html').write_text(html)
    for href in re.findall(r'href="([^"]+)"',html):assert (HERE/href).exists(),href
    paths=list(EVIDENCE.iterdir())+list((HERE/'issues').glob('*.md'))
    manifest={p.relative_to(HERE.parent).as_posix():sha256(p.read_bytes()).hexdigest() for p in sorted(paths) if p.is_file()}
    (HERE/'证据清单.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(f'{len(manifest)} evidence files; local links valid')


if __name__=='__main__':build()
