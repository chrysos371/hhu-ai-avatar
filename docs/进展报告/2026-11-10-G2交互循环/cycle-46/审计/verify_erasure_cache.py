"""Read actual erased result JSON; demonstrate Row-repr oracle weakness explicitly."""
import json
from pathlib import Path
import sqlite3
import subprocess

from run_regression import ROOT, digest
from verify_system import BASE, WORK, read, sql_view


def main():
    output = BASE/'审计/收尾核验/erasure-cache-supplement.json'; assert not output.exists()
    first = BASE/'审计/收尾核验/system-evidence.json'
    assert read(first)['verified'] and read(first)['verifier_sha256'] == digest(BASE/'审计/verify_system.py')
    secret = 'C46待遗忘查询标题'
    cases = []
    for arm in ('sdk','web'):
        result = {'arm':arm}
        for stage in ('before','after'):
            path = WORK/'005-完成查询后的实际遗忘'/(arm+'-'+stage+'-forget.sql')
            conn = sql_view(path)
            try:
                # Explicit scalar extraction is essential; Row repr hides text.
                bodies = [r['result_json'] for r in conn.execute('SELECT result_json FROM memory_chat_results')]
                for body in bodies: assert isinstance(json.loads(body),dict)
                actual = any(secret in body for body in bodies)
                if arm == 'web': assert actual is (stage == 'before')
                else: assert bodies == []  # SDK never records public result rows.
                result[stage] = {'SQL_sha256':digest(path),'result_rows':len(bodies),'secret_in_actual_JSON':actual,
                    'JSON_sha256':[__import__('hashlib').sha256(s.encode()).hexdigest() for s in bodies]}
            finally: conn.close()
        cases.append(result)
    with sqlite3.connect(':memory:') as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('CREATE TABLE memory_chat_results (result_json TEXT)')
        conn.execute('INSERT INTO memory_chat_results VALUES (?)',(json.dumps({'reply':secret},ensure_ascii=False),))
        rows = list(conn.execute('SELECT result_json FROM memory_chat_results'))
        weak_reports_clean = secret not in str(rows)
        corrected_detects_pollution = any(secret in r['result_json'] for r in rows)
        assert weak_reports_clean and corrected_detects_pollution
    proof = {'verified':True,'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'verifier_sha256':digest(Path(__file__)),'first_system_sha256':digest(first),
        'scope':'supplements only the Row-repr cache absence assertion; first system output retained',
        'cases':cases,'deliberate_pollution_negative_control':{'weak_Row_repr_reports_clean':weak_reports_clean,
            'correct_scalar_JSON_detects_secret':corrected_detects_pollution},
        'C46_002_limited_closed':True,'issues_limited_closed_after_supplement':2,
        'additional_native_calls':0,'SQL_dumps_reread_not_newly_collected':4}
    output.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    print('C46 cache supplement:actual Web JSON secret before=true/after=false;SDK no public rows;pollution proves Row-repr weak')


if __name__ == '__main__':
    main()
