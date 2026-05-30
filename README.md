# Meal Planner

A personal meal-planning webapp. Upload recipe PDFs, browse your recipe library, plan a week of meals, and generate a scaled shopping list.

## Features

- **PDF import** — upload recipe books; text is extracted and parsed by an LLM (Claude or Ollama)
- **Recipe library** — browse, search, and filter recipes by course, calories, and protein
- **Weekly planner** — drag recipes into a 7-day grid
- **Shopping list** — auto-generated, scaled to your chosen serving count, grouped by category

## Stack

- **Backend** — FastAPI, Python 3.12, SQLite via SQLModel
- **Frontend** — Angular 21, standalone components, signals
- **LLM** — Anthropic Claude (default) or local Ollama model for recipe extraction

## Quick start

```bash
cp backend/.env.example backend/.env   # add your ANTHROPIC_API_KEY
make install-venv                      # first-time only
make install
make dev                               # backend :8000, frontend :4200
```

## Configuration

Backend is configured via `backend/.env` (see `backend/.env.example`):

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `anthropic` | `anthropic` or `ollama` |
| `ANTHROPIC_API_KEY` | — | Required when using Anthropic |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5-20251001` | |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | |
| `OLLAMA_MODEL` | `qwen3:4b` | |
| `DATA_DIR` | `./data` | SQLite DB + uploaded files |

## Build & deploy

Copy `.env.make.example` and set your registry:

```bash
cp .env.make.example .env.make   # set REGISTRY and IMAGE
make deploy                       # build amd64 + push to registry
```

## Commands

```
make dev             # start dev servers
make test            # run all tests
make build           # build Docker image
make deploy          # build + push to registry
make release         # tag + deploy
```
