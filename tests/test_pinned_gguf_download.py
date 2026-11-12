"""No Internet/model allocation: immutable asset checks and exclusive publish."""
from hashlib import sha256
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from download_pinned_gguf import metadata,publish_verified


def test_metadata_identity_is_checked_before_json_parse(tmp_path):
    path=tmp_path/'model.json';path.write_text('{malformed')
    with pytest.raises(ValueError,match='identity changed'):metadata(path,'wrong')


@pytest.mark.parametrize('size',[True,-1,0])
def test_invalid_size_is_not_a_valid_asset(tmp_path,size):
    data={'repo_id':'Qwen/Fixture','revision':'a'*40,'path':'fixture.gguf','size':size,'lfs':{'oid':'b'*64,'size':size}}
    path=tmp_path/'model.json';path.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='Invalid pinned'):metadata(path,sha256(path.read_bytes()).hexdigest())


def test_verified_publication_preserves_bytes_and_removes_only_owned_partial(tmp_path):
    partial=tmp_path/'owned.part';partial.write_bytes(b'fixture model');target=tmp_path/'model.gguf';expected=sha256(partial.read_bytes()).hexdigest()
    assert publish_verified(partial,target,13,expected)==expected
    assert target.read_bytes()==b'fixture model' and not partial.exists()


@pytest.mark.parametrize('failure',['size','sha'])
def test_bad_asset_never_publishes_and_retains_partial(tmp_path,failure):
    partial=tmp_path/'owned.part';partial.write_bytes(b'fixture');target=tmp_path/'model.gguf'
    with pytest.raises(ValueError):publish_verified(partial,target,7 if failure=='sha' else 8,'a'*64)
    assert not target.exists() and partial.read_bytes()==b'fixture'


def test_existing_target_is_never_overwritten(tmp_path):
    partial=tmp_path/'owned.part';partial.write_bytes(b'fixture');target=tmp_path/'model.gguf';target.write_bytes(b'preexisting user model')
    with pytest.raises(FileExistsError):publish_verified(partial,target,7,sha256(b'fixture').hexdigest())
    assert target.read_bytes()==b'preexisting user model' and partial.exists()
