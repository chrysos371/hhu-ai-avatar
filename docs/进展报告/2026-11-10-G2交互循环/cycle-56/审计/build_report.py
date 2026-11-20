"""Measured C56 CPU engineering report; open provider-chain boundary retained."""
from datetime import datetime,timezone,timedelta
import os
from pathlib import Path
import subprocess
from audit_common import ROOT,BASE,AUDIT,OUT,require,read,sha,write,load


def main():
    system=read(OUT/'system-evidence.json')
    require(system['verified'] and not (OUT/'report-render-metadata.json').exists(),'verified fresh system report required')
    renderer=load('c56_readonly_renderer',BASE.parent/'cycle-50/审计/render_report.py')
    link=lambda label,p:(label,os.path.relpath(p,AUDIT))
    one=AUDIT/'工作目录/001-父死亡保护与终态留痕'
    sections=[{'title':'结论与范围','paragraphs':[
        'C56限定修复并验证了直接worker在监督器硬终止后的自动退役，以及worker命令重入破坏已有终态的问题。原2项真实CPU红测转绿，完整当前Python2562通过/1跳过，812项当前/Git输入在测试前后保持。',
        '本轮0新增真实LLM/训练/GPU实验，没有新模型质量批准。C55两个失败adapter持续隔离、默认模型不变；不能把工程通过或历史2548/1复用当本轮新实验。',
        '系统补充审计发现更深一层边界：真实CPU三层Popen形状中manager信号9、孙payload信号0；硬杀监督器后manager退役、孙payload仍活。所有自建残留精确清理，无关自建CPU对照存活。该项OPEN，未宣称实际GPU provider泄漏或任意进程树已经测过。'],
        'links':[link('系统数据',OUT/'system-evidence.json'),link('完整Python源码绑定',AUDIT/'工作目录/002-当前软件回归/python-first-binding.json'),link('原2项红测',one/'red-v1.log')]},
    {'title':'实际实验与回归','table':(['项目','实际结果','解释边界'],[
        ['原实现真实CPU红测','2失败；2.51秒','直接子任务残留；旧成功终态被重入改为failed/null，payload没有重复执行'],
        ['定向控制','28+10+2=40通过','包含原26与新回归；与完整套件重叠，不把次数相加作独立证据'],
        ['完整当前Python','2562通过/1跳过；183.91秒；812输入稳定','新增guard/测试及全部evals/training/config纳入；无前端或原生质量验收宣称'],
        ['真实exec/独立venv','内核信号9，sys.prefix/argv保留','保护器在新解释器安装后exec，不使用多线程preexec_fn'],
        ['独立CPU回执/正常停止','9实际任务原料复核；payload ready后停止，实际wait=-2','两身份退役；硬杀原父后wait仍未知，不从running/null伪造成功'],
        ['多级链实际边界','manager=9、孙payload=0；manager死/孙仍活','只模拟CPU形状；全部精确清理，实际GPU provider链未验证']]),
        'links':[link('28控制绑定',one/'supervisor-green-binding-v1.json'),link('10 guard控制绑定',one/'guard-controls-binding-v1.json'),link('并发claim控制',one/'claim-controls-binding-v1.json'),link('9任务与exec后停止原料',AUDIT/'工作目录/003-独立CPU留痕复核/cpu-receipts-v1.json'),link('多级链负结果',AUDIT/'工作目录/004-多级进程链边界/chain-cpu-v1.json')]},
    {'title':'工程修复及未解决问题','table':(['单项','状态','实际证据/后续'],[
        ['001 直接子任务父死亡退役','限定关闭','ready payload即便忽略SIGINT/SIGTERM，父SIGKILL后仍自动退役；可信直接子任务范围'],
        ['002 worker重入覆盖终态','限定关闭','旧格式4状态及新claim重入拒绝，原文件字节保留；两并发入口只有一个实际执行'],
        ['003 多级provider形状孙进程','OPEN / P1','fork后信号清零，CPU payload仍活；下轮明确保护项目manager→provider边并复测']]),
        'paragraphs':['新保护器绑定配置/源码SHA、实际父PID与启动身份，设置后再次核对父身份以关闭先死竞态；监督器观察最终payload argv，避免把过渡保护器命令误认为真实工作进程。正常返回、失败7、显式停止非零保留真实wait结果。',
            '直接重入在任何status替换前拒绝旧已尝试任务，并用x独占监督claim抵挡并发。监督器被硬杀时不能恢复其原wait回执，历史未知终态保持；不声称断电持久化、跨OS或凭据变化后仍受保护。',
            '真实父已退出的控制属于实际CPU进程；设置后的调度竞态和syscall失败路径是明确标记的合成seam，不冒充实际内核失败。Linux与Python一级文档链接见设计依据，工程结论以本机实验限定。'],
        'links':[link('001直接父死亡问题',AUDIT/'问题单/001-父死亡后直接子任务残留.md'),link('002终态覆盖问题',AUDIT/'问题单/002-worker直接重入覆盖已有终态.md'),link('003进程链边界',AUDIT/'问题单/003-多级provider形状的孙进程未受保护.md'),link('技术依据与适用范围',one/'设计依据.md')]},
    {'title':'系统完整性与下一轮','paragraphs':[
        '54旧封存/12694项与9集中资产入口保持；另核C55实际阶段1867项原料、14 adapter文件及111外部冻结绑定。C55旧534源在其原Git版本核验，当前其中只有监督器源按本轮有意改变；不拿旧冻结认证新源，也不回写旧证据。',
        '本轮2项限定关闭/1项OPEN；C55自然回复门槛仍失败（新外部联合9/18对基座6/18），材料覆盖、独立人评、真人物理设备、口型和多日全链路仍开放。P0保留全部失败与候选隔离；P1下一轮补明确manager→provider边保护和正常生命周期；随后登记当前能力/来源契约实模机制对照，按实际余量选择GPU并核退役。',
        '持续远期目标仍active。此次没有达到模型语义或整体代际跃迁，封存后继续下一轮，不把审计通过当任务总体完成。'],
        'links':[link('过程进展',BASE/'进展.md'),link('C55失败对照报告',BASE.parent/'cycle-55/审计/系统审计与推进报告.md'),link('远期目标与验收',BASE.parent/'远期目标与验收路线.md')]}]
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    stamp=datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')
    style=BASE.parent/'cycle-53/审计/工作目录/006-报告显示修复/report-style-v2.html.txt'
    meta=renderer.render(AUDIT,'C56 父死亡保护与终态留痕系统审计报告',stamp+' · 源 '+head[:12],
        '两个直接worker工程问题限定关闭；多级provider链仍有开放边界；无新模型质量批准',sections,style)
    meta.update(builder_sha256=sha(Path(__file__)),system_sha256=sha(OUT/'system-evidence.json'),
        MD_sha256=sha(AUDIT/'系统审计与推进报告.md'),HTML_sha256=sha(AUDIT/'系统审计与推进报告.html'),style_sha256=sha(style))
    write(OUT/'report-render-metadata.json',meta)
    print('C56 report built',meta['tables'],'tables',meta['links'],'local links;chain boundary retained')


if __name__=='__main__':main()
