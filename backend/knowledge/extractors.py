"""Turn uploaded files into a flat list of text blocks (headings and paragraphs).

Every format ends up in the same shape, a list of Block, so chunking, citations and
the text preview do not care where the text came from. Headings are kept as their
own blocks with a level, because heading aware chunks keep a policy's section
together and give citations a meaningful location ("Returns > Refund window").

Failures that a user can act on raise ExtractionError with a friendly message, which
ingestion stores on the document as is.
"""

from __future__ import annotations

import io
import logging
import re
import unicodedata
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from html.parser import HTMLParser

logger = logging.getLogger(__name__)

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MARKDOWN = "text/markdown"
TEXT = "text/plain"
HTML = "text/html"

BLOCK_SEPARATOR = "\n\n"


class ExtractionError(Exception):
    """Raised with a message that is safe and useful to show to the uploader."""


@dataclass(frozen=True)
class Block:
    text: str
    heading_level: int = 0  # 1 to 6 for headings, 0 for body text
    page_number: int | None = None

    @property
    def is_heading(self) -> bool:
        return self.heading_level > 0


@dataclass(frozen=True)
class Extraction:
    blocks: list[Block]
    page_count: int | None = None

    @property
    def text(self) -> str:
        return join_blocks(self.blocks)[0]


def join_blocks(blocks: Iterable[Block]) -> tuple[str, list[int]]:
    """The document's full text and the offset of every block inside it.

    Chunk offsets index into this exact string (stored as Document.extracted_text), so
    the preview pane can highlight a cited passage.
    """
    parts: list[str] = []
    offsets: list[int] = []
    position = 0
    for block in blocks:
        if parts:
            position += len(BLOCK_SEPARATOR)
        offsets.append(position)
        parts.append(block.text)
        position += len(block.text)
    return BLOCK_SEPARATOR.join(parts), offsets


# Text normalisation

_CONTROL = {chr(c) for c in range(32) if chr(c) not in "\n\t"} | {"\x7f"}
_SPACES = re.compile(r"[ \t\f\v\u00a0\u2000-\u200b\u202f\u205f\u3000]+")
# "refund-\nable" is one word split by a line break; only lower case continuations are
# joined, so "Wi-\nFi" style compounds keep their hyphen more often than not.
_HYPHEN_BREAK = re.compile(r"([a-z])-\n([a-z])")
_LIST_MARKER = re.compile(r"^(?:[-*+\u2022\u25aa\u25e6]|\d{1,3}[.)])\s+")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    text = "".join(ch for ch in text if ch not in _CONTROL)
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _collapse(text: str) -> str:
    return _SPACES.sub(" ", text.replace("\n", " ")).strip()


def _is_table_row(line: str) -> bool:
    return " | " in line


def _join_soft_wraps(lines: list[str]) -> str:
    """Join lines wrapped for width, but keep list items and table rows on their own
    lines."""
    merged: list[str] = []
    for line in lines:
        if not line:
            continue
        separate = _LIST_MARKER.match(line) or _is_table_row(line) or (merged and _is_table_row(merged[-1]))
        if merged and not separate:
            merged[-1] = f"{merged[-1]} {line}"
        else:
            merged.append(line)
    return "\n".join(merged)


def looks_like_heading(line: str, *, standalone: bool = False) -> bool:
    """Guess headings for formats without heading markup (PDF and plain text).

    Any short line in title case or capitals without sentence punctuation qualifies.
    A line that already stands alone as its own paragraph (plain text keeps blank
    lines) may also be in sentence case ("Password resets"). Missing a heading only
    costs a less specific location; inventing one would split a paragraph, so inside
    running text the rule errs towards "not a heading".
    """
    words = line.split()
    if not 1 <= len(words) <= 10 or len(line) > 80:
        return False
    if line[-1] in ".,;:!?" or _LIST_MARKER.match(line) or _is_table_row(line):
        return False
    if not line[0].isalpha() or not line[0].isupper():
        return False
    letters = [ch for ch in line if ch.isalpha()]
    if len(letters) < 3:
        return False
    if line.isupper() or (standalone and len(words) <= 8):
        return True
    significant = [w for w in words if len(w) > 3 and w[0].isalpha()]
    if not significant:
        return len(words) <= 3
    capitalised = sum(1 for w in significant if w[0].isupper())
    return capitalised / len(significant) >= 0.6


def _paragraph_blocks(text: str, page_number: int | None = None) -> list[Block]:
    blocks: list[Block] = []
    for raw in re.split(r"\n\s*\n", normalize_text(text)):
        lines = [line for line in raw.split("\n") if line]
        pending: list[str] = []
        for index, line in enumerate(lines):
            # PDFs lose the blank lines between paragraphs, so any line may be a
            # heading there. In plain text a heading is a paragraph of its own, or the
            # first line of one when written in capitals.
            if page_number is not None:
                heading = looks_like_heading(line)
            elif len(lines) == 1:
                heading = looks_like_heading(line, standalone=True)
            else:
                heading = index == 0 and line.isupper() and looks_like_heading(line)
            if heading:
                if pending:
                    blocks.append(Block(_join_soft_wraps(pending), page_number=page_number))
                    pending = []
                level = 1 if line.isupper() else 2
                blocks.append(Block(line, heading_level=level, page_number=page_number))
            else:
                pending.append(line)
        if pending:
            blocks.append(Block(_join_soft_wraps(pending), page_number=page_number))
    return blocks


# PDF


def extract_pdf(data: bytes) -> Extraction:
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise ExtractionError("This PDF is password protected. Remove the password and upload it again.")
        pages = [page.extract_text() or "" for page in reader.pages]
    except ExtractionError:
        raise
    except (PyPdfError, ValueError, KeyError, TypeError, NotImplementedError) as exc:
        logger.info("Unreadable PDF: %s", exc)
        raise ExtractionError("This PDF could not be read. It may be damaged.") from exc

    if not any(page.strip() for page in pages):
        raise ExtractionError("This PDF has no extractable text. It may be a scanned image.")
    blocks: list[Block] = []
    for number, page_text in enumerate(pages, start=1):
        blocks.extend(_paragraph_blocks(page_text, page_number=number))
    return Extraction(blocks=blocks, page_count=len(pages))


# DOCX


def _docx_heading_level(style_name: str) -> int:
    name = style_name.strip().lower()
    if name == "title":
        return 1
    match = re.fullmatch(r"heading\s*([1-6])", name)
    return int(match.group(1)) if match else 0


def extract_docx(data: bytes) -> Extraction:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    try:
        document = docx.Document(io.BytesIO(data))
        items = list(document.iter_inner_content())
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        logger.info("Unreadable DOCX: %s", exc)
        raise ExtractionError("This Word document could not be read. It may be damaged.") from exc

    blocks: list[Block] = []
    for item in items:
        if isinstance(item, Paragraph):
            text = _collapse(item.text)
            if not text:
                continue
            style = item.style.name if item.style is not None and item.style.name else ""
            level = _docx_heading_level(style)
            if not level and style.lower().startswith("list"):
                text = f"- {text}"
            blocks.append(Block(text, heading_level=level))
        elif isinstance(item, Table):
            rows: list[str] = []
            for row in item.rows:
                cells: list[str] = []
                for cell in row.cells:
                    value = _collapse(cell.text)
                    # Merged cells repeat the same cell object once per grid column.
                    if value and (not cells or cells[-1] != value):
                        cells.append(value)
                if cells:
                    rows.append(" | ".join(cells))
            if rows:
                blocks.append(Block("\n".join(rows)))
    return Extraction(blocks=blocks)


# Markdown

_FRONT_MATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
_ATX = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_SETEXT = re.compile(r"^(=+|-+)\s*$")
_RULE = re.compile(r"^(?:\*\s*){3,}$|^(?:-\s*){3,}$|^(?:_\s*){3,}$")
_BULLET = re.compile(r"^[*+]\s+")
_TABLE_SEPARATOR = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$")
_INLINE_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"!\[([^\]]*)\]\([^)]*\)"), r"\1"),
    (re.compile(r"\[([^\]]+)\]\([^)]*\)"), r"\1"),
    (re.compile(r"<[^>\n]+>"), ""),
    (re.compile(r"(\*\*|__)(.+?)\1"), r"\2"),
    (re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])"), r"\1"),
    (re.compile(r"`([^`]*)`"), r"\1"),
]


def _clean_markdown_inline(line: str) -> str:
    for pattern, replacement in _INLINE_RULES:
        line = pattern.sub(replacement, line)
    if line.startswith("|") or line.endswith("|"):
        line = " | ".join(cell.strip() for cell in line.strip().strip("|").split("|"))
    return line.strip()


def extract_markdown(text: str) -> Extraction:
    text = _FRONT_MATTER.sub("", normalize_text(text) + "\n", count=1)
    blocks: list[Block] = []
    paragraph: list[str] = []
    in_fence = False

    def flush() -> None:
        if paragraph:
            joined = _join_soft_wraps([_clean_markdown_inline(line) for line in paragraph])
            if joined:
                blocks.append(Block(joined))
            paragraph.clear()

    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            flush()
            continue
        if in_fence:
            if stripped:
                paragraph.append(stripped)
            continue
        if not stripped:
            flush()
            continue
        atx = _ATX.match(stripped)
        if atx:
            flush()
            heading = _clean_markdown_inline(atx.group(2))
            if heading:
                blocks.append(Block(heading, heading_level=len(atx.group(1))))
            continue
        if _SETEXT.match(stripped) and len(paragraph) == 1:
            heading = _clean_markdown_inline(paragraph.pop())
            blocks.append(Block(heading, heading_level=1 if stripped[0] == "=" else 2))
            continue
        if _RULE.match(stripped) or _TABLE_SEPARATOR.match(stripped):
            continue
        if stripped.startswith(">"):
            stripped = stripped.lstrip("> ").strip()
        paragraph.append(_BULLET.sub("- ", stripped))
    flush()
    return Extraction(blocks=[block for block in blocks if block.text])


# Plain text


def extract_text(text: str) -> Extraction:
    return Extraction(blocks=_paragraph_blocks(text))


# HTML


class _HTMLTextParser(HTMLParser):
    """Reduces HTML to headings and paragraphs with the standard library parser.

    Script, style and other non content elements are dropped entirely, so markup that
    never renders as text cannot end up in the index or in a prompt.
    """

    SKIP = frozenset({"script", "style", "noscript", "template", "svg", "head", "nav", "iframe", "object"})
    BREAKS = frozenset(
        {
            "p", "div", "section", "article", "main", "header", "footer", "aside", "ul", "ol",
            "table", "thead", "tbody", "tr", "blockquote", "pre", "dl", "dd", "dt", "figure",
            "figcaption", "details", "summary", "br", "hr", "address", "form", "fieldset",
        }
    )  # fmt: skip
    HEADINGS = {f"h{level}": level for level in range(1, 7)}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[Block] = []
        self._buffer: list[str] = []
        self._lines: list[str] = []
        self._skip_depth = 0
        self._heading: int = 0
        self._cells_in_row = 0

    def _flush_line(self) -> None:
        line = _collapse("".join(self._buffer))
        self._buffer.clear()
        if line:
            self._lines.append(line)

    def _flush_block(self) -> None:
        self._flush_line()
        if self._lines:
            text = "\n".join(self._lines)
            self.blocks.append(
                Block(text if not self._heading else _collapse(text), heading_level=self._heading)
            )
            self._lines.clear()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag in self.HEADINGS:
            self._flush_block()
            self._heading = self.HEADINGS[tag]
        elif tag == "li":
            self._flush_line()
            self._buffer.append("- ")
        elif tag in ("td", "th"):
            if self._cells_in_row:
                self._buffer.append(" | ")
            self._cells_in_row += 1
        elif tag == "tr":
            self._flush_line()
            self._cells_in_row = 0
        elif tag in ("p", "table", "blockquote", "pre"):
            self._flush_block()
        elif tag in self.BREAKS:
            self._flush_line()

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag in self.HEADINGS and self._heading:
            self._flush_block()
            self._heading = 0
        elif tag == "li" or tag == "tr":
            self._flush_line()
            self._cells_in_row = 0
        elif tag in ("p", "table", "blockquote", "pre", "ul", "ol", "dl"):
            self._flush_block()
        elif tag in self.BREAKS:
            self._flush_line()

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._buffer.append(data)

    def close(self) -> None:
        super().close()
        self._flush_block()


def extract_html(text: str) -> Extraction:
    parser = _HTMLTextParser()
    parser.feed(text)
    parser.close()
    blocks = [Block(normalize_text(b.text), b.heading_level) for b in parser.blocks]
    return Extraction(blocks=[block for block in blocks if block.text])


# Dispatch


def decode_text(data: bytes) -> str:
    """Uploads are checked for valid UTF-8 before they get here; replace is a backstop."""
    return data.decode("utf-8-sig", errors="replace")


_TEXT_EXTRACTORS: dict[str, Callable[[str], Extraction]] = {
    MARKDOWN: extract_markdown,
    TEXT: extract_text,
    HTML: extract_html,
}


def extract(data: bytes, content_type: str) -> Extraction:
    if content_type == PDF:
        extraction = extract_pdf(data)
    elif content_type == DOCX:
        extraction = extract_docx(data)
    elif content_type in _TEXT_EXTRACTORS:
        extraction = _TEXT_EXTRACTORS[content_type](decode_text(data))
    else:
        raise ExtractionError("This file type is not supported.")
    if not extraction.blocks:
        raise ExtractionError("This file has no readable text.")
    if all(block.is_heading for block in extraction.blocks):
        # Nothing but heading-like lines (a short notice, a list of titles): index them
        # as body text rather than produce a document with no passages.
        extraction = Extraction(
            [Block(b.text, page_number=b.page_number) for b in extraction.blocks], extraction.page_count
        )
    return extraction
