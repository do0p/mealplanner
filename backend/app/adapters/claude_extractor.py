"""Anthropic-backed recipe extractor.

Single-pass per chunk via tool use: the model returns a list of fully
extracted recipes in one call (no separate segmentation/extraction phases).
Verification is deterministic-only (no LLM verify call). Each adapter call is
forced into a tool invocation which guarantees a valid JSON shape.
"""
import logging
import re
import time
from collections.abc import Callable

import anthropic

from app.config import settings
from app.ports.recipe_extractor import ExtractedIngredient, ExtractedRecipe, RecipeExtractor
from app.services.chunking import build_chunks

logger = logging.getLogger(__name__)


_EXTRACT_TOOL = {
    "name": "submit_recipes",
    "description": "Submit the complete list of recipes extracted from the document.",
    "input_schema": {
        "type": "object",
        "properties": {
            "recipes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "page_numbers": {"type": "array", "items": {"type": "integer"}},
                        "servings": {"type": "integer"},
                        "course": {
                            "type": "string",
                            "enum": [
                                "breakfast", "appetizer", "soup", "salad",
                                "main", "side", "dessert", "snack", "beverage",
                            ],
                        },
                        "ingredients": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "quantity": {"type": ["number", "null"]},
                                    "unit": {"type": ["string", "null"]},
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
                                "calories_per_serving": {"type": "number"},
                                "protein_g_per_serving": {"type": "number"},
                            },
                            "required": ["calories", "protein_g"],
                        },
                    },
                    "required": ["title", "page_numbers", "course", "ingredients", "steps", "nutrition"],
                },
            },
        },
        "required": ["recipes"],
    },
}

_IMAGE_SYSTEM_PROMPT = (
    "You are a recipe extraction assistant. Extract every recipe visible in the image, "
    "then call submit_recipes with full structured data. Rules:\n"
    "1. Copy instruction steps VERBATIM — do not paraphrase or convert anything.\n"
    "2. Ingredient quantities are as written in the recipe (for the stated "
    "serving size — do NOT divide them yourself).\n"
    "3. For each ingredient supply: name, quantity (number or null), "
    "unit (exactly as written, or null), category (produce/dairy/meat/seafood/bakery/"
    "pantry/spices/frozen/beverages), raw_text (original text).\n"
    "4. Set course to one of: breakfast, appetizer, soup, salad, main, "
    "side, dessert, snack, beverage.\n"
    "5. Estimate total calories (kcal) and protein (g) for the whole recipe "
    "as written (before dividing by servings). If the image explicitly states "
    "per-serving values, capture those in calories_per_serving and protein_g_per_serving.\n"
    "6. Set page_numbers to [1] for all recipes.\n"
    "7. Set is_vegetarian=true if the recipe contains no meat or seafood. "
    "Set is_vegan=true if it also contains no animal products "
    "(no dairy, eggs, honey, or other animal-derived ingredients)."
)

_SYSTEM_PROMPT = (
    "You are a recipe extraction assistant. For every recipe in the document, "
    "call submit_recipes with full structured data. Rules:\n"
    "1. Copy instruction steps VERBATIM — do not paraphrase or convert anything.\n"
    "2. Ingredient quantities are as written in the recipe (for the stated "
    "serving size — do NOT divide them yourself).\n"
    "3. For each ingredient supply: name, quantity (number or null), "
    "unit (exactly as written, or null), category (produce/dairy/meat/seafood/bakery/"
    "pantry/spices/frozen/beverages), raw_text (original line).\n"
    "4. Set course to one of: breakfast, appetizer, soup, salad, main, "
    "side, dessert, snack, beverage.\n"
    "5. Estimate total calories (kcal) and protein (g) for the whole recipe "
    "as written (before dividing by servings). If the text also explicitly states "
    "per-serving values, capture those in calories_per_serving and protein_g_per_serving.\n"
    "6. page_numbers must reference the [Page N] markers in the source text.\n"
    "7. Set is_vegetarian=true if the recipe contains no meat or seafood. "
    "Set is_vegan=true if it also contains no animal products "
    "(no dairy, eggs, honey, or other animal-derived ingredients)."
)


_SUPPORTED_MIME = {"image/jpeg", "image/png", "image/gif", "image/webp"}
_MAX_IMAGE_BYTES = 4_500_000  # leave headroom below Claude's 5 MB limit
_MAX_IMAGE_PX = 1568


def _image_media_type(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"GIF8":
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def _prepare_image(data: bytes) -> tuple[bytes, str]:
    """Return (image_bytes, mime_type) sized and formatted for Claude vision."""
    import io
    from PIL import Image

    mt = _image_media_type(data)
    needs_resize = len(data) > _MAX_IMAGE_BYTES
    needs_convert = mt not in _SUPPORTED_MIME

    if not needs_resize and not needs_convert:
        try:
            img = Image.open(io.BytesIO(data))
            if max(img.size) <= _MAX_IMAGE_PX:
                return data, mt
            needs_resize = True
        except Exception:
            return data, mt

    img = Image.open(io.BytesIO(data))
    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        img = bg
    elif img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    w, h = img.size
    if max(w, h) > _MAX_IMAGE_PX:
        ratio = _MAX_IMAGE_PX / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

    out_fmt = "PNG" if mt == "image/png" else "JPEG"
    out_mime = "image/png" if out_fmt == "PNG" else "image/jpeg"
    quality = 88
    while True:
        buf = io.BytesIO()
        save_kwargs: dict = {"format": out_fmt}
        if out_fmt == "JPEG":
            save_kwargs["quality"] = quality
        img.save(buf, **save_kwargs)
        if buf.tell() <= _MAX_IMAGE_BYTES or quality <= 40:
            return buf.getvalue(), out_mime
        quality -= 10


def _build_text(segments: list[tuple[int, str]]) -> str:
    return "\n\n".join(f"[Page {n}]\n{text}" for n, text in segments)


def _normalize_title(title: str) -> str:
    return re.sub(r"\W+", " ", title.lower()).strip()


class ClaudeRecipeExtractor(RecipeExtractor):

    def _client(self) -> anthropic.Anthropic:
        return anthropic.Anthropic(
            api_key=settings.anthropic_api_key,
            timeout=settings.anthropic_timeout,
        )

    def is_available(self) -> bool:
        if not settings.anthropic_api_key:
            return False
        try:
            self._client().models.list(limit=1)
            return True
        except Exception:
            logger.exception("Anthropic API unreachable")
            return False

    def extract_recipes(
        self,
        segments: list[tuple[int, str]],
        on_progress: Callable[[str, int, int], None] | None = None,
    ) -> list[ExtractedRecipe]:
        page_map = {n: text for n, text in segments}
        chunk_tokens = settings.anthropic_chunk_tokens
        _MIN_CHUNK_TOKENS = 1000

        # ── Phase 1: extraction with automatic chunk-size halving on truncation ─
        while True:
            ordered, truncated = self._run_extraction(segments, chunk_tokens, on_progress)
            if not truncated:
                break
            new_tokens = chunk_tokens // 2
            if new_tokens < _MIN_CHUNK_TOKENS:
                logger.error(
                    "Chunk size %d is already at/below the minimum (%d); "
                    "giving up — some recipes may be missing.",
                    chunk_tokens, _MIN_CHUNK_TOKENS,
                )
                break
            logger.warning(
                "Truncation detected; retrying extraction with chunk_tokens=%d → %d",
                chunk_tokens, new_tokens,
            )
            chunk_tokens = new_tokens

        for r in ordered:
            pages = [int(p) for p in (r.source_pages or "").split(",") if p.strip().isdigit()]
            r.raw_source_text = "\n\n".join(page_map[p] for p in pages if p in page_map)

        return ordered

    def _run_extraction(
        self,
        segments: list[tuple[int, str]],
        chunk_tokens: int,
        on_progress: Callable[[str, int, int], None] | None,
    ) -> tuple[list[ExtractedRecipe], bool]:
        """Extract all recipes using the given chunk_tokens budget.

        Returns (recipes, truncated) where truncated=True means at least one
        chunk hit the output token limit and the caller should retry with a
        smaller budget.
        """
        chunks = build_chunks(segments, chunk_tokens)
        total_chunks = len(chunks)
        logger.info(
            "Claude extract: %d chunk(s), budget %d tokens, model %s",
            total_chunks, chunk_tokens, settings.anthropic_model,
        )

        if on_progress:
            on_progress("extracting", 0, total_chunks)

        seen: dict[str, ExtractedRecipe] = {}
        ordered: list[ExtractedRecipe] = []
        any_truncated = False

        for i, chunk in enumerate(chunks):
            chunk_text = _build_text(chunk)
            recipes, truncated = self._extract_chunk(chunk_text, i + 1, total_chunks)
            if truncated:
                any_truncated = True

            for r in recipes:
                key = _normalize_title(r.title)
                if not key:
                    continue
                if key in seen:
                    existing = {p.strip() for p in (seen[key].source_pages or "").split(",") if p.strip()}
                    new = {p.strip() for p in (r.source_pages or "").split(",") if p.strip()}
                    merged = sorted(existing | new, key=lambda x: int(x) if x.isdigit() else 0)
                    seen[key].source_pages = ",".join(merged)
                else:
                    seen[key] = r
                    ordered.append(r)

            if on_progress:
                on_progress("extracting", i + 1, total_chunks)

        return ordered, any_truncated

    @property
    def supports_image_extraction(self) -> bool:
        return True

    def extract_from_image(
        self,
        data: bytes,
        on_progress: Callable[[str, int, int], None] | None = None,
    ) -> list[ExtractedRecipe]:
        import base64
        if on_progress:
            on_progress("extracting", 0, 1)

        image_bytes, mime_type = _prepare_image(data)
        b64 = base64.standard_b64encode(image_bytes).decode()
        logger.info("Claude image extract: %d bytes, mime=%s", len(image_bytes), mime_type)
        t0 = time.monotonic()
        try:
            resp = self._client().messages.create(
                model=settings.anthropic_model,
                max_tokens=settings.anthropic_max_output_tokens,
                system=_IMAGE_SYSTEM_PROMPT,
                tools=[_EXTRACT_TOOL],
                tool_choice={"type": "tool", "name": "submit_recipes"},
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": mime_type, "data": b64},
                        },
                        {"type": "text", "text": "Extract every recipe from this image."},
                    ],
                }],
            )
        except Exception:
            logger.exception("Claude image extract: API call failed")
            raise

        elapsed = time.monotonic() - t0
        logger.info(
            "Claude image extract: %.1fs, in=%d out=%d tokens, stop_reason=%s",
            elapsed, resp.usage.input_tokens, resp.usage.output_tokens, resp.stop_reason,
        )

        tool_block = next((b for b in resp.content if b.type == "tool_use"), None)
        if tool_block is None:
            logger.warning("Claude image extract: no tool_use block in response")
            if on_progress:
                on_progress("extracting", 1, 1)
            return []

        raw_recipes = tool_block.input.get("recipes", [])
        result: list[ExtractedRecipe] = []
        for data_item in (raw_recipes if isinstance(raw_recipes, list) else []):
            if not isinstance(data_item, dict):
                continue
            ingredients = [
                ExtractedIngredient(
                    name=ing.get("name", ""),
                    quantity=ing.get("quantity"),
                    unit=ing.get("unit"),
                    category=ing.get("category"),
                    raw_text=ing.get("raw_text"),
                )
                for ing in (data_item.get("ingredients") or [])
                if isinstance(ing, dict)
            ]
            nutrition = data_item.get("nutrition") or {}
            result.append(ExtractedRecipe(
                title=data_item.get("title", "Untitled"),
                base_servings=data_item.get("servings"),
                course=data_item.get("course"),
                is_vegetarian=bool(data_item.get("is_vegetarian", False)),
                is_vegan=bool(data_item.get("is_vegan", False)),
                calories_total=nutrition.get("calories"),
                protein_total=nutrition.get("protein_g"),
                calories_per_serving_stated=nutrition.get("calories_per_serving"),
                protein_per_serving_stated=nutrition.get("protein_g_per_serving"),
                ingredients=ingredients,
                steps=data_item.get("steps", []),
                notes=data_item.get("notes"),
                source_pages="1",
            ))

        logger.info("Claude image extract: %d recipe(s) extracted", len(result))
        if on_progress:
            on_progress("extracting", 1, 1)
        return result

    def _extract_chunk(
        self, chunk_text: str, idx: int, total: int
    ) -> tuple[list[ExtractedRecipe], bool]:
        """Return (recipes, truncated). truncated=True when output hit max_tokens."""
        logger.info(
            "Claude chunk %d/%d: sending %d chars (~%d tokens)",
            idx, total, len(chunk_text), len(chunk_text) // 4,
        )
        t0 = time.monotonic()
        try:
            resp = self._client().messages.create(
                model=settings.anthropic_model,
                max_tokens=settings.anthropic_max_output_tokens,
                system=_SYSTEM_PROMPT,
                tools=[_EXTRACT_TOOL],
                tool_choice={"type": "tool", "name": "submit_recipes"},
                messages=[
                    {
                        "role": "user",
                        "content": f"Extract every recipe from this document text:\n\n{chunk_text}",
                    },
                ],
            )
        except Exception:
            logger.exception("Claude chunk %d/%d: API call failed", idx, total)
            raise

        elapsed = time.monotonic() - t0
        truncated = resp.stop_reason == "max_tokens"
        logger.info(
            "Claude chunk %d/%d: response in %.1fs, in=%d out=%d tokens, stop_reason=%s",
            idx, total, elapsed,
            resp.usage.input_tokens, resp.usage.output_tokens, resp.stop_reason,
        )

        if truncated:
            logger.warning(
                "Claude chunk %d/%d: output truncated at %d tokens — will retry with smaller chunks.",
                idx, total, resp.usage.output_tokens,
            )
            return [], True

        tool_block = next((b for b in resp.content if b.type == "tool_use"), None)
        if tool_block is None:
            logger.warning("Claude chunk %d/%d: no tool_use block in response", idx, total)
            return [], False

        raw_recipes = tool_block.input.get("recipes", [])
        if not isinstance(raw_recipes, list):
            logger.warning(
                "Claude chunk %d/%d: 'recipes' field is %s, not a list — skipping chunk",
                idx, total, type(raw_recipes).__name__,
            )
            return [], False

        logger.info(
            "Claude chunk %d/%d: extracted %d recipe(s)", idx, total, len(raw_recipes),
        )

        result: list[ExtractedRecipe] = []
        for data in raw_recipes:
            if not isinstance(data, dict):
                logger.warning(
                    "Claude chunk %d/%d: recipe item is %s, not a dict — skipping",
                    idx, total, type(data).__name__,
                )
                continue
            ingredients_raw = data.get("ingredients", [])
            ingredients = [
                ExtractedIngredient(
                    name=ing.get("name", ""),
                    quantity=ing.get("quantity"),
                    unit=ing.get("unit"),
                    category=ing.get("category"),
                    raw_text=ing.get("raw_text"),
                )
                for ing in (ingredients_raw if isinstance(ingredients_raw, list) else [])
                if isinstance(ing, dict)
            ]
            nutrition = data.get("nutrition") or {}
            pages = data.get("page_numbers") or []
            result.append(ExtractedRecipe(
                title=data.get("title", "Untitled"),
                base_servings=data.get("servings"),
                course=data.get("course"),
                is_vegetarian=bool(data.get("is_vegetarian", False)),
                is_vegan=bool(data.get("is_vegan", False)),
                calories_total=nutrition.get("calories"),
                protein_total=nutrition.get("protein_g"),
                calories_per_serving_stated=nutrition.get("calories_per_serving"),
                protein_per_serving_stated=nutrition.get("protein_g_per_serving"),
                ingredients=ingredients,
                steps=data.get("steps", []),
                notes=data.get("notes"),
                source_pages=",".join(str(p) for p in pages),
            ))
        return result, False
