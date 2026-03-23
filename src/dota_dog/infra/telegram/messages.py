from __future__ import annotations

import re

TELEGRAM_TEXT_LIMIT = 4096

_HTML_TOKEN_RE = re.compile(r"<[^>]+>|[^<]+")
_TAG_NAME_RE = re.compile(r"</?\s*([a-zA-Z0-9]+)")


def split_html_message(text: str, *, max_length: int = TELEGRAM_TEXT_LIMIT) -> list[str]:
    if max_length < 1:
        msg = "max_length must be positive"
        raise ValueError(msg)

    chunks: list[str] = []
    current_parts: list[str] = []
    current_length = 0
    open_tags: list[tuple[str, str]] = []

    def flush_chunk() -> None:
        nonlocal current_parts, current_length
        closing_tags = [f"</{name}>" for name, _ in reversed(open_tags)]
        chunk = "".join(current_parts + closing_tags)
        if chunk:
            chunks.append(chunk)
        current_parts = [opening_tag for _, opening_tag in open_tags]
        current_length = 0

    for token in _HTML_TOKEN_RE.findall(text):
        if token.startswith("<"):
            current_parts.append(token)
            _update_open_tags(open_tags, token)
            continue

        remainder = token
        while remainder:
            available = max_length - current_length
            if available <= 0:
                flush_chunk()
                available = max_length

            if len(remainder) <= available:
                current_parts.append(remainder)
                current_length += len(remainder)
                break

            split_at = _best_split_index(remainder, available)
            current_parts.append(remainder[:split_at])
            current_length += len(remainder[:split_at])
            flush_chunk()
            remainder = remainder[split_at:]

    closing_tags = [f"</{name}>" for name, _ in reversed(open_tags)]
    tail = "".join(current_parts + closing_tags)
    if tail:
        chunks.append(tail)
    return chunks


def split_html_sections(
    header: str,
    sections: list[str],
    *,
    max_length: int = TELEGRAM_TEXT_LIMIT,
) -> list[str]:
    if max_length < 1:
        msg = "max_length must be positive"
        raise ValueError(msg)

    header_length = html_text_length(header)
    if header_length > max_length:
        return split_html_message(header, max_length=max_length)
    if not sections:
        return [header]

    chunks: list[str] = []
    current_sections: list[str] = []
    current_length = header_length

    for section in sections:
        section_length = html_text_length(section)
        section_with_separator = 2 + section_length
        if current_length + section_with_separator <= max_length:
            current_sections.append(section)
            current_length += section_with_separator
            continue

        if current_sections:
            chunks.append(_render_html_sections(header, current_sections))
            current_sections = []
            current_length = header_length

        if header_length + section_with_separator <= max_length:
            current_sections.append(section)
            current_length = header_length + section_with_separator
            continue

        available = max_length - header_length - 2
        if available < 1:
            chunks.extend(split_html_message(section, max_length=max_length))
            continue
        chunks.extend(
            f"{header}\n\n{part}" for part in split_html_message(section, max_length=available)
        )

    if current_sections:
        chunks.append(_render_html_sections(header, current_sections))
    return chunks


def html_text_length(text: str) -> int:
    return sum(len(token) for token in _HTML_TOKEN_RE.findall(text) if not token.startswith("<"))


def _update_open_tags(open_tags: list[tuple[str, str]], token: str) -> None:
    if token.startswith("<!--") or token.rstrip().endswith("/>"):
        return

    tag_name = _tag_name(token)
    if tag_name is None:
        return

    if token.startswith("</"):
        for index in range(len(open_tags) - 1, -1, -1):
            if open_tags[index][0] == tag_name:
                del open_tags[index]
                return
        return

    open_tags.append((tag_name, token))


def _tag_name(token: str) -> str | None:
    match = _TAG_NAME_RE.match(token)
    if match is None:
        return None
    return match.group(1).lower()


def _best_split_index(text: str, max_length: int) -> int:
    prefix = text[:max_length]
    for separator in ("\n\n", "\n", " "):
        index = prefix.rfind(separator)
        if index > 0:
            return index + len(separator)
    return max_length


def _render_html_sections(header: str, sections: list[str]) -> str:
    return f"{header}\n\n" + "\n\n".join(sections)
