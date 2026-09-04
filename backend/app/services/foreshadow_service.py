from __future__ import annotations

from typing import Any, Dict, List, Optional
import re
from sqlmodel import Session, select
from datetime import datetime

from app.db.models import ForeshadowItem as ForeshadowItemModel


# English intent cues -> pending goals (bilingual: English + Chinese).
_GOAL_PATTERN = re.compile(
    r"\b(will|is going to|plans to|intends to|prepares to|swears to|vows to|must|将要|准备|打算|誓要|必须)\s*"
    r"([^。？！.!?\n]{2,80})",
    re.IGNORECASE,
)
# English item suffixes + CJK item radicals.
_ITEM_PATTERN = re.compile(
    r"\b((?:[A-Za-z][A-Za-z'\-]* ){0,2}?"
    r"(?:sword|blade|dagger|ring|amulet|talisman|seal|elixir|pill|formation|array|armor|armour|cauldron|pearl|mirror|staff|wand|crown|locket|coin))\b"
    r"|([\u4e00-\u9fa5]{1,8})(剑|刀|戒|符|印|丹|阵|甲|鼎|珠|镜)",
    re.IGNORECASE,
)
_EN_NAME = re.compile(r"\b[A-Z][a-z]{2,15}\b")
_STOPWORDS_EN = {
    "The", "And", "But", "She", "Her", "His", "Him", "They", "Them", "You", "Your", "Was", "Were",
    "Had", "Has", "Did", "Does", "Not", "All", "For", "From", "With", "This", "That", "Then", "When",
    "What", "Where", "Who", "How", "Why", "Will", "Must", "Chapter", "Volume", "Part",
}
_STOPWORDS_CJK = {"什么", "但是", "因为", "然后", "虽然", "可是", "不会", "看看", "我们", "你们", "他们", "以及"}


class ForeshadowService:
    def __init__(self, session: Session):
        self.session = session

    def suggest(self, text: str) -> Dict[str, Any]:
        """
        Bilingual heuristic (English + Chinese):
        - Capture phrases following intent cues (will / plans to / swears to / must / 将要 / 必须 ...)
          as pending goals
        - Capture artifact nouns (sword / ring / amulet ... / 剑 / 戒 ...) as suspected items
        - Extract name candidates (capitalized English words or 2-4 char CJK runs, minus stopwords)
        """
        if not isinstance(text, str):
            text = str(text or "")
        goals: List[str] = []
        items: List[str] = []
        persons: List[str] = []

        # Goals
        for m in _GOAL_PATTERN.findall(text):
            frag = (m[0].strip() + " " + m[1].strip()).strip() if m[0].isascii() else (m[0] + m[1]).strip()
            if frag and frag not in goals:
                goals.append(frag)

        # Items
        for m in _ITEM_PATTERN.findall(text):
            if m[0]:
                frag = m[0].strip()
            else:
                frag = (m[1] + m[2]).strip()
            if frag and frag not in items:
                items.append(frag)

        # Person names (rough): capitalized English words, then 2-4 char CJK runs
        for m in _EN_NAME.findall(text):
            if m not in _STOPWORDS_EN and m not in persons:
                persons.append(m)
        for m in re.findall(r"([\u4e00-\u9fa5]{2,4})", text):
            if m and m not in _STOPWORDS_CJK and m not in persons:
                persons.append(m)
        persons = persons[:10]

        return {
            "goals": goals[:8],
            "items": items[:8],
            "persons": persons,
        }

    # --- CRUD via DB ---
    def list(self, project_id: int, status: Optional[str] = None) -> List[ForeshadowItemModel]:
        stmt = select(ForeshadowItemModel).where(ForeshadowItemModel.project_id == project_id)
        if status:
            stmt = stmt.where(ForeshadowItemModel.status == status)
        items = self.session.exec(stmt.order_by(ForeshadowItemModel.status.desc(), ForeshadowItemModel.created_at.desc())).all()
        return items

    def register(self, project_id: int, entries: List[Dict[str, Any]]) -> List[ForeshadowItemModel]:
        out: List[ForeshadowItemModel] = []
        for it in entries:
            title = str(it.get('title') or '').strip()
            if not title:
                continue
            item = ForeshadowItemModel(
                project_id=project_id,
                chapter_id=it.get('chapter_id'),
                title=title,
                type=str(it.get('type') or 'other') or 'other',
                note=it.get('note'),
                status='open',
            )
            self.session.add(item)
            out.append(item)
        if out:
            self.session.commit()
            for i in out:
                self.session.refresh(i)
        return out

    def resolve(self, project_id: int, item_id: str | int) -> Optional[ForeshadowItemModel]:
        item = self.session.get(ForeshadowItemModel, item_id)
        if not item or item.project_id != project_id:
            return None
        if item.status != 'resolved':
            item.status = 'resolved'
            item.resolved_at = datetime.utcnow()
            self.session.add(item)
            self.session.commit()
            self.session.refresh(item)
        return item

    def delete(self, project_id: int, item_id: str | int) -> bool:
        item = self.session.get(ForeshadowItemModel, item_id)
        if not item or item.project_id != project_id:
            return False
        self.session.delete(item)
        self.session.commit()
        return True
