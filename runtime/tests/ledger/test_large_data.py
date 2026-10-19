import json
import pytest
from heteroes.product.files import write_json
from heteroes.product.storage import checked_directory,data_root
from heteroes.product.recovery import capture_point,verify_point
from test_recovery_points import sample
from test_product_gateway import manager,config


def test_external_checkpoint_is_self_contained_with_ledger_in_original_root(tmp_path):
    root,sha=sample(tmp_path)
    large=tmp_path/'secondary/run';large.mkdir(parents=True)
    (root/'weights').rename(large/'weights')
    write_json(root/'large-data.json',{'directory':str(large)})
    point=capture_point(root,{'generation':0,'child_sha256':sha,'parent_sha256':sha},{},{'interval':1,'retain':3},final=True)
    assert point.parent==large/'recovery-points'
    assert (root/'ledger.sqlite').is_file() and not (root/'weights').exists()
    assert verify_point(point)['childWeightsSha256']==sha
    assert data_root(root)==large


def test_unavailable_volume_blocks_new_run_before_fallback_weights(manager,tmp_path):
    manager.config.update(largeDataDirectory=str(tmp_path/'missing-volume/data'),
        storageVolumeUUID='00000000-0000-0000-0000-000000000000')
    with pytest.raises(ValueError,match='unavailable'):manager.submit(config())
    assert not (tmp_path/'missing-volume').exists()
    assert not manager.directory('a'*32).exists()


def test_large_data_identity_cannot_point_at_unauthorized_or_relative_paths(tmp_path):
    for path in ['relative/cache','/mnt/sekai/model']:
        with pytest.raises(ValueError):checked_directory(path)
    link=tmp_path/'redirect';link.symlink_to('/mnt/sekai')
    with pytest.raises(ValueError):checked_directory(link)
