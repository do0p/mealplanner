from functools import lru_cache

from sqlmodel import Session

from app.adapters.extractor_registry import ExtractorRegistry
from app.adapters.fake_extractor import FakeRecipeExtractor
from app.adapters.ollama_extractor import OllamaRecipeExtractor
from app.adapters.pdf_extractor import PdfTextExtractor
from app.config import settings
from app.db import engine
from app.ports.recipe_extractor import RecipeExtractor
from app.services.import_service import ImportService


@lru_cache
def _text_registry() -> ExtractorRegistry:
    registry = ExtractorRegistry()
    registry.register(PdfTextExtractor())
    return registry


@lru_cache
def _recipe_extractor() -> RecipeExtractor:
    if settings.llm_provider == "anthropic":
        from app.adapters.claude_extractor import ClaudeRecipeExtractor
        return ClaudeRecipeExtractor()
    return OllamaRecipeExtractor()


def _session_factory() -> Session:
    return Session(engine)


def get_import_service() -> ImportService:
    return ImportService(
        session_factory=_session_factory,
        text_registry=_text_registry(),
        recipe_extractor=_recipe_extractor(),
    )
