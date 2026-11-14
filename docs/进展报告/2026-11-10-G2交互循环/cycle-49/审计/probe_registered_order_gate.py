"""Reproduce archived oracle defects and test actual runner order/gate changes.

Only selected pure AST fragments execute; no provider or SDK is constructed.
"""
import argparse
import ast
from collections import Counter
import json
from pathlib import Path
import subprocess

from native_common import ROOT,BASE,CASES,PROTOCOL,read,digest

WORK = BASE/'审计/工作目录/001-材料与来源调查'


def fragment(source,predicate):
    nodes = [n for n in ast.walk(ast.parse(source)) if predicate(n)]
    assert len(nodes)==1,len(nodes)
    return compile(ast.fix_missing_locations(ast.Module(body=[nodes[0]],type_ignores=[])),
        'pure selected research AST','exec')


def main(mode):
    destination = WORK/('registered-oracle-'+mode+'.json'); assert not destination.exists()
    material = read(CASES); protocol = read(PROTOCOL); cases = {c['id']:c for c in material['cases']}
    original_path = WORK/'verify-native-before-order-review.py.txt'; original = original_path.read_text()
    order_node = lambda n: isinstance(n,ast.For) and isinstance(n.target,ast.Tuple) and [getattr(v,'id',None) for v in n.target.elts]==['index','case']
    old_order = fragment(original,order_node)
    old_gate = fragment(original,lambda n:isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='primary' for t in n.targets))
    old_positions = []
    for repetition in range(1,4):
        namespace = {'protocol':protocol,'cases':cases,'repetition':repetition,'order':[]}
        exec(old_order,namespace)
        old_positions.append(dict(Counter(arm for _,arm in namespace['order'][::3])))
    namespace = {'transport':True,'stops':326,'source_ok':True,'facts_ok':True,'modes_ok':True,
        'scores':{a:54 for a in protocol['arms']},'protocol':protocol}
    exec(old_gate,namespace)
    assert namespace['primary'] is False
    assert all(counts.get('C48_typed_control',0)==0 for counts in old_positions)
    result = {'mode':mode,'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'probe_sha256':digest(Path(__file__)),'archived_verifier_sha256':digest(original_path),
        'old_first_positions':old_positions,'old_gate_rejects_registered_perfect_result':True,
        'native_calls':0,'SDK_calls':0,'provider_constructions':0}
    if mode=='fixed':
        from verify_native import registered_order, primary_passes
        runner_path = BASE/'审计/run_native.py'; runner = runner_path.read_text()
        runner_cases = fragment(runner,order_node)
        first_by_case = {c:[] for c in cases}; positions = []
        for repetition in range(1,4):
            namespace = {'protocol':protocol,'cases':list(cases.values()),'repetition':repetition,'groups':[]}
            # Execute only the actual runner's order expressions, excluding the
            # sampling loop below them. The source selector is intentionally exact.
            node = next(n for n in ast.walk(ast.parse(runner)) if order_node(n))
            assignments = [n for n in node.body if isinstance(n,ast.Assign)]
            assert [n.targets[0].id for n in assignments[:2]] == ['offset','arms']
            generated = []
            for index,case in enumerate(cases.values()):
                local = {'protocol':protocol,'index':index,'repetition':repetition}
                code = compile(ast.fix_missing_locations(ast.Module(body=assignments[:2],type_ignores=[])),'actual runner order','exec')
                exec(code,local); generated.extend((case['id'],a) for a in local['arms'])
            assert generated == registered_order(cases,protocol,repetition)
            count = Counter(a for _,a in generated[::3]); assert count == Counter({a:6 for a in protocol['arms']})
            positions.append(dict(count))
            for case,arm in generated[::3]:first_by_case[case].append(arm)
        assert all(set(arms)==set(protocol['arms']) for arms in first_by_case.values())
        scores = {a:54 for a in protocol['arms']}
        assert primary_passes(True,326,True,True,True,scores,protocol) is True
        rejected = []
        for stops,score in [(325,54),(146,54),(326,53),(326,36),(326.0,54),(326,54.0),(True,54),(326,True)]:
            assert primary_passes(True,stops,True,True,True,scores|{protocol['primary_candidate']:score},protocol) is False
            rejected.append({'stops':stops,'candidate_score':score})
        result.update(verified=True,runner_sha256=digest(runner_path),
            'current_verifier_sha256':digest(BASE/'审计/verify_native.py'),
            current_first_positions=positions,each_case_each_arm_first_once=True,
            perfect_registered_result_passes=True,invalid_count_gates_rejected=rejected)
    else: result.update(expected_red_reproduced=True,count_as_admission=False)
    destination.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C49 oracle',mode,'old two-arm order/146-36 gate reproduced;',
        'current 6/6/6 and326-54 verified' if mode=='fixed' else 'no native;not admitted')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=('red','fixed'))
    main(parser.parse_args().mode)
