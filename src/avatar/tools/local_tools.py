"""Local document access is opt-in and read-only."""
import os
from pathlib import Path


def search_documents(query: str, limit: int = 5) -> dict:
    if not isinstance(query, str) or not query.strip() or len(query) > 200:
        raise ValueError('请输入1～200字的查询。')
    if type(limit) is not int or not 1 <= limit <= 10:
        raise ValueError('limit必须在1～10之间。')
    roots = [Path(p).resolve() for p in os.getenv('AVATAR_DOCUMENT_ROOTS', '').split(os.pathsep) if p.strip()]
    if not roots:
        raise ValueError('请先配置 AVATAR_DOCUMENT_ROOTS 白名单目录。')
    rows, scanned = [], 0
    for index, root in enumerate(roots):
        if not root.is_dir():
            continue
        for directory, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = [d for d in dirs if not d.startswith('.') and not (Path(directory)/d).is_symlink() and not (Path(directory)/d).is_junction()]
            for name in files:
                scanned += 1
                if scanned > 2000:
                    return {'results': rows, 'truncated': True, 'untrusted': True}
                path = Path(directory)/name
                if name.startswith('.') or path.suffix.lower() not in ('.md', '.txt') or path.is_symlink():
                    continue
                try:
                    resolved = path.resolve()
                    if not resolved.is_relative_to(root) or resolved.stat().st_size > 262144:
                        continue
                    text = resolved.read_text(encoding='utf-8')
                except (OSError, UnicodeError):
                    continue
                pos = text.casefold().find(query.strip().casefold())
                if pos >= 0:
                    rows.append({'root': index, 'path': str(path.relative_to(root)), 'line': text[:pos].count('\n')+1, 'excerpt': text[max(0,pos-100):pos+700]})
                    if len(rows) >= limit:
                        return {'results': rows, 'truncated': True, 'untrusted': True}
    return {'results': rows, 'truncated': False, 'untrusted': True}
