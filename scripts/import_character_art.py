"""Import attributed community previews into ignored local data; never installs code."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT.parent / 'references/ai-girls'
DEST = ROOT / 'data/characters'


def main():
    catalog = json.loads((REFERENCE / 'catalog.json').read_text())
    cards = json.loads((ROOT / 'src/avatar/characters/catalog.json').read_text())
    DEST.mkdir(parents=True, exist_ok=True, mode=0o700)
    assets = DEST / 'art'; assets.mkdir(exist_ok=True, mode=0o700)
    def download(card):
        candidates = [a for a in catalog['assets'] if a['character_id'] == card['id']
                      and a.get('asset_type') == 'original_portrait' and a.get('preview')
                      and a.get('source_id') not in ('aigengtu-refs','doubao-official')]
        if not candidates:return card['id'], None
        a = candidates[0]
        preview = a['preview']
        if not preview.startswith('previews/') or '..' in preview:raise ValueError('Invalid preview')
        url = 'https://raw.githubusercontent.com/shuaizenge/ai-girls/main/' + preview
        cached=assets/(card['id']+'.jpg')
        if cached.is_file():
            raw=cached.read_bytes()
        else:
            try:
                with urllib.request.urlopen(url,timeout=30) as response:raw=response.read(1048577)
            except urllib.error.HTTPError as error:
                if error.code==404:return card['id'], None
                raise
        if len(raw)>1048576 or not raw.startswith(b'\xff\xd8'):raise ValueError('Invalid portrait')
        path=assets/(card['id']+'.jpg');path.write_bytes(raw);path.chmod(0o600)
        source=catalog['sources'][a['source_id']]
        return card['id'], {'file':card['id']+'.jpg','sha256':hashlib.sha256(raw).hexdigest(),
            'creators':a.get('creators',[source.get('author','来源作者')]), 'source_url':source['page_url'],
            'archive_url':'https://github.com/shuaizenge/ai-girls', 'license':a.get('license',{}),
            'asset_id':a['id'], 'preview_url':url}
    with ThreadPoolExecutor(max_workers=4) as pool:result=dict(pool.map(download,cards))
    (DEST/'art-index.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    (DEST/'art-index.json').chmod(0o600)
    shutil.copy2(REFERENCE/'NOTICE.md',DEST/'ART-NOTICE.md')
    print('Imported portraits:',sum(v is not None for v in result.values()))


if __name__=='__main__':main()
