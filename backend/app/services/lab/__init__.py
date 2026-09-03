"""Narrative Reverse-Engineering Lab services.

- ``manuscript_import``: parse user-supplied TXT / Markdown / EPUB / DOCX files,
  detect volumes and chapters, and store the manuscript so workflows can analyse it.
- ``lab_helpers``: expression helpers used by the Lab workflow (window building,
  digest formatting, entity mention aggregation).
"""

from .manuscript_import import ManuscriptImportService

__all__ = ["ManuscriptImportService"]
