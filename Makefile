VERSION := $(shell cat VERSION)
REGISTRY ?= localhost:5000
IMAGE ?= mealplanner

-include .env.make

.PHONY: help install install-venv dev dev-backend dev-frontend test test-backend test-frontend build build-frontend build-backend deploy release clean

help:
	@echo "Available commands:"
	@echo "  make install-venv    - Bootstrap Python venv (first-time setup)"
	@echo "  make install         - Install backend pip deps + frontend npm deps"
	@echo "  make dev             - Run backend + frontend dev servers"
	@echo "  make dev-backend     - Run FastAPI dev server (http://localhost:8000)"
	@echo "  make dev-frontend    - Run Angular dev server (http://localhost:4200)"
	@echo "  make test            - Run all tests"
	@echo "  make test-backend    - Run backend pytest"
	@echo "  make test-frontend   - Run frontend Vitest"
	@echo "  make build           - Build frontend + Docker image"
	@echo "  make build-frontend  - Build Angular (outputs to backend/frontend-dist)"
	@echo "  make build-backend   - Build Docker image"
	@echo "  make deploy          - Multi-platform build + push to registry"
	@echo "  make release         - Git tag + deploy"
	@echo "  make clean           - Remove build artifacts"

install-venv:
	python3 -m venv --without-pip backend/.venv
	curl -sSL https://bootstrap.pypa.io/get-pip.py | backend/.venv/bin/python

install:
	cd backend && .venv/bin/pip install -r requirements.txt
	cd frontend && npm install

dev:
	cd backend && DATA_DIR=./data .venv/bin/uvicorn app.main:app --reload &
	cd frontend && npm start

dev-backend:
	cd backend && DATA_DIR=./data .venv/bin/uvicorn app.main:app --reload

dev-frontend:
	cd frontend && npm start

test: test-backend test-frontend

test-backend:
	cd backend && .venv/bin/python -m pytest

test-frontend:
	cd frontend && npm test

build: build-frontend build-backend

build-frontend:
	printf "export const APP_VERSION = '$(VERSION)';\n" > frontend/src/app/version.ts
	cd frontend && npm run build

build-backend:
	docker build -t $(IMAGE):$(VERSION) -t $(IMAGE):latest .

deploy:
	docker buildx build --platform linux/amd64,linux/arm64 \
		--output "type=image,name=$(REGISTRY)/$(IMAGE):$(VERSION),push=true,registry.insecure=true" .
	docker buildx build --platform linux/amd64,linux/arm64 \
		--output "type=image,name=$(REGISTRY)/$(IMAGE):latest,push=true,registry.insecure=true" .

release:
	git tag v$(VERSION)
	git push origin v$(VERSION)
	$(MAKE) deploy

clean:
	cd backend && rm -rf .pytest_cache __pycache__ frontend-dist data
	cd frontend && rm -rf dist node_modules .angular
	docker image rm $(IMAGE) 2>/dev/null || true
