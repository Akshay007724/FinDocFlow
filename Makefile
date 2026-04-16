.PHONY: up down build pull-model k8s-deploy k8s-delete test lint

# ── Docker Compose ─────────────────────────────────────────────────────────

up:
	docker compose up -d --build

down:
	docker compose down -v

build:
	docker compose build

logs:
	docker compose logs -f --tail=100

pull-model:
	docker compose exec ollama ollama pull llava

# ── Kubernetes ─────────────────────────────────────────────────────────────

k8s-deploy:
	kubectl apply -f k8s/namespace.yaml
	kubectl apply -f k8s/configmap.yaml
	kubectl apply -f k8s/secret.yaml
	kubectl apply -f k8s/redis/deployment.yaml
	kubectl apply -f k8s/kafka/deployment.yaml
	kubectl apply -f k8s/minio/deployment.yaml
	kubectl apply -f k8s/neo4j/deployment.yaml
	kubectl apply -f k8s/ollama/deployment.yaml
	kubectl apply -f k8s/ingestion/deployment.yaml
	kubectl apply -f k8s/extraction/deployment.yaml
	kubectl apply -f k8s/entity-linking/deployment.yaml
	kubectl apply -f k8s/reasoning/deployment.yaml
	kubectl apply -f k8s/frontend/deployment.yaml

k8s-delete:
	kubectl delete namespace findocflow

k8s-status:
	kubectl get pods -n findocflow
	kubectl get svc -n findocflow

# ── Development ─────────────────────────────────────────────────────────────

install-dev:
	pip install -r services/ingestion_service/requirements.txt
	pip install -r services/reasoning_service/requirements.txt
	pip install pytest httpx

test:
	pytest experiments/ -v

lint:
	ruff check services/ pipeline/ experiments/
	ruff format --check services/ pipeline/ experiments/

# ── Dataset & Experiments ────────────────────────────────────────────────────

collect-dataset:
	python dataset/collector.py

evaluate:
	python experiments/evaluate.py --model full

ablation:
	python experiments/ablation.py
