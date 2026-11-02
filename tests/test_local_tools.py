import pytest
from avatar.tools.local_tools import search_documents

def test_document_search_restricts_files(tmp_path, monkeypatch):
    (tmp_path / 'lesson.md').write_text('河海大学水文学课程', encoding='utf-8')
    (tmp_path / '.env').write_text('河海大学秘密', encoding='utf-8')
    monkeypatch.setenv('AVATAR_DOCUMENT_ROOTS', str(tmp_path))
    rows = search_documents('水文学')['results']
    assert rows[0]['path'] == 'lesson.md'
    assert search_documents('秘密')['results'] == []

def test_documents_disabled_without_roots(monkeypatch):
    monkeypatch.delenv('AVATAR_DOCUMENT_ROOTS', raising=False)
    with pytest.raises(ValueError):
        search_documents('课程')
