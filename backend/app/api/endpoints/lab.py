"""Narrative Reverse-Engineering Lab API: manuscript import wizard.

Analysis itself runs through the "Narrative Reverse-Engineering Lab" workflow so
it benefits from background execution, node progress and checkpoint resume.
"""

from __future__ import annotations

import base64
import re
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.db.session import get_session
from app.services.lab.manuscript_import import (
    CHAPTER_PATTERN_CANDIDATES,
    SUPPORTED_EXTENSIONS,
    VOLUME_PATTERN_DEFAULT,
    DetectedChapter,
    DetectionResult,
    ManuscriptImportService,
    apply_corrections,
    detect_chapters,
    extract_text,
)

router = APIRouter()


class ManuscriptPreviewRequest(BaseModel):
    filename: str
    content_base64: str = Field(description="File bytes, base64 encoded (user-supplied file only)")
    encoding: Optional[str] = Field(default=None, description="Text encoding for TXT/MD; auto-detect when empty")
    chapter_pattern: Optional[str] = Field(default=None, description="Chapter heading regex; auto-detected when empty")
    volume_pattern: Optional[str] = Field(default=None, description="Volume heading regex")
    exclude_front_matter: bool = True
    exclude_afterword: bool = True
    corrections: List[Dict[str, Any]] = Field(default_factory=list, description="split/merge/exclude/include/rename ops")
    preview_chars: int = Field(default=400, ge=0, le=4000)


class ChapterPreview(BaseModel):
    index: int
    number: Optional[int]
    title: str
    volume: str
    word_count: int
    flags: List[str]
    preview: str


class ManuscriptPreviewResponse(BaseModel):
    chapter_pattern: str
    pattern_name: str
    volume_pattern: str
    chapters: List[ChapterPreview]
    volumes: List[str]
    warnings: List[str]
    total_words: int
    total_chapters: int
    included_chapters: int
    estimated_input_tokens: int
    pattern_candidates: List[Dict[str, str]]
    supported_extensions: List[str]


class ManuscriptImportRequest(ManuscriptPreviewRequest):
    project_id: int
    book_title: str = ""
    author: str = ""
    genre: str = ""
    language: str = ""
    replace_existing: bool = True


class ManuscriptImportResponse(BaseModel):
    folder_card_id: int
    chapter_card_ids: List[int]
    chapter_count: int
    total_words: int


class ManuscriptListResponse(BaseModel):
    folder_card_id: Optional[int]
    meta: Dict[str, Any]
    chapters: List[Dict[str, Any]]


def _detect(req: ManuscriptPreviewRequest) -> Tuple[List[DetectedChapter], DetectionResult]:
    try:
        data = base64.b64decode(req.content_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="content_base64 is not valid base64")
    if len(data) > 60 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (limit 60 MB)")
    try:
        text = extract_text(req.filename, data, req.encoding)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {e}")
    try:
        result = detect_chapters(
            text,
            chapter_pattern=req.chapter_pattern or None,
            volume_pattern=req.volume_pattern or None,
            exclude_front_matter=req.exclude_front_matter,
            exclude_afterword=req.exclude_afterword,
        )
    except re.error as e:
        raise HTTPException(status_code=400, detail=f"Invalid chapter/volume regex: {e}")
    chapters = apply_corrections(result.chapters, req.corrections) if req.corrections else result.chapters
    return chapters, result


@router.post("/manuscript/preview", response_model=ManuscriptPreviewResponse, summary="Parse a user-supplied manuscript and preview chapter detection")
def preview_manuscript(req: ManuscriptPreviewRequest):
    chapters, result = _detect(req)
    included = [c for c in chapters if not ({"front_matter", "afterword"} & set(c.flags))]
    total_words = sum(c.word_count for c in included)
    return ManuscriptPreviewResponse(
        chapter_pattern=result.chapter_pattern,
        pattern_name=result.pattern_name,
        volume_pattern=result.volume_pattern,
        chapters=[
            ChapterPreview(index=c.index, number=c.number, title=c.title, volume=c.volume, word_count=c.word_count, flags=c.flags, preview=c.text[: req.preview_chars])
            for c in chapters
        ],
        volumes=result.volumes,
        warnings=result.warnings,
        total_words=total_words,
        total_chapters=len(chapters),
        included_chapters=len(included),
        # Rough estimate: ~1.4 tokens per word of source plus prompt overhead per chapter.
        estimated_input_tokens=int(total_words * 1.4) + len(included) * 1500,
        pattern_candidates=[{"name": n, "pattern": p} for n, p in CHAPTER_PATTERN_CANDIDATES],
        supported_extensions=list(SUPPORTED_EXTENSIONS),
    )


@router.post("/manuscript/import", response_model=ManuscriptImportResponse, summary="Store the corrected chapter split as Chapter Analysis cards")
def import_manuscript(req: ManuscriptImportRequest, session: Session = Depends(get_session)):
    chapters, _ = _detect(req)
    svc = ManuscriptImportService(session)
    try:
        result = svc.store_manuscript(
            project_id=req.project_id,
            title=req.book_title or req.filename,
            author=req.author,
            genre=req.genre,
            language=req.language,
            chapters=chapters,
            replace_existing=req.replace_existing,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ManuscriptImportResponse(**result)


@router.get("/manuscript", response_model=ManuscriptListResponse, summary="List the imported manuscript chapters and their analysis status")
def list_manuscript(project_id: int, session: Session = Depends(get_session)):
    return ManuscriptImportService(session).list_manuscript(project_id)


@router.get("/manuscript/defaults", summary="Default detection patterns")
def manuscript_defaults():
    return {
        "volume_pattern": VOLUME_PATTERN_DEFAULT,
        "pattern_candidates": [{"name": n, "pattern": p} for n, p in CHAPTER_PATTERN_CANDIDATES],
        "supported_extensions": list(SUPPORTED_EXTENSIONS),
    }
