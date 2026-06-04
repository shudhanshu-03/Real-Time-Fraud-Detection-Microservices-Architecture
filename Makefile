.PHONY: setup test lint format build up down logs migrate proto seed clean

setup:
	pip install -r requirements.txt

test:
	pytest

lint:
	ruff check .
	mypy .

format:
	ruff format .

build:
	docker-compose build

up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f

migrate:
	echo "Running migrations..."

proto:
	python -m grpc_tools.protoc -I./proto --python_out=./shared/fraud_common/pb --grpc_python_out=./shared/fraud_common/pb ./proto/*.proto

seed:
	python scripts/seed-data.py

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
