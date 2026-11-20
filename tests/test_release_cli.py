"""Application-entry checks use fresh interpreters and isolated real databases."""
import json
import os
from pathlib import Path
import subprocess
import sys
import sqlite3

from avatar import __version__
from avatar.application_assets import check_frontend

ROOT = Path(__file__).resolve().parents[1]


def invoke(tmp_path, *args, input=None, no_site=False, extra_env=None):
    env = dict(os.environ, PYTHONPATH=str(ROOT/'src'), HHU_AVATAR_DATA_ROOT=str(tmp_path/'assets'),
        MEMORY_DB_PATH=str(tmp_path/'memory.db'), LLM_API_KEY='', EMBEDDING_MODEL='')
    env.update(extra_env or {})
    return subprocess.run([sys.executable, '-B', *(['-S'] if no_site else []), '-m', 'avatar', *args],
        cwd=tmp_path, env=env, input=input, text=True, capture_output=True, timeout=15)


def test_version_works_outside_checkout_without_site_packages(tmp_path):
    result = invoke(tmp_path, '--version', no_site=True)
    assert result.returncode == 0 and result.stdout.strip() == __version__


def test_doctor_does_not_expose_credentials_or_make_model_request(tmp_path):
    result = invoke(tmp_path, 'doctor', extra_env={'LLM_API_KEY': 'fake-test-only-secret',
        'LLM_BASE_URL': 'http://127.0.0.1:1/v1'})
    assert result.returncode == 0 and not (tmp_path/'memory.db').exists()
    assert 'fake-test-only-secret' not in result.stdout+result.stderr
    report = json.loads(result.stdout)
    assert report['llm']['configured'] and report['llm']['mode'] == 'configured_not_connectivity_verified'
    assert not report['external_delivery']['sms'] and not report['asr']['enabled_by_default']


def test_text_exit_closes_real_database_without_model_configuration(tmp_path):
    result = invoke(tmp_path, 'text', input='quit\n')
    assert result.returncode == 0, result.stderr
    assert (tmp_path/'memory.db').is_file() and '再见' in result.stdout


def test_standard_text_entry_uses_release_contract_and_recovers_actual_sql_across_processes(tmp_path):
    first=invoke(tmp_path,'text',input='我叫陆遥。\n原样输出这句话：“发布正文。”\nquit\n')
    assert first.returncode==0,first.stderr
    second=invoke(tmp_path,'text',input='我叫什么名字？\nquit\n')
    assert second.returncode==0 and '目前记录你使用的名字是陆遥' in second.stdout
    with sqlite3.connect(tmp_path/'memory.db') as conn:
        values=[json.loads(r[0]) for r in conn.execute('SELECT result_json FROM memory_chat_results ORDER BY message_id')]
        assert [r['generation_mode'] for r in values]==['rules_profile_source','rules_writing_artifact','rules_profile_source']
        assert all('capability_contract' in r for r in values)
        assert conn.execute('SELECT COUNT(*) FROM memory_role_state').fetchone()[0]==1


def test_web_arguments_are_validated_by_existing_parser(tmp_path):
    result = invoke(tmp_path, 'web', '--port', '65536')
    assert result.returncode == 2 and '--port' in result.stderr
    assert not (tmp_path/'memory.db').exists()


def test_ui_readiness_rejects_missing_or_external_entry_asset(tmp_path):
    root = tmp_path/'ui'
    (root/'assets').mkdir(parents=True)
    (root/'index.html').write_text('<html><script src="/assets/app.js"></script></html>')
    assert not check_frontend(root)['available']
    outside = tmp_path/'outside.js'
    outside.write_text('console.log("outside")')
    (root/'assets/app.js').symlink_to(outside)
    assert not check_frontend(root)['available']
    (root/'assets/app.js').unlink()
    (root/'assets/app.js').write_text('console.log("inside")')
    assert check_frontend(root)['available']
