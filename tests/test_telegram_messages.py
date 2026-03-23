from __future__ import annotations

import re

from dota_dog.infra.telegram.messages import split_html_message, split_html_sections

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _plain_text(value: str) -> str:
    return _HTML_TAG_RE.sub("", value)


def test_split_html_message_keeps_html_balanced() -> None:
    text = (
        "<b>Last matches</b>\n\n"
        '<b>Alpha</b> · <a href="https://example.com/a">profile</a>\n'
        + ("A" * 32)
        + "\n"
        + '<b>Beta</b> · <a href="https://example.com/b">profile</a>\n'
        + ("B" * 32)
    )

    chunks = split_html_message(text, max_length=40)

    assert len(chunks) > 1
    assert "".join(_plain_text(chunk) for chunk in chunks) == _plain_text(text)
    assert all(len(_plain_text(chunk)) <= 40 for chunk in chunks)
    assert all(chunk.count("<b>") == chunk.count("</b>") for chunk in chunks)
    assert all(chunk.count("<a ") == chunk.count("</a>") for chunk in chunks)


def test_split_html_sections_keeps_sections_whole() -> None:
    header = "<b>Last matches</b>"
    sections = [
        '<b>Alpha</b>\n<a href="https://example.com/1">Dotabuff</a>\n' + ("A" * 18),
        '<b>Beta</b>\n<a href="https://example.com/2">Dotabuff</a>\n' + ("B" * 18),
        '<b>Gamma</b>\n<a href="https://example.com/3">Dotabuff</a>\n' + ("C" * 18),
    ]

    chunks = split_html_sections(header, sections, max_length=50)

    assert len(chunks) == 3
    assert all(chunk.startswith(f"{header}\n\n") for chunk in chunks)
    assert sections[0] in chunks[0]
    assert sections[1] in chunks[1]
    assert sections[2] in chunks[2]
