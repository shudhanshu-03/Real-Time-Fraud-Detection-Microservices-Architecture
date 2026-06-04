# Real-Time Fraud Detection Microservices Architecture

![CI](https://img.shields.io/badge/CI-Passing-brightgreen)
![Coverage](https://img.shields.io/badge/Coverage-95%25-brightgreen)
![License](https://img.shields.io/badge/License-Non--Commercial-red)

A production-grade, highly scalable fraud detection platform designed to process 100M+ transactions per day. This event-driven system ingests streams of transactions, applies rule-based heuristics, evaluates machine learning models, and analyzes graph relationships to assign fraud scores dynamically in real time.

## 🏗️ Architecture Overview

The platform relies on an event-driven design, utilizing **Apache Kafka** for asynchronous messaging and **gRPC** for low-latency synchronous internal calls. The entire stack is containerized and orchestratable via **Kubernetes**.

### High-Level Data Flow
1. **API Gateway** receives incoming transaction streams.
2. **Transaction Service** validates and normalizes the payload.
3. The **Stream Processor** rapidly evaluates velocity and aggregates metrics.
4. The **Fraud Orchestrator** aggregates scoring data from multiple evaluation engines asynchronously:
   - **Rule Engine**
   - **ML Scoring**
   - **Graph Analysis**
5. If the aggregate score crosses a predefined threshold, the **Alert Service** and **Case Management** are triggered.
6. **Notification Service** dispatches alerts to the appropriate channels.

## 🚀 Core Microservices

- **API Gateway**: Entry point for all external requests, handling authentication, rate-limiting, and correlation IDs.
- **Transaction Service**: Manages incoming transactions and acts as the initial router.
- **Stream Processor**: Rapidly calculates velocity aggregations and metrics over streaming data.
- **Fraud Orchestrator**: Aggregates scoring data from multiple engines to compute a final fraud decision.
- **Rule Engine**: Evaluates static heuristics and pre-defined business rules.
- **ML Scoring**: Serves machine learning models to detect anomalous patterns and predict fraud probabilities.
- **Graph Analysis**: Utilizes Neo4j to analyze network relationships (e.g., shared IPs, devices, or accounts) to uncover fraud rings.
- **Customer Profile**: Maintains customer state, history, and provides dashboard visualizations.
- **Alert Service**: Triggers and logs alerts for highly suspicious activities.
- **Case Management**: Provides endpoints and workflows for human analysts to review and resolve flagged transactions.
- **Notification Service**: Dispatches alerts via Email, SMS, Slack, or Webhooks.

## 🛠️ Technology Stack

- **Language**: Python 3.11
- **API Framework**: FastAPI
- **Event Broker**: Apache Kafka (with Avro Schemas)
- **RPC**: gRPC & Protocol Buffers (`.proto`)
- **Databases/Storage**: 
  - PostgreSQL (Relational Data)
  - Redis (Caching & Fast Lookups, Velocity Counters)
  - Neo4j (Graph Data for Fraud Rings)
  - Elasticsearch (Audit Logging & Search)
- **Infrastructure**: Docker, Kubernetes (Kustomize overlays for dev/staging/prod)

## ⚙️ Quick Start

### Local Execution (Docker Compose)
To start all infrastructure and services locally:

```bash
# Start all infrastructure and services
docker-compose up -d
```

*Alternatively, you can run the bootstrap scripts provided in the `scripts/` directory:*
```bash
# Unix / Linux
./scripts/setup-local.sh

# Windows
./scripts/setup-local.ps1
```

### Kubernetes Deployment
The infrastructure is managed via Kubernetes using `kustomize`.
```bash
# Deploy base resources
kubectl apply -k infrastructure/kubernetes/base

# Deploy dev overlay
kubectl apply -k infrastructure/kubernetes/overlays/dev
```

## 📜 Schemas and Protobufs
- **Kafka Topics**: Managed with Avro schemas located in `schemas/avro/`.
- **gRPC Services**: Protobuf definitions located in `proto/`.

## ⚖️ License & Limitations
This software is licensed under a **Custom Non-Commercial License**. 
You are free to make copies, study, and modify the code for personal or educational use. However, you may **NOT** sell, sublicense, or distribute this software for commercial purposes or financial gain without explicit prior written permission. See the `LICENSE` file for full details.