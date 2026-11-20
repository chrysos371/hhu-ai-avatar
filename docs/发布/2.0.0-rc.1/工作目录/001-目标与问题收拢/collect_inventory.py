"""Inventory existing goals/issues without treating keyword matches as closure."""
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess

ROOT=Path('/data/Users/zrh/repo/hhu-ai-avatar')
HERE=Path(__file__).resolve().parent
RELEASE=HERE.parents[1]


def digest(path):return sha256(path.read_bytes()).hexdigest()


def write(path,value):
    with path.open('x') as stream:json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n')


def main():
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    tracked=subprocess.check_output(['git','ls-files','-z','docs'],cwd=ROOT).decode().split('\0')
    rows=[]
    for name in sorted(tracked):
        path=ROOT/name
        if path.suffix!='.md' or not any(part in ('问题单','issues') for part in path.parts):continue
        content=path.read_text();lines=content.splitlines()
        cycle=re.search(r'/cycle-(\d+)/',name)
        number=re.search(r'(?:G2C\d+-)?(\d{3})',path.name)
        identifier=f'C{int(cycle[1]):02}-{number[1]}' if cycle and number else None
        title=next((line.lstrip('# ').strip() for line in lines if line.startswith('#')) ,path.stem)
        candidates=[line for line in lines[:20] if re.search(r'状态|OPEN|CLOSED|已关闭|限定关闭|未解决|P[0-3]',line)]
        rows.append({'id':identifier,'path':name,'sha256':digest(path),'title':title,
            'original_status_candidates':candidates,'referenced_issue_ids':sorted(set(re.findall(r'C\d{2,3}-\d{3}',content))),
            'release_disposition':'pending_review','release_impact':'unassessed','resolution_evidence':[],
            'automatic_keyword_classification_is_not_closure':True})
    device=Path('/dev/snd')
    write(HERE/'original-issues-v1.json',{'source_ref':head,'collector_sha256':digest(Path(__file__)),
        'issue_documents':len(rows),'rows':rows,'scope':'all tracked issue documents;historical status strings require explicit cross-cycle review'})
    write(HERE/'local-device-observation-v1.json',{'scope':'server device nodes only;not remote target equipment or physical acceptance',
        'snd_entries':sorted(p.name for p in device.iterdir()) if device.is_dir() else [],
        'PCM_device_nodes':sorted(str(p) for p in device.glob('pcm*')) if device.is_dir() else [],
        'independent_human_review_received':False,'physical_acceptance_passed':False})
    goals=[('G01','记忆与实际操作','来源/归属/版本/删除取消及真实副作用去重'),
        ('G02','交互时钟','暂停/跳转/速率/分段/取消与实际媒体显示一致'),
        ('G03','语音与形象','中文识别/音素口型/正式形象统一时间协议及真人ü/声调'),
        ('G04','生成与交付','未见场景、逐轮来源、自然度与任务充分性/独立判断'),
        ('G05','稳定使用','固定事件/故障重启资源/真实观察时长与多日闭环'),
        ('G06','真实设备体验','目标设备麦克风、播放、视觉听感与独立真人记录'),
        ('G07','已有代际提升判据','跨层质量/可靠性/速度可复现改进，关键不变量无退步'),
        ('R01','用户本次发布交付','完整版本/说明/启动/版本基础设施/归档不删除/全部门控后发布暂停')]
    write(RELEASE/'目标验收台账.json',{'source':'既有远期目标与验收路线的六层及跨层判据，加用户本次发布指令；不新增远期目标',
        'release_version_candidate':'2.0.0-rc.1','formal_release_allowed':False,
        'goals':[{'id':code,'name':name,'existing_acceptance':text,'status':'needs_verification','evidence':[]} for code,name,text in goals]})
    lines=['# 既有问题原始索引','','仅供收拢：原文状态可能被后续周期限定修复，尚不能据关键词认定当前缺陷或关闭。逐项处置和证据将写入发布台账。','',
        '| ID | 原始标题 | 原文 |','| --- | --- | --- |']
    for row in rows:
        target='../../../../'+row['path'].removeprefix('docs/')
        lines.append(f"| {row['id'] or '未统一编号'} | {row['title'].replace('|','/')} | [原文]({target}) |")
    (HERE/'原始问题索引.md').write_text('\n'.join(lines)+'\n')
    print('Release inventory:',len(rows),'existing issue documents;8 existing/release acceptance rows;no goal marked passed')


if __name__=='__main__':main()
