import pytest
from avatar.tools.web_search import normalize_results, validate_query


def test_results_are_bounded_deduplicated_and_links_are_public():
    rows = [{'title': ' Official ', 'href': 'https://example.com/doc', 'body': 'x' * 1000},
            {'title': 'duplicate', 'href': 'https://example.com/doc', 'body': 'duplicate'},
            {'title': 'private', 'href': 'http://127.0.0.1/', 'body': 'secret'},
            {'title': 'script', 'href': 'javascript:alert(1)', 'body': ''}]
    result = normalize_results(rows, 3)
    assert len(result) == 1 and result[0]['title'] == 'Official'
    assert len(result[0]['snippet']) <= 350


@pytest.mark.parametrize('query', ['', ' ', 'x' * 501, None, True])
def test_invalid_query_is_not_sent_to_search_engine(query):
    with pytest.raises(ValueError):
        validate_query(query)


def test_search_retries_once_after_transient_provider_failure(monkeypatch):
    import avatar.tools.web_search as search
    ddgs = pytest.importorskip('ddgs')
    attempts = []
    class Engine:
        def __init__(self, **kwargs):
            pass
        def text(self, query, **kwargs):
            attempts.append(query)
            if len(attempts) == 1:
                raise TimeoutError('provider timeout')
            return [{'title': 'Docs', 'href': 'https://example.com/docs', 'body': 'retrieved snippet'}]
    monkeypatch.setattr(ddgs, 'DDGS', Engine)
    assert search.web_search('MCP')['results'][0]['url'] == 'https://example.com/docs'
    assert attempts == ['MCP', 'MCP']
