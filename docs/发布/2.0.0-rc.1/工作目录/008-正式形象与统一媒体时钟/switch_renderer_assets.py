"""Replace only two ignored pointers; retain original trees and identities."""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path('/data/Users/zrh/repo/hhu-ai-avatar')
ASSETS=Path('/data/Users/zrh/data/hhu-ai-avatar')
HERE=Path(__file__).resolve().parent


def tree(path):
    return {str(p.relative_to(path)):(dict(symlink=os.readlink(p)) if p.is_symlink()
        else dict(sha256=sha256(p.read_bytes()).hexdigest())) for p in sorted(path.rglob('*'))
        if p.is_symlink() or p.is_file()}


def main():
    assert os.path.ismount('/data')
    raw=ASSETS/'artifacts/release/renderer-asset-switch-v1';raw.mkdir(parents=True,exist_ok=False)
    pairs=[('frontend/node_modules','frontend/node_modules','frontend/release-renderer-dev-v1/node_modules'),
        ('frontend/dist','frontend/dist','frontend/renderer-development-dist-v1')]
    before={};changes=[]
    for name,old,new in pairs:
        link,previous,target=ROOT/name,ASSETS/old,ASSETS/new
        assert link.is_symlink() and link.resolve()==previous and previous.is_dir()
        if name=='frontend/dist':target.mkdir(parents=True,exist_ok=False)
        assert target.is_dir()
        before[old]=tree(previous)
        changes.append(dict(checkout=name,old_link_text=os.readlink(link),old_target=str(previous),new_target=str(target)))
    (raw/'original-trees.json').write_text(json.dumps(before,ensure_ascii=False,indent=2)+'\n')
    for name,old,new in pairs:
        link,target=ROOT/name,ASSETS/new
        temporary=link.with_name(link.name+'.release-switch-v1')
        assert not os.path.lexists(temporary)
        temporary.symlink_to(os.path.relpath(target,link.parent),target_is_directory=True)
        os.replace(temporary,link)
    assert all(tree(ASSETS/old)==before[old] for _,old,_ in pairs)
    sys.path.insert(0,str(ROOT/'scripts'))
    from link_project_assets import check_links
    aliases=check_links();assert len(aliases)==9 and all(x['valid'] for x in aliases)
    proof=dict(source_ref=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),changes=changes,
        old_tree_entries=sum(len(x) for x in before.values()),old_trees_preserved=True,aliases=aliases,
        raw_manifest=str(raw/'original-trees.json'),raw_manifest_sha256=sha256((raw/'original-trees.json').read_bytes()).hexdigest(),
        scope='only two checkout pointers switched; original data trees retained byte-for-byte; no renderer approval')
    with (HERE/'renderer-asset-switch-v1.json').open('x') as stream:json.dump(proof,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print('Both original trees preserved;',proof['old_tree_entries'],'entries; all 9 current aliases valid')


if __name__=='__main__':main()
