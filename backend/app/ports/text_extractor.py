from abc import ABC, abstractmethod


class TextExtractor(ABC):
    """Extracts text from a document of a specific format.
    Returns a list of (section_number, text) tuples — one per page or section.
    """

    @property
    @abstractmethod
    def supported_format(self) -> str: ...

    @abstractmethod
    def extract(self, data: bytes) -> list[tuple[int, str]]: ...

    def extract_sections(self, data: bytes) -> list[tuple[int, str]]:
        """Return (page_number, section_title) pairs marking where sections start.
        Override to provide richer section detection; default returns empty list."""
        return []
