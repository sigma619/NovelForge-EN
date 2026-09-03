"""Read-side Bible queries: dashboard, ledgers and audits.

The Bible is stored as cards (see ``bootstrap/card_types.py``), so this service
is a typed view over the card table. It never calls an LLM.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlmodel import Session, select

from app.db.models import Card, CardType
from app.schemas.bible import REWARD_TYPES

BIBLE_SECTION_TYPES: Dict[str, List[str]] = {
    "foundation": ["Story Foundation", "Reader Contract", "Theme Map", "Style Profile", "Narrative Architecture"],
    "characters": ["Character Card"],
    "relationships": ["Relationship Arc"],
    "world": ["Worldview Setting", "World Rule", "Power System", "Scene Card", "Organization Card", "Item Card", "Concept Card"],
    "threads": ["Plot Thread"],
    "promises": ["Promise Payoff"],
    "knowledge": ["Knowledge Fact"],
    "timeline": ["Timeline Event"],
    "analysis": ["Chapter Analysis", "Story Structure Map", "Emotional Rhythm", "Narrative Genome", "Originality Transformation"],
}

# Ledger types whose cards are one entry each.
LEDGER_TYPES = ["Plot Thread", "Promise Payoff", "Knowledge Fact", "Timeline Event", "Relationship Arc", "World Rule"]


def _content(card: Card) -> Dict[str, Any]:
    return card.content if isinstance(card.content, dict) else {}


class BibleService:
    def __init__(self, session: Session):
        self.session = session
        self._type_cache: Dict[str, Optional[CardType]] = {}

    # ------------------------------------------------------------------ helpers
    def card_type(self, name: str) -> Optional[CardType]:
        if name not in self._type_cache:
            self._type_cache[name] = self.session.exec(select(CardType).where(CardType.name == name)).first()
        return self._type_cache[name]

    def cards_of_type(self, project_id: int, type_name: str) -> List[Card]:
        ct = self.card_type(type_name)
        if not ct:
            return []
        stmt = (
            select(Card)
            .where(Card.project_id == project_id, Card.card_type_id == ct.id)
            .order_by(Card.display_order, Card.id)
        )
        return list(self.session.exec(stmt).all())

    def singleton(self, project_id: int, type_name: str) -> Optional[Card]:
        cards = self.cards_of_type(project_id, type_name)
        return cards[0] if cards else None

    def find_card(self, project_id: int, type_name: str, title: str) -> Optional[Card]:
        ct = self.card_type(type_name)
        if not ct:
            return None
        stmt = select(Card).where(Card.project_id == project_id, Card.card_type_id == ct.id, Card.title == title)
        return self.session.exec(stmt).first()

    def find_card_by_content_name(self, project_id: int, type_name: str, name: str) -> Optional[Card]:
        """Match by title first, then by content.name / aliases (Character Bible aliases)."""
        card = self.find_card(project_id, type_name, name)
        if card:
            return card
        needle = (name or "").strip().lower()
        if not needle:
            return None
        for c in self.cards_of_type(project_id, type_name):
            content = _content(c)
            if str(content.get("name") or "").strip().lower() == needle:
                return c
            aliases = content.get("aliases")
            if isinstance(aliases, list) and any(str(a).strip().lower() == needle for a in aliases):
                return c
        return None

    def current_chapter_number(self, project_id: int) -> int:
        """Highest chapter number among Chapter Text cards with non-empty content."""
        best = 0
        for card in self.cards_of_type(project_id, "Chapter Text"):
            content = _content(card)
            if not str(content.get("content") or "").strip():
                continue
            try:
                best = max(best, int(content.get("chapter_number") or 0))
            except (TypeError, ValueError):
                continue
        return best

    # ---------------------------------------------------------------- dashboard
    def dashboard(self, project_id: int) -> Dict[str, Any]:
        sections: Dict[str, Any] = {}
        for section, type_names in BIBLE_SECTION_TYPES.items():
            entries = []
            for type_name in type_names:
                for card in self.cards_of_type(project_id, type_name):
                    content = _content(card)
                    entries.append({
                        "card_id": card.id,
                        "card_type": type_name,
                        "title": card.title,
                        "truth_status": content.get("truth_status"),
                        "confidence": content.get("confidence"),
                        "status": content.get("status"),
                        "urgency": content.get("urgency"),
                        "evidence_count": len(content.get("evidence") or []) if isinstance(content.get("evidence"), list) else 0,
                        "has_content": bool(content),
                    })
            sections[section] = {"count": len(entries), "entries": entries}

        current_chapter = self.current_chapter_number(project_id)
        return {
            "project_id": project_id,
            "current_chapter": current_chapter,
            "sections": sections,
            "audits": self.audit(project_id, current_chapter),
        }

    # ------------------------------------------------------------------- audits
    def audit(self, project_id: int, current_chapter: Optional[int] = None) -> Dict[str, Any]:
        """Deterministic continuity audits over the ledgers (no LLM)."""
        if current_chapter is None:
            current_chapter = self.current_chapter_number(project_id)
        warnings: List[Dict[str, Any]] = []

        # Neglected threads: active + not advanced for a long time relative to urgency.
        neglect_window = {"critical": 5, "high": 8, "medium": 15, "low": 30}
        for card in self.cards_of_type(project_id, "Plot Thread"):
            c = _content(card)
            if c.get("status") not in ("active", "planned"):
                continue
            last = c.get("last_advanced_chapter") or c.get("opening_chapter")
            if not isinstance(last, int) or current_chapter <= 0:
                continue
            gap = current_chapter - last
            limit = neglect_window.get(str(c.get("urgency") or "medium"), 15)
            if gap >= limit:
                warnings.append({
                    "kind": "neglected_thread",
                    "severity": "high" if c.get("urgency") in ("high", "critical") else "medium",
                    "card_id": card.id,
                    "title": card.title,
                    "message": f"Thread '{card.title}' has not advanced for {gap} chapters and is marked {c.get('urgency', 'medium')} urgency.",
                })
            nxt = c.get("next_expected_chapter")
            if isinstance(nxt, int) and current_chapter > nxt:
                warnings.append({
                    "kind": "overdue_thread",
                    "severity": "medium",
                    "card_id": card.id,
                    "title": card.title,
                    "message": f"Thread '{card.title}' was expected to advance by chapter {nxt}; current chapter is {current_chapter}.",
                })

        # Overdue promises.
        for card in self.cards_of_type(project_id, "Promise Payoff"):
            c = _content(card)
            status = str(c.get("status") or "planted")
            if status in ("paid_off", "subverted", "intentionally_abandoned", "contradicted"):
                continue
            rng = c.get("target_payoff_range")
            if isinstance(rng, (list, tuple)) and len(rng) == 2 and isinstance(rng[1], int) and current_chapter > rng[1]:
                warnings.append({
                    "kind": "overdue_promise",
                    "severity": "high" if c.get("strength") == "strong" else "medium",
                    "card_id": card.id,
                    "title": card.title,
                    "message": f"Promise '{card.title}' targeted payoff by chapter {rng[1]} and is still '{status}'.",
                })
            elif status == "forgotten":
                warnings.append({
                    "kind": "forgotten_promise",
                    "severity": "medium",
                    "card_id": card.id,
                    "title": card.title,
                    "message": f"Promise '{card.title}' is marked forgotten.",
                })

        # Disputed / low-confidence canon.
        for type_name in LEDGER_TYPES + ["Story Foundation", "Reader Contract", "Theme Map", "Style Profile", "Power System"]:
            for card in self.cards_of_type(project_id, type_name):
                c = _content(card)
                if c.get("truth_status") == "disputed":
                    warnings.append({
                        "kind": "disputed_fact",
                        "severity": "high",
                        "card_id": card.id,
                        "title": card.title,
                        "message": f"{type_name} '{card.title}' is disputed and needs a decision.",
                    })
                conf = c.get("confidence")
                if c.get("truth_status") == "canon" and isinstance(conf, (int, float)) and conf < 0.5:
                    warnings.append({
                        "kind": "low_confidence_canon",
                        "severity": "medium",
                        "card_id": card.id,
                        "title": card.title,
                        "message": f"{type_name} '{card.title}' is canon but confidence is {conf:.2f}.",
                    })

        # Reader-contract reward drought (uses Emotional Rhythm if present).
        contract = self.singleton(project_id, "Reader Contract")
        rhythm = self.singleton(project_id, "Emotional Rhythm")
        if contract and rhythm:
            cc = _content(contract)
            chapters = [ch for ch in (_content(rhythm).get("chapters") or []) if isinstance(ch, dict)]
            chapters.sort(key=lambda ch: int(ch.get("chapter_number") or 0))
            priority = [r for r in (cc.get("reward_types_priority") or []) if r in REWARD_TYPES]
            if priority and chapters:
                primary = priority[0]
                recent = chapters[-8:]
                if recent and not any(primary in (ch.get("rewards") or []) for ch in recent):
                    first, last = recent[0].get("chapter_number"), recent[-1].get("chapter_number")
                    warnings.append({
                        "kind": "reward_drought",
                        "severity": "medium",
                        "card_id": contract.id,
                        "title": contract.title,
                        "message": f"Chapters {first}-{last} delivered none of the primary promised reward '{primary}'.",
                    })

        # Repeated dominant function across adjacent chapters.
        if rhythm:
            chapters = [ch for ch in (_content(rhythm).get("chapters") or []) if isinstance(ch, dict)]
            chapters.sort(key=lambda ch: int(ch.get("chapter_number") or 0))
            run_start = None
            for i in range(1, len(chapters)):
                same = chapters[i].get("dominant_function") == chapters[i - 1].get("dominant_function")
                if same and run_start is None:
                    run_start = i - 1
                if (not same or i == len(chapters) - 1) and run_start is not None:
                    end = i if same else i - 1
                    if end - run_start >= 2:
                        warnings.append({
                            "kind": "repeated_function",
                            "severity": "low",
                            "card_id": rhythm.id,
                            "title": rhythm.title,
                            "message": f"Chapters {chapters[run_start].get('chapter_number')}-{chapters[end].get('chapter_number')} all have dominant function '{chapters[run_start].get('dominant_function')}'.",
                        })
                    run_start = None

        return {"current_chapter": current_chapter, "warnings": warnings}

    # --------------------------------------------------------- relationship view
    def relationship_matrix(self, project_id: int) -> Dict[str, Any]:
        arcs = []
        for card in self.cards_of_type(project_id, "Relationship Arc"):
            c = _content(card)
            arcs.append({
                "card_id": card.id,
                "title": card.title,
                "character_a": c.get("character_a"),
                "character_b": c.get("character_b"),
                "trust": c.get("trust"),
                "affection": c.get("affection"),
                "fear": c.get("fear"),
                "dependency": c.get("dependency"),
                "resentment": c.get("resentment"),
                "public_relationship": c.get("public_relationship"),
                "private_relationship": c.get("private_relationship"),
                "milestones": c.get("milestones") or [],
                "history": c.get("history") or [],
                "truth_status": c.get("truth_status"),
            })
        return {"arcs": arcs}

    # ---------------------------------------------------------- knowledge matrix
    def knowledge_matrix(self, project_id: int) -> Dict[str, Any]:
        rows = []
        entities: List[str] = []
        for card in self.cards_of_type(project_id, "Knowledge Fact"):
            c = _content(card)
            states = {"reader": c.get("reader_state") or "unaware"}
            for k in c.get("knowers") or []:
                if isinstance(k, dict) and k.get("entity"):
                    states[str(k["entity"])] = k.get("state") or "unaware"
                    if k["entity"] not in entities:
                        entities.append(str(k["entity"]))
            rows.append({
                "card_id": card.id,
                "fact": c.get("fact") or card.title,
                "truth_status": c.get("truth_status"),
                "sensitivity": c.get("sensitivity"),
                "planned_reveal_chapter": c.get("planned_reveal_chapter"),
                "states": states,
            })
        return {"entities": ["reader"] + entities, "rows": rows}
