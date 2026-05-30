from app.ports.text_extractor import TextExtractor


class UnsupportedFormatError(Exception):
    def __init__(self, fmt: str):
        self.format = fmt
        super().__init__(f"No text extractor registered for format '{fmt}'")


class ExtractorRegistry:
    def __init__(self) -> None:
        self._extractors: dict[str, TextExtractor] = {}

    def register(self, extractor: TextExtractor) -> None:
        self._extractors[extractor.supported_format] = extractor

    def has(self, fmt: str) -> bool:
        return fmt in self._extractors

    def get(self, fmt: str) -> TextExtractor:
        if fmt not in self._extractors:
            raise UnsupportedFormatError(fmt)
        return self._extractors[fmt]
