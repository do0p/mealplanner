"""Page-level chunking shared by all LLM-backed RecipeExtractor adapters.

Each adapter passes its own token_budget — small for local models with limited
context or slow CPU prefill, large for hosted APIs with big context windows.
When the whole document fits in the budget, this returns a single chunk.
"""
import logging

logger = logging.getLogger(__name__)


def estimate_tokens(text: str) -> int:
    """Rough heuristic: ~4 characters per token for English prose."""
    return len(text) // 4


def build_chunks(
    segments: list[tuple[int, str]],
    token_budget: int,
) -> list[list[tuple[int, str]]]:
    """Split (page, text) segments into chunks that fit token_budget.

    Accumulates pages until adding the next would exceed the budget, then emits
    the chunk and starts the next one with a 1-page overlap so recipes that span
    a boundary remain fully visible in both chunks. Returns a single chunk when
    the whole document fits.
    """
    if not segments:
        return []

    page_map = {p: text for p, text in segments}
    sorted_pages = sorted(page_map)

    logger.info(
        "build_chunks: %d pages, budget %d tokens, avg %.0f tokens/page",
        len(sorted_pages),
        token_budget,
        sum(estimate_tokens(t) for t in page_map.values()) / len(sorted_pages),
    )

    chunks: list[list[tuple[int, str]]] = []
    current: list[int] = []
    current_tokens = 0

    for page in sorted_pages:
        page_tokens = estimate_tokens(page_map.get(page, ""))

        if current and current_tokens + page_tokens > token_budget:
            chunks.append([(p, page_map[p]) for p in current])
            logger.info(
                "build_chunks: chunk %d → pages %d-%d, ~%d tokens",
                len(chunks), current[0], current[-1], current_tokens,
            )
            if len(current) > 1:
                current = [current[-1]]
                current_tokens = estimate_tokens(page_map.get(current[0], ""))
            else:
                current = []
                current_tokens = 0

        current.append(page)
        current_tokens += page_tokens

    if current:
        chunks.append([(p, page_map[p]) for p in current])
        logger.info(
            "build_chunks: chunk %d → pages %d-%d, ~%d tokens",
            len(chunks), current[0], current[-1], current_tokens,
        )

    result = chunks if chunks else [list(segments)]
    logger.info("build_chunks: %d chunk(s) total", len(result))
    return result
