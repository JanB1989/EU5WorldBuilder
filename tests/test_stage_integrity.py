import json
import pytest
from historical_agriculture.pipeline import check_prerequisites
from historical_agriculture.provenance import fingerprint,digest


def test_outputs_and_configuration_cannot_silently_recertify(tmp_path):
    config=tmp_path/'configs/reconstruction.json';config.parent.mkdir();config.write_text('{}')
    raw=tmp_path/'raw';raw.mkdir();out=tmp_path/'artifacts';out.mkdir()
    artifact=out/'input_audit.json';artifact.write_text('{}')
    fp,_=fingerprint(config,raw)
    (out/'audit.stamp.json').write_text(json.dumps({'fingerprint':fp,'output_hashes':{'input_audit.json':digest(artifact)}}))
    check_prerequisites('evidence',config,raw,out)
    artifact.write_text('{"tampered":true}')
    with pytest.raises(ValueError,match='output changed'):
        check_prerequisites('evidence',config,raw,out)
    artifact.write_text('{}');config.write_text('{"changed":true}')
    with pytest.raises(ValueError,match='Stale stage'):
        check_prerequisites('evidence',config,raw,out)
