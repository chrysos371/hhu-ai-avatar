"""Generate fresh balanced identities without exposing the key in stdout."""
import csv
import hashlib
import json
from pathlib import Path
import secrets

root = Path('/root/Users/zyyh/hhu-ai-avatar')
p = root / 'data/evals/three-arms-20-schema-v2'
suite = json.loads((root / 'evals/companion/lora-dev-20.json').read_text())
results = json.loads((p / 'raw-results.json').read_text())
arms = ['raw_base', 'base_avatar', 'lora_avatar']
if (p / 'review.csv').exists():
    with (p / 'review.csv').open(encoding='utf-8-sig') as file:
        if any(row['reviewer_type'] or row['ranking'] for row in csv.DictReader(file)):
            raise ValueError('Never overwrite human review')
archive = p / 'original-labels'; archive.mkdir(exist_ok=False)
for name in ['blind-review.md', 'review.csv', 'unblinding-key.json']:
    (p / name).rename(archive / name)
rng = secrets.SystemRandom()
cases = list(suite['cases']); rng.shuffle(cases)
rng.shuffle(arms)
orders = [arms[i % 3:] + arms[:i % 3] for i in range(20)]
rng.shuffle(orders)
key = {}; lines = ['# 三组匿名完整对话（结构化分析复测）', '',
    '先看本文件并填写review.csv；其他结果文件含身份。',
    '三组每题重新随机分配X/Y/Z，列位置各组出现6–7次。',
    '只因内部分析达到上限不能判最终回复截断；各组按完整三轮的关键要求评分。', '']
with (p / 'review.csv').open('w', encoding='utf-8-sig', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(['blind_id','X_quality','Y_quality','Z_quality','ranking','reviewer_type','reviewer','evidence'])
    for i,(case,order) in enumerate(zip(cases,orders),1):
        label=f'triad-{i:02d}';key[label]=dict(case_id=case['id'],**dict(zip('XYZ',order)))
        writer.writerow([label]+['']*7)
        lines += [f'## {label}', '', '检查：'+'；'.join(case['checks']), '']
        for side,arm in zip('XYZ',order):
            lines += [f'### {side}', '']
            for n,t in enumerate(results[arm][case['id']]['turns'],1):
                lines += [f'用户{n}：{t["user"]}', '', f'助手{n}：{t["reply"]}', '']
key_path=p/'unblinding-key.json';key_path.write_text(json.dumps(key,ensure_ascii=False,indent=2))
(p/'blind-review.md').write_text('\n'.join(lines))
assert all(sorted(sum(k[s]==a for k in key.values()) for a in arms)==[6,7,7] for s in 'XYZ')
(p/'reblinding-provenance.json').write_text(json.dumps(dict(method='SystemRandom; balanced cyclic orders shuffled independently of case order',key_sha256=hashlib.sha256(key_path.read_bytes()).hexdigest(),script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),indent=2))
print('Fresh anonymous packet written; identities not printed.')
