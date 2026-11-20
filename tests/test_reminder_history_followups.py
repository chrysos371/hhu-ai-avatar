"""Known C50 development cases through actual SDK, SQL and a hostile stub.

This is a deterministic engineering counterexample, not measured model quality.
The product must never import this corpus or its oracle observations.
"""
from contextlib import closing
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
import time

import pytest

from avatar.brain.conversations import ConversationStore
from avatar.brain.memory import MemoryStore
from avatar.main import Avatar
from test_capability_prompt_lab import Recorder
from test_reminder_query_flow import projection

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT/'evals/interaction/cycle-50/natural-history-cases.json').read_text())['cases']


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['id'])
def test_known_history_boundary_with_foreign_sql_writer_and_hostile_generation(tmp_path, case):
    evidence = os.environ.get('AVATAR_RELEASE_FOLLOWUP_EVIDENCE_DIR')
    folder = tmp_path
    if evidence:
        folder = Path(evidence).resolve()
        assert folder.is_relative_to(Path('/data/Users/zrh/data/hhu-ai-avatar/artifacts/release'))
        folder = folder/case['id']; folder.mkdir(exist_ok=False)
    db = str(folder/'state.db')
    model = Recorder('目前仍然有效，创建时间是2099年1月1日，你已亲眼读过并完成。')
    seed = case['seed']; ident = seed['record_id']
    due = datetime.fromisoformat(seed['due_date']).timestamp()
    with closing(MemoryStore(db)) as memory:
        bot = Avatar(memory=memory, llm=model, capability_contract_enabled=True, role_state_enabled=True)
        def insert(conn, status):
            conn.execute('INSERT INTO memory_reminders(id,title,due_at,created_at,status) VALUES (?,?,?,?,?)',
                (ident, seed['title'], due, time.time(), status))
        with memory.transaction():
            if seed['status_at_query'] != 'missing': insert(memory._conn, seed['status_at_query'])
            if seed['client_ack_recorded']:
                memory._conn.execute('INSERT INTO memory_reminder_deliveries(reminder_id,created_at,acknowledged_at) VALUES (?,?,?)',
                    (ident, time.time(), time.time()))
        queries = [bot.respond(case['query_text'], mode='reminder_query')]
        ConversationStore(memory).record_result(queries[-1])
        with closing(sqlite3.connect(db)) as actor:
            if case['independent_actor_after_query'] == 'create_record': insert(actor, 'active')
            else: actor.execute('UPDATE memory_reminders SET status=? WHERE id=?',
                (case['independent_actor_after_query'].removeprefix('set_'), ident))
            actor.commit()
        if case['repeat_query_after_actor']:
            queries.append(bot.respond(case['query_text'], mode='reminder_query'))
            ConversationStore(memory).record_result(queries[-1])
        before = projection(memory)
        analysis_before, generation_before = len(model.analysis), len(model.native)
        if case['group'] == 'actual_action_request': model.reply = '已拨出。'
        if case['group'] == 'preservation_control': model.reply = '小林说：“我已经打电话通知他了”。'
        deltas = []
        result = bot.respond(case['followup_text'], on_delta=deltas.append)
        evidence_data = dict(case_id=case['id'], source_queries=queries, result=result, deltas=deltas,
            business_before=before, business_after=projection(memory),
            analysis_calls=len(model.analysis)-analysis_before, generation_calls=len(model.native)-generation_before,
            actual_generation_prompts=model.native[generation_before:],
            scope='known development, hostile stub, actual SQL; not native or human quality')
        if evidence: (folder/'result.json').write_text(json.dumps(evidence_data, ensure_ascii=False, indent=2)+'\n')
        assert projection(memory) == before
        assert not result['tool_calls'] and not result['due_reminders'] and not result['action_receipts']['items']
        if case['group'] == 'actual_action_request':
            assert result['generation_mode'] == 'rules_capability_request'
            assert len(model.native) == generation_before
        elif case['group'] == 'preservation_control':
            literal = '我已经发出通知，请查收' if 'draft' in case['id'] else '我已经打电话通知他了'
            assert literal in result['reply']
            assert result['generation_mode'] in ('rules_writing_artifact', 'llm', 'llm_writing_repaired')
        else:
            assert result['generation_mode'] == 'rules_reminder_history'
            assert len(model.native) == generation_before
            data = result['reminder_history']
            assert data['current_state_verified'] is data['human_reading_verified'] is data['human_task_completion_verified'] is False
            assert data['source_query_user_ids'] == [q['conversation']['user_message_id'] for q in queries]
            assert '创建时间是2099' not in result['reply']
            assert '未重新查询' in result['reply']
