"""Add final scoped dispositions without rewriting historical findings or seals."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
P = ROOT/'docs/发布/2.0.0-rc.1'
W = P/'工作目录'


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def main():
    native = W/'006-写作交付与严格格式/native-source-span-review-v15.json'
    browser = W/'011-语音与综合发布门控/browser-final-batch-v4-result.json'
    assert read(native)['content_approved'] and read(browser)['passed']
    evidence = [str(x.relative_to(ROOT)) for x in [native, browser,
        W/'006-写作交付与严格格式/python-writing-v22-binding.json',
        W/'011-语音与综合发布门控/install-smoke-v11-proof.json']]
    ledger = read(P/'既有问题处置台账.json')
    for row in ledger['rows']:
        original = row['release_disposition']
        row['final_release_evidence'] = list(evidence)
        if original.startswith(('closed', 'rejected')):
            row['final_release_disposition'] = original
            row['final_release_review'] = ('保留原限定结论；未批准的候选/adapter不晋升。当前全量与独立安装为补充工程证据，'
                                           '不把旧实验结论改成当前通用语义或真人通过。')
        elif row['id'] == 'C05-003':
            row['final_release_disposition'] = 'deferred_by_user_phoneme_calibration_with_known_analytic_limits'
            row['final_release_review'] = ('五锚区解析开发结果仍有限：组件82.92%、网页16k92.14%，F2缺失50/12；'
                '没有实现或批准一般中文音素/ü/声调准确率。依用户本次暂用自动评审的授权保留为已知限制和下次校准待办，'
                '并非根治。时间协议与公开朗读ASR另有当前软件证据。')
            row['final_release_evidence'] += [str((W/'011-语音与综合发布门控/signal-regression-v5.json').relative_to(ROOT)),
                                            'docs/发布/2.0.0-rc.1/下次启动待办.md']
        elif row['id'] == 'C09-002':
            row['final_release_disposition'] = 'verified_fixed_event_software_scope_multiday_deferred_by_user'
            row['final_release_review'] = '60事件/120受控HTTP请求、三进程重启/硬杀及资源原门槛通过；实际秒级短程，真实多日未验。'
            row['final_release_evidence'].append(str((W/'011-语音与综合发布门控/installed-soak-v6-proof.json').relative_to(ROOT)))
        elif row['id'] == 'C08-002':
            row['final_release_disposition'] = 'verified_current_media_clock_and_rendered_geometry_scope'
            row['final_release_review'] = '真实浏览器三段/速率/跳转/暂停/停止、Three几何与50/100ms原门槛通过；软件WebGL，不是物理音画验收。'
            row['final_release_evidence'].append(str((W/'011-语音与综合发布门控/browser-playback-v6.json').relative_to(ROOT)))
        elif row['id'] == 'C33-002':
            row['final_release_disposition'] = 'verified_standard_entry_role_persistence_and_source_history_scope'
            row['final_release_review'] = '标准入口启用角色状态，真实独立OS进程和已安装CLI验证跨进程恢复/衰减；不恢复旧用户当作当前观察。'
        else:
            row['final_release_disposition'] = 'verified_registered_source_contract_scope_lab_candidates_remain_isolated'
            row['final_release_review'] = ('既有根因在标准来源契约下经完整软件和68题双臂逐来源复验；'
                '有限主体/数值/稿件/外发/身体/同意状态/提醒时效规则，无法核验时澄清或诚实拒绝。'
                '不是任意语言的完备语义验证器，也不批准旧lab或旧adapter。原始失败与原状态字段保持。')
            if row['id'] in ('C02-016', 'C16-002', 'C37-007'):
                row['final_release_evidence'] += ['docs/发布/2.0.0-rc.1/工作目录/012-既有根因覆盖补缺/既有根因受控复现结论.md'] if (W/'012-既有根因覆盖补缺/既有根因受控复现结论.md').exists() else ['tests/test_body_output_boundary.py', 'tests/test_original_c37_release_residuals.py']
                row['final_release_evidence'] = [x for x in row['final_release_evidence'] if (ROOT/x).is_file()]
    ledger['final_review_scope'] = ('242个ID均有最终处置；原状态/原始SHA保留。有限软件修复、隔离候选及用户延期分别列示。'
                                   '正式批准由独立发布门控输出决定，本表不能自行批准。')
    write(P/'既有问题处置台账.json', ledger)
    goals = read(P/'目标验收台账.json')
    goals['release_version_candidate'] = '2.0.0'
    statuses = dict(G01='verified_software_scope', G02='verified_software_scope',
                    G03='verified_with_user_deferrals', G04='verified_with_user_deferrals',
                    G05='verified_with_user_deferrals', G06='deferred_by_user',
                    G07='verified_with_user_deferrals', R01='verified_delivery')
    for goal in goals['goals']:
        goal['status'] = goal['final_release_status'] = statuses[goal['id']]
        goal['evidence'] = evidence
        goal['final_release_scope'] = ('仅有限登记工程/非人工评审范围；真人、物理、音素/ü/声调校准、多日仍留仓库待补。'
                                       '批准见audit/2026-11-21-release-2.0.0/工作目录/002-发布门控/release-gate-v1.json。')
        goal.pop('partial_evidence_scope', None)
    goals['approval_authority'] = '独立release-gate-v1.json及Git发布标签；本台账formal_release_allowed=False表示本表不自行发放批准'
    write(P/'目标验收台账.json', goals)
    text = ['# 既有问题最终处置矩阵', '', '原255份文档归并242个ID，13份重复原件未删除。原始状态和SHA保持，最终范围另列；完整证据见仓库JSON台账。', '',
            '| ID | 原问题 | 最终处置范围 |', '|---|---|---|']
    for r in ledger['rows']:
        text.append('| '+r['id']+' | '+r['title'].replace('|', '\\|')+' | '+r['final_release_disposition']+' |')
    (ROOT/'audit/2026-11-21-release-2.0.0/既有问题最终处置矩阵.md').write_text('\n'.join(text)+'\n')


if __name__ == '__main__':
    main()
