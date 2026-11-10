"""Durable download -> integrity gate -> idle-GPU evaluation -> same-condition comparison."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
PYTHON=ROOT.parent/'envs/hhu-ai-avatar-train/bin/python'


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--gpu',type=int,default=0)
    args=parser.parse_args();out=args.output.resolve()
    if not out.is_relative_to(ROOT.parent):raise ValueError('Run must stay in workspace')
    out.mkdir(parents=True,exist_ok=True)
    baseline=ROOT/'data/style-lab/style-regression-20261110-01'
    lock=ROOT/'data/style-lab/model-lock-003/models.lock.json'
    from avatar.lab.common import source_state
    def status(stage,**fields):
        data={'stage':stage,'updated_at':datetime.now(timezone.utc).isoformat(),'pid':os.getpid(),'automatic_deployment':False,**fields}
        temp=out/'status.tmp';temp.write_text(json.dumps(data,ensure_ascii=False,indent=2));temp.replace(out/'status.json')
        print(json.dumps(data,ensure_ascii=False),flush=True)
    def command(argv,name):
        with (out/name).open('ab') as log:
            subprocess.run([str(x) for x in argv],cwd=ROOT,stdout=log,stderr=log,check=True)
    try:
        expected=json.loads((baseline/'manifest.json').read_text())
        reference={'path':str(baseline),'manifest_sha256':digest(baseline/'manifest.json'),
                   'results_sha256':digest(baseline/'results.json'),'checks_sha256':digest(baseline/'checks.json'),
                   'backend_files':expected['backend']['files']}
        (out/'baseline-reference.json').write_text(json.dumps(reference,ensure_ascii=False,indent=2))
        if source_state()['files']!=reference['backend_files']:
            status('blocked',reason='backend_source_changed_before_download');return
        status('downloading',model='Qwen/Qwen3-14B',progress_file=str(ROOT.parent/'models/Qwen3-14B/range-download-progress.json'))
        command([PYTHON,ROOT/'scripts/download_locked_ranges.py','--lock',lock,'--model','14b','--workers','24'],'download.log')
        status('weights_verified')
        if source_state()['files']!=reference['backend_files']:
            status('blocked',reason='backend_source_changed_while_downloading');return
        from avatar.lab.runner import gpu_inventory,validate_gpu_selection
        cards=gpu_inventory()
        try:
            validate_gpu_selection([args.gpu],cards,required_cards=1)
            if cards[args.gpu]['used_mib'] != 0 or cards[args.gpu].get('utilization',0) != 0:
                raise ValueError('GPU must be entirely idle for unattended trial')
        except ValueError:
            status('blocked',reason='selected_gpu_busy_no_wait_or_takeover',gpu=args.gpu);return
        status('evaluating',gpu=args.gpu,model='Qwen/Qwen3-14B',cases=20,arms=['raw_base','base'])
        command([PYTHON,'-m','avatar.lab','evaluate','--include-raw','--lock',lock,'--model','14b','--gpus',args.gpu,'--output',out/'evaluation'],'evaluation.log')
        if source_state()['files']!=reference['backend_files']:
            status('blocked',reason='backend_source_changed_during_evaluation');return
        status('comparing')
        command([PYTHON,'-m','avatar.lab','compare','--runs',baseline,out/'evaluation','--output',out/'comparison'],'comparison.log')
        new=json.loads((out/'evaluation/results.json').read_text());old=json.loads((baseline/'results.json').read_text())
        matrix={'4b:'+arm:old[arm] for arm in ['raw_base','base']}
        matrix.update({'14b:'+arm:new[arm] for arm in ['raw_base','base']})
        comparison=json.loads((out/'comparison/comparison.json').read_text())
        lines=['# 4B / 14B 原始模型对照','',
          '同一20个已暴露开发场景，每组60轮。4B复用固定源码、同生成设置且适配器禁用的已保存记录；14B新跑。两者均BF16、关闭思考，未训练、未切换线上模型。',
          '','| 模型与组别 | 机械硬失败场景/20 | 中位轮耗时（秒） |','|---|---:|---:|']
        for label in matrix:
            m=comparison['arms'][label];lines.append(f'| {label} | {m["hard_failed_cases"]} | {m["turn_seconds_p50"]:.2f} |')
        lines += ['', '机械检查不等于语义正确率。14B是否改善角色视角、任务交付和事实归属，需要查看完整回复；quality_winner仍为null，不自动部署。',
                  '', '来源：原始模型卡 https://huggingface.co/Qwen/Qwen3-14B；固定权重revision与逐文件SHA256见evaluation/manifest.json。',
                  '', '4B参考来自上次同一PEFT容器中禁用适配器的输出，其原始权重不变；延迟仅作本次运行参考，不视为严格硬件性能基准。']
        (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n')
        rows={label:{r['id']:r for r in values} for label,values in matrix.items()}
        randomizer=random.Random(20261111);key={};review=['# 4B / 14B 四组完整对话审阅','', 'A–D逐场景随机映射；不是独立盲测，未人工批准。','']
        for caseid in rows['4b:base']:
            arms=list(rows);randomizer.shuffle(arms);key[caseid]=dict(zip('ABCD',arms));review+=['## '+caseid,'']
            for label,arm in key[caseid].items():
                review+=['### '+label,'']
                for turn in rows[arm][caseid]['turns']:review+=['用户：'+turn['user'],'','回复：'+turn['reply'],'']
        (out/'blind-review.md').write_text('\n'.join(review));(out/'unblinding-key.json').write_text(json.dumps(key,indent=2))
        status('completed',report=str(out/'SUMMARY.md'),semantic_quality='unscored',deployment_approved=False)
    except Exception as exc:
        status('failed',error_type=type(exc).__name__,details='See phase log; no automatic model deployment')
        raise


if __name__=='__main__':main()
