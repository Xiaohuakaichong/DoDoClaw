import json

from dodoclaw.gsi.recorder import GsiRecorder


def test_records_per_match_and_strips_auth(tmp_path):
    rec = GsiRecorder(tmp_path)
    rec.record({"auth": {"token": "x"}, "map": {"matchid": "1"}, "draft": {}})
    rec.record({"map": {"matchid": "1"}})
    rec.record({"map": {"matchid": "2"}})
    rec.close()
    files = sorted(tmp_path.glob("*.jsonl"))
    assert len(files) == 2
    lines = [json.loads(x) for x in files[0].read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 2
    assert "auth" not in lines[0]["p"]
