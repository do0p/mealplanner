import logging
import re
from io import BytesIO

import pypdf

from app.ports.text_extractor import TextExtractor

logger = logging.getLogger(__name__)

# Words that appear as recipe sub-headings, not section titles
_RECIPE_SUBHEADINGS = {
    "ingredients", "method", "instructions", "directions",
    "preparation", "serves", "servings", "notes", "tips",
}


class PdfTextExtractor(TextExtractor):
    supported_format = "pdf"

    def extract(self, data: bytes) -> list[tuple[int, str]]:
        reader = pypdf.PdfReader(BytesIO(data))
        segments = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                segments.append((page_number, text))
        return segments

    def extract_sections(self, data: bytes) -> list[tuple[int, str]]:
        reader = pypdf.PdfReader(BytesIO(data))

        # Try PDF outline/bookmarks first
        if reader.outline:
            sections = self._sections_from_outline(reader, reader.outline)
            if sections:
                logger.info("PDF outline: %d bookmark(s) found", len(sections))
                return sections

        # Fallback: heuristic heading detection from page text
        sections = self._sections_from_heuristics(reader)
        logger.info("No PDF outline, %d heuristic heading(s) found", len(sections))
        return sections

    def _sections_from_outline(
        self, reader: pypdf.PdfReader, outline, depth: int = 0
    ) -> list[tuple[int, str]]:
        """Traverse all bookmark levels and return every (page_num, title) pair."""
        sections = []
        for item in outline:
            if isinstance(item, list):
                sections.extend(self._sections_from_outline(reader, item, depth + 1))
            else:
                try:
                    page_num = reader.get_destination_page_number(item) + 1
                    sections.append((page_num, item.title))
                except Exception:
                    pass
        return sorted(sections, key=lambda x: x[0])

    def _sections_from_heuristics(
        self, reader: pypdf.PdfReader
    ) -> list[tuple[int, str]]:
        sections = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
            for line in lines[:6]:
                if self._looks_like_heading(line):
                    sections.append((i + 1, line))
                    break
        return sections

    def _looks_like_heading(self, line: str) -> bool:
        if not line or len(line) < 3 or len(line) > 60:
            return False
        if line[0].isdigit():
            return False
        if line[-1] in ".,:;?!":
            return False
        normalized = line.lower().strip()
        if normalized in _RECIPE_SUBHEADINGS:
            return False
        words = line.split()
        if not words:
            return False
        cap_count = sum(1 for w in words if w and w[0].isupper())
        return line.isupper() or (cap_count / len(words) >= 0.7)
