"""Optional metasearch adapter. No results and provider errors remain explicit."""
from __future__ import annotations

import time
from .web_fetch import public_url, system_proxy


def validate_query(query: str) -> str:
    if not isinstance(query, str) or not query.strip() or len(query) > 500 or any(ord(c) < 32 for c in query):
        raise ValueError('搜索词须为1～500字符的单行文本。')
    return query.strip()


def normalize_results(rows, limit: int) -> list[dict]:
    if type(limit) is not int or not 1 <= limit <= 5:
        raise ValueError('搜索结果数量须为1～5。')
    results, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            url = public_url(row.get('href', row.get('url', '')))
        except (ValueError, TypeError, UnicodeError):
            continue
        if url in seen:
            continue
        seen.add(url)
        results.append({'title': str(row.get('title', '')).strip()[:200], 'url': url,
                        'snippet': str(row.get('body', row.get('snippet', ''))).strip()[:350]})
        if len(results) >= limit:
            break
    return results


def web_search(query: str, limit: int = 3) -> dict:
    query = validate_query(query)
    if type(limit) is not int or not 1 <= limit <= 5:
        raise ValueError('搜索结果数量须为1～5。')
    try:
        from ddgs import DDGS
    except ImportError:
        raise RuntimeError('请先安装 requirements-web.txt 中的联网扩展。') from None
    started, error_name = time.monotonic(), 'NoResults'
    for backend in ('auto', 'duckduckgo'):
        if backend != 'auto' and time.monotonic() - started > 20:
            break
        try:
            rows = DDGS(proxy=system_proxy(), timeout=8 if backend == 'auto' else 6).text(
                query, max_results=limit, backend=backend, region='us-en', safesearch='moderate')
            results = normalize_results(rows, limit)
            if results:
                return dict(query=query, results=results, provider='ddgs', fetched_at=time.time(), untrusted=True)
        except Exception as exc:
            error_name = type(exc).__name__
    raise RuntimeError(f'搜索未成功（{error_name}）。可能是网络超时、限流或验证码，请稍后重试。') from None
