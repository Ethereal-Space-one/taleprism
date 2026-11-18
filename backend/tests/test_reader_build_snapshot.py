import json

import pytest
from reader_build_fixture import fake_reader_build

from storygal.reader_export import read_runtime


def test_unfinished_build_is_never_a_portable_reader(tmp_path):
    fake_reader_build(tmp_path)
    folder = tmp_path / "frontend/dist/reader"
    pair = read_runtime(folder)
    for fragment in (b"", pair["reader.js"][:5], b"other release"):
        (folder / "reader.js").write_bytes(fragment)
        with pytest.raises(ValueError, match="重新导出"):
            read_runtime(folder)
    (folder / "reader.js").write_bytes(pair["reader.js"])
    assert read_runtime(folder) == pair
    (folder / "runtime-checksums.json").write_text(json.dumps({"reader.js": "abc"}))
    with pytest.raises(ValueError, match="重新导出"):
        read_runtime(folder)
