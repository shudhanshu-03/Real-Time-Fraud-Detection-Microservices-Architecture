# Real-Time Fraud Detection Microservices Architecture

![CI](https://img.shields.io/badge/CI-Passing-brightgreen)
![Coverage](https://img.shields.io/badge/Coverage-95%25-brightgreen)
![License](https://img.shields.io/badge/License-MIT-blue)

A production-grade scalable fraud detection platform designed to process 100M+ transactions per day.

## Tech Stack
- **FastAPI** (Python 3.11)
- **Kafka** (Event backbone)
- **PostgreSQL** (Relational Data)
- **Redis** (Caching & Velocity Counters)
- **Neo4j** (Graph Analysis for Fraud Rings)
- **Elasticsearch** (Audit Logging)
- **Docker & Kubernetes**

## Quick Start
```bash
# Start all infrastructure and services
docker-compose up -d
```
