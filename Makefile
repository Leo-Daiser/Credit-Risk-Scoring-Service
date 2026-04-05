up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

test:
	pytest -q

api:
	uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload