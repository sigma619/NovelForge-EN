"""Manuscript import for the Narrative Reverse-Engineering Lab.

Only user-supplied files are analysed. There is deliberately no fetching,
scraping or downloading of any kind here.

Pipeline:
1. ``extract_text`` converts TXT / Markdown / EPUB / DOCX to plain text
   (EPUB and DOCX are parsed with the standard library: zipfile + xml + html.parser).
2. ``detect_chapters`` splits the text using a chapter regex (auto-detected from a
   small set of common patterns when the user does not supply one), optionally
   tracking volume headings and excluding front matter / afterword.
3. ``store_manuscript`` writes each chapter as a "Chapter Analysis" card whose
   content holds only identity + word count + ``source_text`` so the Lab workflow
   can analyse chapters without re-reading files from disk (the legacy workflow
   hard-coded a local path).
"""

from __future__ import annotations

import html
import re
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree

from loguru import logger
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import Session, select

from app.db.models import Card, CardType
from app.schemas.card import CardCreate
from app.services.card_service import CardService

SUPPORTED_EXTENSIONS = (".txt", ".md", ".markdown", ".epub", ".docx")

# Ordered by specificity. Each pattern must expose the chapter number (or be numberless).
CHAPTER_PATTERN_CANDIDATES: List[Tuple[str, str]] = [
    ("chapter_word", r"^\s*(?:#+\s*)?Chapter\s+(\d+|[IVXLC]+|[A-Za-z\-]+)\b.*$"),
    ("cjk_chapter", r"^\s*第\s*([零一二三四五六七八九十百千0-9]+)\s*[章节回].*$"),
    ("numbered_heading", r"^\s*#{1,3}\s*(\d+)[\.\):]?\s+.*$"),
    ("bare_number_title", r"^\s*(\d{1,4})[\.\)]\s+\S.*$"),
    ("markdown_h1", r"^\s*#\s+(.+)$"),
]

VOLUME_PATTERN_DEFAULT = r"^\s*(?:#+\s*)?(?:Volume|Book|Part|Arc)\s+(\d+|[IVXLC]+|[A-Za-z\-]+)\b.*$|^\s*第\s*([零一二三四五六七八九十百千0-9]+)\s*[卷部纪].*$"

FRONT_MATTER_HINTS = ("copyright", "table of contents", "contents", "dedication", "acknowledg", "foreword", "preface", "prologue")
AFTERWORD_HINTS = ("afterword", "epilogue", "about the author", "acknowledg", "postscript", "author's note", "authors note")

_CJK_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CJK_UNITS = {"十": 10, "百": 100, "千": 1000}
_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
_WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90, "hundred": 100,
}


def parse_number(token: str) -> Optional[int]:
    t = (token or "").strip()
    if not t:
        return None
    if t.isdigit():
        return int(t)
    if re.fullmatch(r"[IVXLC]+", t):
        total, prev = 0, 0
        for ch in reversed(t):
            v = _ROMAN[ch]
            total = total - v if v < prev else total + v
            prev = max(prev, v)
        return total
    if all(ch in _CJK_DIGITS or ch in _CJK_UNITS for ch in t):
        total, num = 0, 0
        for ch in t:
            if ch in _CJK_DIGITS:
                num = _CJK_DIGITS[ch]
            else:
                unit = _CJK_UNITS[ch]
                total += (num or 1) * unit
                num = 0
        return total + num
    words = re.split(r"[\s\-]+", t.lower())
    if words and all(w in _WORD_NUMBERS for w in words):
        total, current = 0, 0
        for w in words:
            v = _WORD_NUMBERS[w]
            if v == 100:
                current = (current or 1) * 100
            else:
                current += v
        return total + current
    return None


# --------------------------------------------------------------------------- text
class _HTMLText(HTMLParser):
    BLOCK_TAGS = {"p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li", "section", "article", "blockquote", "tr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("script", "style", "head"):
            self._skip += 1
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")
        if tag in ("h1", "h2", "h3"):
            self.parts.append("\n# ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "head") and self._skip:
            self._skip -= 1
        if tag in self.BLOCK_TAGS or tag in ("h1", "h2", "h3"):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts)
        raw = re.sub(r"[ \t]+\n", "\n", raw)
        return re.sub(r"\n{3,}", "\n\n", raw).strip()


def _decode(data: bytes, encoding: Optional[str]) -> str:
    if encoding and encoding.lower() != "auto":
        return data.decode(encoding, errors="replace")
    for enc in ("utf-8-sig", "utf-8", "gb18030", "utf-16", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _epub_text(data: bytes) -> str:
    out: List[str] = []
    with zipfile.ZipFile(_bytes_io(data)) as zf:
        names = zf.namelist()
        spine: List[str] = []
        try:
            container = ElementTree.fromstring(zf.read("META-INF/container.xml"))
            ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
            rootfile = container.find(".//c:rootfile", ns)
            opf_path = rootfile.attrib["full-path"] if rootfile is not None else None
            if opf_path:
                opf = ElementTree.fromstring(zf.read(opf_path))
                base = opf_path.rsplit("/", 1)[0] + "/" if "/" in opf_path else ""
                manifest = {item.attrib.get("id"): item.attrib.get("href") for item in opf.iter() if item.tag.endswith("item")}
                for itemref in opf.iter():
                    if itemref.tag.endswith("itemref"):
                        href = manifest.get(itemref.attrib.get("idref"))
                        if href:
                            spine.append(base + html.unescape(href))
        except Exception as exc:  # fall back to alphabetical html order
            logger.warning(f"[ManuscriptImport] EPUB spine parse failed, falling back: {exc}")
        if not spine:
            spine = sorted(n for n in names if n.lower().endswith((".xhtml", ".html", ".htm")))
        for name in spine:
            if name not in names:
                continue
            parser = _HTMLText()
            parser.feed(_decode(zf.read(name), None))
            text = parser.text()
            if text:
                out.append(text)
    return "\n\n".join(out)


def _docx_text(data: bytes) -> str:
    with zipfile.ZipFile(_bytes_io(data)) as zf:
        xml = zf.read("word/document.xml")
    root = ElementTree.fromstring(xml)
    w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    lines: List[str] = []
    for para in root.iter(f"{w}p"):
        style = para.find(f"{w}pPr/{w}pStyle")
        style_val = style.attrib.get(f"{w}val", "") if style is not None else ""
        text = "".join(t.text or "" for t in para.iter(f"{w}t")).strip()
        if not text:
            lines.append("")
            continue
        if style_val.lower().startswith("heading") or style_val.lower() == "title":
            lines.append(f"# {text}")
        else:
            lines.append(text)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _bytes_io(data: bytes):
    import io
    return io.BytesIO(data)


def extract_text(filename: str, data: bytes, encoding: Optional[str] = None) -> str:
    name = (filename or "").lower()
    if name.endswith(".epub"):
        return _epub_text(data)
    if name.endswith(".docx"):
        return _docx_text(data)
    if name.endswith(SUPPORTED_EXTENSIONS[:3]):
        return _decode(data, encoding)
    raise ValueError(f"Unsupported file type: {filename}. Supported: {', '.join(SUPPORTED_EXTENSIONS)}")


# ------------------------------------------------------------------- detection
@dataclass
class DetectedChapter:
    index: int
    number: Optional[int]
    title: str
    volume: str
    text: str
    word_count: int
    start_line: int
    flags: List[str] = field(default_factory=list)


@dataclass
class DetectionResult:
    chapter_pattern: str
    pattern_name: str
    volume_pattern: str
    chapters: List[DetectedChapter]
    volumes: List[str]
    warnings: List[str]
    total_words: int


def _word_count(text: str) -> int:
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    words = len(re.findall(r"[A-Za-z0-9'’-]+", text))
    return cjk + words


def auto_detect_pattern(lines: List[str]) -> Tuple[str, str]:
    best: Tuple[int, str, str] = (0, "", "")
    for name, pattern in CHAPTER_PATTERN_CANDIDATES:
        rx = re.compile(pattern, re.IGNORECASE)
        hits = sum(1 for ln in lines if rx.match(ln))
        if hits > best[0]:
            best = (hits, name, pattern)
    if best[0] < 2:
        return "none", ""
    return best[1], best[2]


def detect_chapters(
    text: str,
    *,
    chapter_pattern: Optional[str] = None,
    volume_pattern: Optional[str] = None,
    exclude_front_matter: bool = True,
    exclude_afterword: bool = True,
    min_chapter_words: int = 80,
) -> DetectionResult:
    lines = text.splitlines()
    pattern_name = "custom"
    if not chapter_pattern:
        pattern_name, chapter_pattern = auto_detect_pattern(lines)
    warnings: List[str] = []
    volume_pattern = volume_pattern or VOLUME_PATTERN_DEFAULT
    vol_rx = re.compile(volume_pattern, re.IGNORECASE | re.MULTILINE) if volume_pattern else None
    chap_rx = re.compile(chapter_pattern, re.IGNORECASE) if chapter_pattern else None
    # Standalone headings for non-chapter sections so they never leak into a chapter body.
    section_rx = re.compile(r"^\s*(?:#+\s*)?(afterword|epilogue|prologue|foreword|preface|postscript|author'?s note|about the author|acknowledg\w*)\b.{0,60}$", re.IGNORECASE)

    chapters: List[DetectedChapter] = []
    volumes: List[str] = []
    current_volume = "Volume 1"
    current_title: Optional[str] = None
    current_number: Optional[int] = None
    buffer: List[str] = []
    start_line = 0
    preface_buffer: List[str] = []

    def flush(end_line: int) -> None:
        nonlocal buffer, current_title, current_number, start_line
        body = "\n".join(buffer).strip()
        if current_title is None:
            if body:
                preface_buffer.append(body)
        else:
            chapters.append(DetectedChapter(
                index=len(chapters) + 1,
                number=current_number,
                title=current_title,
                volume=current_volume,
                text=body,
                word_count=_word_count(body),
                start_line=start_line,
            ))
        buffer = []
        start_line = end_line

    for i, line in enumerate(lines):
        if vol_rx and vol_rx.match(line) and (not chap_rx or not chap_rx.match(line)):
            flush(i)
            current_volume = line.strip().lstrip("#").strip() or f"Volume {len(volumes) + 1}"
            if current_volume not in volumes:
                volumes.append(current_volume)
            current_title = None
            current_number = None
            continue
        if chap_rx and chap_rx.match(line):
            flush(i)
            m = chap_rx.match(line)
            current_title = line.strip().lstrip("#").strip()
            num = None
            for g in (m.groups() if m else ()):
                if g:
                    num = parse_number(g)
                    if num is not None:
                        break
            current_number = num
            continue
        if section_rx.match(line) and (chap_rx is None or not chap_rx.match(line)):
            flush(i)
            current_title = line.strip().lstrip("#").strip()
            current_number = None
            continue
        buffer.append(line)
    flush(len(lines))

    if not chapters:
        if text.strip():
            chapters.append(DetectedChapter(index=1, number=1, title="Chapter 1", volume=current_volume, text=text.strip(), word_count=_word_count(text), start_line=0))
            warnings.append("No chapter headings detected; the whole file was treated as one chapter. Adjust the chapter pattern.")
    if not volumes:
        volumes = [current_volume]

    # Front matter / afterword heuristics.
    if chapters and exclude_front_matter:
        first = chapters[0]
        low = first.title.lower()
        if first.word_count < min_chapter_words or any(h in low for h in FRONT_MATTER_HINTS if h != "prologue"):
            first.flags.append("front_matter")
    if chapters and exclude_afterword:
        last = chapters[-1]
        low = last.title.lower()
        if any(h in low for h in AFTERWORD_HINTS):
            last.flags.append("afterword")

    # Duplicate / missing number / tiny chapter warnings.
    seen: Dict[str, int] = {}
    numbers = [c.number for c in chapters if c.number is not None]
    for c in chapters:
        key = re.sub(r"\s+", " ", c.title.strip().lower())
        if key in seen:
            c.flags.append("duplicate_title")
            warnings.append(f"Chapter {c.index} '{c.title}' duplicates chapter {seen[key]}.")
        else:
            seen[key] = c.index
        if c.word_count < min_chapter_words and "front_matter" not in c.flags and "afterword" not in c.flags:
            c.flags.append("very_short")
    if numbers:
        expected = set(range(min(numbers), max(numbers) + 1))
        missing = sorted(expected - set(numbers))
        if missing:
            warnings.append(f"Missing chapter numbers: {missing[:20]}{'…' if len(missing) > 20 else ''}")
        dupes = sorted({n for n in numbers if numbers.count(n) > 1})
        if dupes:
            warnings.append(f"Repeated chapter numbers: {dupes[:20]}")
    if preface_buffer and exclude_front_matter:
        warnings.append(f"{_word_count(' '.join(preface_buffer))} words before the first chapter heading were excluded as front matter.")

    return DetectionResult(
        chapter_pattern=chapter_pattern or "",
        pattern_name=pattern_name,
        volume_pattern=volume_pattern,
        chapters=chapters,
        volumes=volumes,
        warnings=warnings,
        total_words=sum(c.word_count for c in chapters),
    )


def apply_corrections(chapters: List[DetectedChapter], corrections: List[Dict[str, Any]]) -> List[DetectedChapter]:
    """Apply user split/merge/exclude/rename corrections, then renumber sequentially."""
    result = list(chapters)
    for corr in corrections:
        op = corr.get("op")
        idx = int(corr.get("index") or 0)
        pos = next((i for i, c in enumerate(result) if c.index == idx), None)
        if pos is None:
            continue
        if op == "exclude":
            result.pop(pos)
        elif op == "include":
            result[pos].flags = [f for f in result[pos].flags if f not in ("front_matter", "afterword")]
        elif op == "rename":
            result[pos].title = str(corr.get("title") or result[pos].title)
        elif op == "merge_with_next" and pos + 1 < len(result):
            a, b = result[pos], result[pos + 1]
            a.text = f"{a.text}\n\n{b.text}".strip()
            a.word_count = _word_count(a.text)
            a.flags = [f for f in a.flags if f != "very_short"]
            result.pop(pos + 1)
        elif op == "split":
            marker = str(corr.get("at_text") or "").strip()
            c = result[pos]
            if marker and marker in c.text:
                head, tail = c.text.split(marker, 1)
                c.text = head.strip()
                c.word_count = _word_count(c.text)
                new = DetectedChapter(index=c.index, number=None, title=str(corr.get("new_title") or f"{c.title} (2)"), volume=c.volume, text=(marker + tail).strip(), word_count=_word_count(marker + tail), start_line=c.start_line)
                result.insert(pos + 1, new)
    for i, c in enumerate(result, start=1):
        c.index = i
    return result


# --------------------------------------------------------------------- storage
MANUSCRIPT_FOLDER_TITLE = "Imported Manuscript"


class ManuscriptImportService:
    def __init__(self, session: Session):
        self.session = session

    def _card_type(self, name: str) -> CardType:
        ct = self.session.exec(select(CardType).where(CardType.name == name)).first()
        if not ct:
            raise ValueError(f"Card type not found: {name}")
        return ct

    def _get_or_create_folder(self, project_id: int, title: str) -> Card:
        folder_type = self._card_type("Folder")
        existing = self.session.exec(select(Card).where(Card.project_id == project_id, Card.card_type_id == folder_type.id, Card.title == title, Card.parent_id.is_(None))).first()
        if existing:
            return existing
        return CardService(self.session).create(CardCreate(title=title, content={}, card_type_id=folder_type.id, parent_id=None), project_id)

    def store_manuscript(
        self,
        *,
        project_id: int,
        title: str,
        author: str,
        genre: str,
        language: str,
        chapters: List[DetectedChapter],
        replace_existing: bool = True,
    ) -> Dict[str, Any]:
        analysis_type = self._card_type("Chapter Analysis")
        folder = self._get_or_create_folder(project_id, MANUSCRIPT_FOLDER_TITLE)
        folder.content = {**(folder.content or {}), "book_title": title, "author": author, "genre": genre, "language": language, "chapter_count": len(chapters)}
        flag_modified(folder, "content")
        self.session.add(folder)

        if replace_existing:
            old = self.session.exec(select(Card).where(Card.project_id == project_id, Card.card_type_id == analysis_type.id, Card.parent_id == folder.id)).all()
            for c in old:
                self.session.delete(c)
            self.session.flush()

        service = CardService(self.session)
        card_ids: List[int] = []
        kept = [c for c in chapters if not ({"front_matter", "afterword"} & set(c.flags))]
        for seq, ch in enumerate(kept, start=1):
            content = {
                "chapter_number": seq,
                "title": ch.title,
                "volume": ch.volume,
                "word_count": ch.word_count,
                "summary": "",
                "source_text": ch.text,
                "source_chapter_label": ch.number,
                "analysis_status": "pending",
            }
            card = service.create(CardCreate(title=f"Ch {seq:04d} · {ch.title}"[:200], content=content, card_type_id=analysis_type.id, parent_id=folder.id), project_id)
            card_ids.append(card.id)
        self.session.commit()
        logger.info(f"[ManuscriptImport] stored {len(card_ids)} chapters for project {project_id}")
        return {"folder_card_id": folder.id, "chapter_card_ids": card_ids, "chapter_count": len(card_ids), "total_words": sum(c.word_count for c in kept)}

    def list_manuscript(self, project_id: int) -> Dict[str, Any]:
        analysis_type = self._card_type("Chapter Analysis")
        folder_type = self._card_type("Folder")
        folder = self.session.exec(select(Card).where(Card.project_id == project_id, Card.card_type_id == folder_type.id, Card.title == MANUSCRIPT_FOLDER_TITLE)).first()
        if not folder:
            return {"folder_card_id": None, "meta": {}, "chapters": []}
        cards = self.session.exec(select(Card).where(Card.project_id == project_id, Card.card_type_id == analysis_type.id, Card.parent_id == folder.id).order_by(Card.display_order, Card.id)).all()
        chapters = []
        for c in cards:
            content = c.content if isinstance(c.content, dict) else {}
            chapters.append({
                "card_id": c.id,
                "chapter_number": content.get("chapter_number"),
                "title": content.get("title") or c.title,
                "volume": content.get("volume"),
                "word_count": content.get("word_count"),
                "analysis_status": content.get("analysis_status") or ("done" if content.get("summary") else "pending"),
                "scene_count": len(content.get("scenes") or []),
            })
        return {"folder_card_id": folder.id, "meta": {k: v for k, v in (folder.content or {}).items()}, "chapters": chapters}
