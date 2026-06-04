"""Ollama-backed recipe extractor.

All LLM calls happen only at import/processing time, never at serving time.
The client is created per call so a newly-started Ollama server is picked up
immediately — no app restart needed.
"""
import json
import logging
import re
import time
from collections.abc import Callable

import ollama

from app.config import settings
from app.ports.recipe_extractor import ExtractedIngredient, ExtractedRecipe, RecipeExtractor
from app.services.chunking import build_chunks, estimate_tokens

logger = logging.getLogger(__name__)

_SEGMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "recipes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "page_numbers": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["title", "page_numbers"],
            },
        }
    },
    "required": ["recipes"],
}

_EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "servings": {"type": "integer"},
        "course": {
            "type": "string",
            "enum": ["breakfast", "appetizer", "soup", "salad", "main", "side", "dessert", "snack", "beverage"],
        },
        "ingredients": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "quantity": {"type": "number"},
                    "unit": {"type": "string"},
                    "category": {"type": "string"},
                    "raw_text": {"type": "string"},
                },
                "required": ["name", "raw_text"],
            },
        },
        "steps": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "string"},
        "is_vegetarian": {"type": "boolean"},
        "is_vegan": {"type": "boolean"},
        "nutrition": {
            "type": "object",
            "properties": {
                "calories": {"type": "number"},
                "protein_g": {"type": "number"},
                "fat_g": {"type": "number"},
                "carbs_g": {"type": "number"},
                "calories_per_serving": {"type": "number"},
                "protein_g_per_serving": {"type": "number"},
                "fat_g_per_serving": {"type": "number"},
                "carbs_g_per_serving": {"type": "number"},
            },
            "required": ["calories", "protein_g", "fat_g", "carbs_g"],
        },
    },
    "required": ["title", "course", "ingredients", "steps", "nutrition"],
}


def _client() -> ollama.Client:
    return ollama.Client(host=settings.ollama_base_url, timeout=settings.ollama_timeout)


def _chat(messages: list[dict], schema: dict) -> dict:
    total_chars = sum(len(m["content"]) for m in messages)
    estimated_tokens = estimate_tokens("x" * total_chars)
    logger.info(
        "_chat: sending %d chars (~%d tokens), think=False, num_ctx=%d, num_predict=4096",
        total_chars, estimated_tokens, settings.ollama_num_ctx,
    )
    t0 = time.monotonic()
    resp = _client().chat(
        model=settings.ollama_model,
        messages=messages,
        format=schema,
        think=False,
        options={"num_predict": 4096, "num_ctx": settings.ollama_num_ctx},
    )
    elapsed = time.monotonic() - t0
    response_chars = len(resp.message.content)
    logger.info(
        "_chat: response in %.1fs, %d chars output",
        elapsed, response_chars,
    )
    return json.loads(resp.message.content)


def _build_text(segments: list[tuple[int, str]]) -> str:
    return "\n\n".join(f"[Page {n}]\n{text}" for n, text in segments)


def _normalize_title(title: str) -> str:
    return re.sub(r"\W+", " ", title.lower()).strip()


def _merge_recipe_list(all_found: list[dict]) -> list[dict]:
    """Deduplicate recipes found across chunks by normalized title."""
    seen: dict[str, dict] = {}
    for item in all_found:
        key = _normalize_title(item.get("title", ""))
        if not key:
            continue
        if key in seen:
            existing = set(seen[key].get("page_numbers") or [])
            new = set(item.get("page_numbers") or [])
            seen[key]["page_numbers"] = sorted(existing | new)
        else:
            seen[key] = {
                "title": item.get("title", ""),
                "page_numbers": sorted(set(item.get("page_numbers") or [])),
            }
    result = list(seen.values())
    result.sort(key=lambda x: min(x["page_numbers"]) if x["page_numbers"] else 0)
    return result



class OllamaRecipeExtractor(RecipeExtractor):

    def is_available(self) -> bool:
        try:
            _client().list()
            return True
        except Exception:
            return False

    def extract_recipes(
        self,
        segments: list[tuple[int, str]],
        on_progress: Callable[[str, int, int], None] | None = None,
    ) -> list[ExtractedRecipe]:
        page_map = {n: text for n, text in segments}

        chunks = build_chunks(segments, settings.ollama_chunk_tokens)
        total_chunks = len(chunks)

        logger.info("Segmenting document: %d chunk(s), budget %d tokens", total_chunks, settings.ollama_chunk_tokens)

        # ── Phase 1: segmentation ──────────────────────────────────────────
        if on_progress:
            on_progress("segmenting", 0, total_chunks)

        all_found: list[dict] = []
        for i, chunk in enumerate(chunks):
            chunk_text = _build_text(chunk)
            pages_in_chunk = [p for p, _ in chunk]
            logger.info(
                "Segmenting chunk %d/%d: pages %d-%d (%d pages, ~%d tokens)",
                i + 1, total_chunks,
                pages_in_chunk[0], pages_in_chunk[-1],
                len(pages_in_chunk),
                estimate_tokens(chunk_text),
            )
            seg_result = _chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a recipe extraction assistant. "
                            "Identify all recipes in the provided document text and return their "
                            "titles and the page numbers on which they appear."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "/no_think\n"
                            "Find all recipes in the text below. For a single-recipe document "
                            "return a one-item array. Each item needs a title and an array of "
                            "page_numbers.\n\n" + chunk_text
                        ),
                    },
                ],
                schema=_SEGMENT_SCHEMA,
            )
            recipes_found = seg_result.get("recipes", [])
            logger.info(
                "Segmenting chunk %d/%d: found %d recipe(s)",
                i + 1, total_chunks, len(recipes_found),
            )
            all_found.extend(recipes_found)
            if on_progress:
                on_progress("segmenting", i + 1, total_chunks)

        found = _merge_recipe_list(all_found)
        if not found:
            found = [{"title": "Recipe", "page_numbers": [n for n, _ in segments]}]

        total_recipes = len(found)
        logger.info("Found %d recipe(s) after merging chunks", total_recipes)

        # ── Phase 2: extraction ────────────────────────────────────────────
        if on_progress:
            on_progress("extracting", 0, total_recipes)

        results: list[ExtractedRecipe] = []
        for i, rec_info in enumerate(found):
            title: str = rec_info.get("title", "Untitled")
            pages: list[int] = rec_info.get("page_numbers") or [n for n, _ in segments]
            source_text = "\n\n".join(
                page_map[p] for p in pages if p in page_map
            ) or _build_text(segments)

            ext = self._extract_one(title, source_text, pages)
            results.append(ext)
            if on_progress:
                on_progress("extracting", i + 1, total_recipes)

        return results

    def _extract_one(
        self, title: str, source_text: str, pages: list[int]
    ) -> ExtractedRecipe:
        try:
            data = _chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a recipe extraction assistant. Rules:\n"
                            "1. Copy instruction steps VERBATIM — do not paraphrase or convert anything.\n"
                            "2. Ingredient quantities are as written in the recipe (for the "
                            "stated serving size — do NOT divide them yourself).\n"
                            "3. For each ingredient supply: name, quantity (number or null), "
                            "unit (exactly as written, or null), category "
                            "(produce/dairy/meat/seafood/bakery/pantry/spices/frozen/beverages), "
                            "raw_text (original line).\n"
                            "4. Set course to one of: breakfast, appetizer, soup, salad, main, "
                            "side, dessert, snack, beverage.\n"
                            "5. Estimate total calories (kcal), protein (g), fat (g), and carbs (g) "
                            "for the whole recipe as written (before dividing by servings). If the "
                            "text also explicitly states per-serving values, capture those in "
                            "calories_per_serving, protein_g_per_serving, fat_g_per_serving, "
                            "and carbs_g_per_serving.\n"
                            "6. Set is_vegetarian=true if the recipe contains no meat or seafood. "
                            "Set is_vegan=true if it also contains no animal products "
                            "(no dairy, eggs, honey, or other animal-derived ingredients)."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"/no_think\nExtract the recipe '{title}':\n\n{source_text}",
                    },
                ],
                schema=_EXTRACT_SCHEMA,
            )
        except Exception as exc:
            logger.exception("Extraction failed for '%s'", title)
            return ExtractedRecipe(
                title=title,
                source_pages=",".join(str(p) for p in pages),
                raw_source_text=source_text,
            )

        ingredients = [
            ExtractedIngredient(
                name=i.get("name", ""),
                quantity=i.get("quantity"),
                unit=i.get("unit"),
                category=i.get("category"),
                raw_text=i.get("raw_text"),
            )
            for i in data.get("ingredients", [])
        ]
        nutrition = data.get("nutrition") or {}
        return ExtractedRecipe(
            title=data.get("title", title),
            base_servings=data.get("servings"),
            course=data.get("course"),
            is_vegetarian=bool(data.get("is_vegetarian", False)),
            is_vegan=bool(data.get("is_vegan", False)),
            calories_total=nutrition.get("calories"),
            protein_total=nutrition.get("protein_g"),
            fat_total=nutrition.get("fat_g"),
            carbs_total=nutrition.get("carbs_g"),
            calories_per_serving_stated=nutrition.get("calories_per_serving"),
            protein_per_serving_stated=nutrition.get("protein_g_per_serving"),
            fat_per_serving_stated=nutrition.get("fat_g_per_serving"),
            carbs_per_serving_stated=nutrition.get("carbs_g_per_serving"),
            ingredients=ingredients,
            steps=data.get("steps", []),
            notes=data.get("notes"),
            source_pages=",".join(str(p) for p in pages),
            raw_source_text=source_text,
        )

