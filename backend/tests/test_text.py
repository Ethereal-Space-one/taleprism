import pytest
from hypothesis import given
from hypothesis import strategies as st

from storygal.text import (
    assert_span_coverage,
    build_units,
    decode_source,
    split_spans,
    visible_text,
)

TEXT = st.text(
    alphabet=st.characters(blacklist_categories=("Cs", "Cc", "Zl", "Zp"))
    | st.sampled_from("\r\n\t"),
    max_size=3000,
)


@given(TEXT)
def test_every_utf8_byte_is_covered_and_pages_preserve_visible_text(text):
    raw = text.encode("utf-8")
    spans = split_spans(raw)
    assert_span_coverage(raw, spans)
    units = build_units(raw)
    assert "".join(u.text for u in units) == visible_text(text)
    assert all(raw[u.byte_start : u.byte_end].decode("utf-8") == u.text for u in units)
    assert all(len(u.text) <= 64 for u in units)


@pytest.mark.parametrize("encoding", ["utf-8", "gb18030"])
def test_encoding_roundtrip(encoding):
    raw = "　　宝玉道：“你好，世界。”\r\n emoji 😀".encode(encoding)
    selected, canonical = decode_source(raw, encoding)
    assert canonical.decode("utf-8").encode(selected) == raw


def test_bom_crlf_whitespace_and_unknown_speaker():
    raw = "\ufeff　　周瑜曰：「只欠東風。」\r\n\r\n　　孔明微笑。".encode()
    assert b"".join(s.text.encode() for s in split_spans(raw)) == raw
    units = build_units(raw)
    assert [u.text for u in units] == ["周瑜曰：「只欠東風。」", "孔明微笑。"]
    assert all(u.speaker_id is None for u in units)
    assert "dialogue" in {s.kind for s in split_spans(raw)}


def test_bad_or_empty_text_and_limits():
    for raw in [b"", b"\x00abc", b" \n\t", "字".encode() * 30001]:
        with pytest.raises(ValueError):
            decode_source(raw)


def test_coverage_rejects_gap_and_changed_content():
    raw = "一二三".encode()
    spans = split_spans(raw)
    spans[0].byte_start = 1
    with pytest.raises(ValueError):
        assert_span_coverage(raw, spans)
