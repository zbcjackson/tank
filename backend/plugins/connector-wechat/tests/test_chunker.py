"""Unit tests for message chunker."""

from __future__ import annotations

from connector_wechat.chunker import chunk_message


def test_short_text_unchanged() -> None:
    text = "Hello, world!"
    assert chunk_message(text) == [text]


def test_empty_text() -> None:
    assert chunk_message("") == []


def test_exact_limit() -> None:
    text = "x" * 4000
    assert chunk_message(text, 4000) == [text]


def test_split_at_paragraph() -> None:
    para1 = "a" * 100
    para2 = "b" * 100
    text = f"{para1}\n\n{para2}"
    # With a limit that forces a split
    chunks = chunk_message(text, 110)
    assert len(chunks) == 2
    assert chunks[0] == para1
    assert chunks[1] == para2


def test_split_at_newline() -> None:
    line1 = "a" * 80
    line2 = "b" * 80
    text = f"{line1}\n{line2}"
    chunks = chunk_message(text, 90)
    assert len(chunks) == 2
    assert chunks[0] == line1
    assert chunks[1] == line2


def test_hard_cut_no_boundaries() -> None:
    text = "x" * 200
    chunks = chunk_message(text, 100)
    assert len(chunks) == 2
    assert chunks[0] == "x" * 100
    assert chunks[1] == "x" * 100


def test_code_fence_preserved() -> None:
    code = "```python\nprint('hello')\n```"
    text = f"Before\n\n{code}\n\nAfter some more text that is long"
    # Should prefer splitting between the sections
    chunks = chunk_message(text, 50)
    # Code fence should not be split mid-block
    found_fence_in_chunk = False
    for chunk in chunks:
        if "```python" in chunk and "```" in chunk[chunk.index("```python") + 3:]:
            found_fence_in_chunk = True
    assert found_fence_in_chunk


def test_multiple_chunks() -> None:
    text = "\n\n".join([f"Paragraph {i}: " + "x" * 50 for i in range(10)])
    chunks = chunk_message(text, 100)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 100


def test_single_char_limit() -> None:
    # Edge case: very small limit
    text = "abc"
    chunks = chunk_message(text, 1)
    assert len(chunks) == 3


def test_unicode_text() -> None:
    text = "你好世界" * 1000  # 4000 chars
    chunks = chunk_message(text, 4000)
    assert len(chunks) == 1

    chunks = chunk_message(text, 2000)
    assert len(chunks) == 2
    assert "".join(chunks) == text
