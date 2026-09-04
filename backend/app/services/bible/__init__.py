"""Novel Bible 2.0 services.

- ``bible_service``: read-side dashboard, ledger queries and audits (neglected
  threads, due promises, reader-contract compliance).
- ``living_bible_service``: extraction of proposed Bible updates from a written
  chapter and the accept/reject/apply review loop with value history.
- ``context_compiler``: selects the minimum relevant Bible slice for a chapter.
"""

from .bible_service import BibleService
from .living_bible_service import LivingBibleService
from .context_compiler import ContextCompiler
from .character_deepening_service import CharacterDeepeningService

__all__ = ["BibleService", "LivingBibleService", "ContextCompiler", "CharacterDeepeningService"]
