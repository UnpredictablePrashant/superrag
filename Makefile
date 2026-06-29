.PHONY: up down migrate api-test web-test lint e2e

up:
	docker compose up --build

down:
	docker compose down

migrate:
	docker compose exec api alembic upgrade head

api-test:
	docker compose exec api pytest

web-test:
	docker compose exec web npm run test

lint:
	docker compose exec web npm run lint
	docker compose exec api ruff check app tests

e2e:
	npm run e2e
