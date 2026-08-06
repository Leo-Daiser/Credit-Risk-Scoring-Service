up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

test:
	pytest -q

migrate:
	python -m src.db.migrate

train:
	python -m src.cli train-catboost
	python -m src.cli prepare-production-model

batch:
	python -m src.cli batch-score

monitor:
	python -m src.cli monitor-drift

api:
	uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
