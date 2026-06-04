# Mealplanner

A self-hosted meal-planning webapp. Upload recipe PDFs (or other formats in the future), browse your recipe library, plan a week of meals, and generate a scaled shopping list. Recipe text is extracted by an LLM — either a local Ollama model or the Anthropic Claude API.

---

## Features

- **PDF import** — upload recipe books or single-recipe PDFs; the LLM segments and extracts each recipe automatically
- **Recipe library** — browse and search your full collection in a responsive card grid
- **Smart filters** — filter by course, dietary tags (vegetarian, vegan), calorie cap, protein target, favourites, and "want to try"; only filters with matching results are shown
- **Fraction quantities** — ingredient amounts like 0.5 or 0.33 are displayed as ½, ⅓, ¾, etc.
- **Serving scaler** — adjust the serving count on any recipe and all ingredient quantities update instantly
- **Nutrition display** — kcal and protein per serving shown on the recipe detail page, scaled live
- **Favourites & want-to-try** — bookmark recipes with ⭐ and 🔖 from both the grid and the detail page
- **Edit mode** — correct titles, ingredients, steps, course, and dietary tags after import
- **Weekly planner** — assign recipes to a 7×3 (day × meal-type) grid with per-slot serving counts
- **Shopping list** — auto-generated from the active plan, aggregated by ingredient and grouped by category, with checkboxes and a print view
- **Dark mode** — toggle between light and dark themes; preference is persisted in the browser
- **Upload decoupling** — file upload is instant and LLM-free; processing runs as a background task when the LLM is reachable
- **MCP server** — exposes recipes and plans as tools for AI assistants via the Model Context Protocol (no authentication, LAN-only)
- **No cloud required** — runs entirely on your own hardware; LLM can be local via Ollama

---

## Quick start

### With Docker Compose

```bash
cp backend/.env.example backend/.env   # set LLM_PROVIDER + API key or Ollama URL
docker compose up -d
# Open http://localhost:8000
```

### Development (hot-reload)

Requires Python 3.12+ and Node.js 20+.

```bash
cp backend/.env.example backend/.env   # configure LLM
make install-venv                      # first-time only (bootstraps pip)
make install                           # install backend + frontend deps
make dev                               # backend on :8000, frontend on :4200
```

---

## Configuration

All backend settings are environment variables. Copy `backend/.env.example` and edit:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `anthropic` | `anthropic` or `ollama` |
| `ANTHROPIC_API_KEY` | — | Required when using Anthropic. Get one at [console.anthropic.com](https://console.anthropic.com). Note: Pro/Max subscriptions do not include API credits — prepaid credits are billed separately. |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5-20251001` | Any Claude model ID |
| `ANTHROPIC_TIMEOUT` | `120` | Seconds to wait for an Anthropic API response |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint. Inside Docker use `http://host.docker.internal:11434` |
| `OLLAMA_MODEL` | `qwen3:4b` | Any model pulled in Ollama |
| `OLLAMA_TIMEOUT` | `600` | Seconds to wait for an Ollama response |
| `DATA_DIR` | `./data` | Directory for the SQLite database and uploaded files |
| `DISPLAY_TIMEZONE` | `Europe/Vienna` | IANA timezone name used for date display in the frontend |
| `DEFAULT_SERVINGS` | `2` | Initial serving count shown when opening any recipe |

> **Security:** The server has no built-in authentication. It is designed to run on a trusted local network. Do not expose it directly to the internet — if remote access is needed, place it behind a reverse proxy with authentication (e.g. Nginx, Caddy, Traefik).

---

## Docker deployment

Build and run a single container:

```bash
docker build -t mealplanner .

docker run -d \
  --name mealplanner \
  --restart unless-stopped \
  -p 8000:8000 \
  -v /path/to/data:/app/data \
  -e LLM_PROVIDER=anthropic \
  -e ANTHROPIC_API_KEY=sk-... \
  mealplanner

# Open http://localhost:8000
```

Or use the provided `docker-compose.yml`:

```bash
cp backend/.env.example backend/.env   # edit to taste
docker compose up -d
```

To push to your own registry, copy `.env.make.example` → `.env.make` and set `REGISTRY` and `IMAGE`, then:

```bash
make deploy    # multi-platform build + push
```

---

## MCP server

A separate Docker image (`Dockerfile.mcp`) exposes the mealplanner database as an MCP server over HTTP (Streamable HTTP transport). It has **no authentication** and is intended for use on a trusted local network.

### Tools exposed

| Tool | Description |
|------|-------------|
| `list_recipes` | List accepted recipes; optional filters: `course`, `is_vegetarian`, `is_vegan`, `is_favourite` |
| `get_recipe` | Full recipe detail including ingredients and steps |
| `create_recipe` | Create a recipe directly (no PDF import); ingredient quantities per person |
| `list_plans` | List all meal plans |
| `get_plan` | Plan detail with all entries |
| `create_plan` | Create a plan, optionally pre-populated with entries |
| `update_plan` | Rename a plan or replace its entries |
| `get_shopping_list` | Shopping list for a plan, scaled and grouped by category |

### Running the MCP server

The MCP container shares the same data volume as the main webapp:

```bash
docker build -f backend/Dockerfile.mcp -t mealplanner-mcp backend/

docker run -d \
  --name mealplanner-mcp \
  --restart unless-stopped \
  -p 8001:8001 \
  -v /path/to/data:/app/data \
  mealplanner-mcp
```

MCP endpoint: `http://<host>:8001/mcp`
Health check: `http://<host>:8001/health`

---

## How it works

### Import pipeline

1. **Upload** — file is stored and a `pending` import job is created (no LLM contact)
2. **Process** — triggered manually or automatically; the LLM segments the text into individual recipes, extracts structured data (title, ingredients with quantities and units, steps, course, dietary flags), and normalises units to metric
3. **Review** — extracted recipes are shown as drafts; accept all or pick individual ones

### Ingredient storage and scaling

Ingredients are stored **per person** (`book_quantity ÷ book_servings`). Scaling to N servings = `quantity_per_person × N`. Metric units (g, ml) are rounded to the nearest 5; culinary units (cup, tbsp, tsp) are rendered as fractions where appropriate.

A small hardcoded list of indivisible ingredients (currently: eggs) is rounded to the nearest integer in the display, with a minimum of 1 — e.g. 1.3 eggs shows as 1, 1.5 eggs shows as 2, and a sub-1 result (e.g. 1 egg across 3 people scaled to 1) still shows as 1. This list lives in `backend/app/models.py` (`WHOLE_UNIT_INGREDIENTS`) and takes effect immediately for all existing recipes without re-importing.

### Shopping list aggregation

`build_shopping_list()` scales all plan entries, converts units to metric, aggregates by normalised ingredient name and unit, and groups by category. No LLM is involved at serving time — everything is deterministic.

---

## Tech stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI, Python 3.12, SQLite via SQLModel |
| Frontend | Angular 21, standalone components, signals |
| LLM (import only) | Anthropic Claude API or local Ollama |
| Container | Docker (multi-stage, slim Python base) |

---

## Make targets

```
make install-venv    Bootstrap Python venv (first-time setup)
make install         Install backend + frontend dependencies
make dev             Start backend (:8000) + frontend (:4200) dev servers
make test            Run all tests (pytest + Vitest)
make build           Build Angular + Docker image
make deploy          Multi-platform build + push to registry
make release         Git tag + deploy
```

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
