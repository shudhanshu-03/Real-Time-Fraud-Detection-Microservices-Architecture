#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Fraud Detection Platform - Local Development Environment Setup
# ==============================================================================
# This script bootstraps the entire local development stack including:
#   - Infrastructure services (Postgres, Redis, Kafka, Neo4j, Elasticsearch)
#   - Schema Registry & Kafka UI
#   - Kafka topic creation
#   - All application microservices
#
# Usage:
#   chmod +x scripts/setup-local.sh
#   ./scripts/setup-local.sh
#
# Prerequisites:
#   - Docker & Docker Compose (v2)
#   - Python 3.8+
# ==============================================================================

# ---------------------------------------------------------------------------
# Color Constants
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DOCKER_COMPOSE_FILE="${PROJECT_ROOT}/infrastructure/docker/docker-compose.yml"

# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------
log_info()    { echo -e "${BLUE}[INFO]${NC}    $*"; }
log_success() { echo -e "${GREEN}[OK]${NC}      $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}    $*"; }
log_error()   { echo -e "${RED}[ERROR]${NC}   $*"; }
log_step()    { echo -e "\n${MAGENTA}${BOLD}▸ Step $1:${NC} ${BOLD}$2${NC}"; }

print_banner() {
    echo -e "${CYAN}${BOLD}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                                                            ║"
    echo "║       🛡️  Fraud Detection Platform — Local Setup  🛡️        ║"
    echo "║                                                            ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo -e "${BLUE}  Bootstrapping the complete local development environment${NC}"
    echo -e "${BLUE}  $(date '+%Y-%m-%d %H:%M:%S %Z')${NC}"
    echo ""
}

# ---------------------------------------------------------------------------
# wait_for_service  <container_name>  <timeout_seconds>
#   Polls "docker inspect --format='{{.State.Health.Status}}'" until the
#   container reports "healthy" or the timeout is reached.
# ---------------------------------------------------------------------------
wait_for_service() {
    local container="$1"
    local timeout="${2:-120}"
    local elapsed=0
    local interval=3

    printf "  ⏳  Waiting for ${BOLD}%-20s${NC}" "${container}..."
    while [ $elapsed -lt $timeout ]; do
        local status
        status=$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || echo "not_found")

        if [ "$status" = "healthy" ]; then
            echo -e " ${GREEN}✔  healthy${NC} (${elapsed}s)"
            return 0
        fi

        sleep "$interval"
        elapsed=$((elapsed + interval))
    done

    echo -e " ${RED}✘  timeout after ${timeout}s${NC}"
    log_error "Service '${container}' did not become healthy within ${timeout}s"
    return 1
}

# ---------------------------------------------------------------------------
# docker_compose  — wrapper that picks docker compose v2 or v1 automatically
# ---------------------------------------------------------------------------
COMPOSE_CMD=""

detect_compose() {
    if docker compose version &>/dev/null; then
        COMPOSE_CMD="docker compose"
    elif command -v docker-compose &>/dev/null; then
        COMPOSE_CMD="docker-compose"
    else
        log_error "Neither 'docker compose' (v2) nor 'docker-compose' (v1) found."
        exit 1
    fi
    log_info "Using compose command: ${BOLD}${COMPOSE_CMD}${NC}"
}

dc() {
    # shellcheck disable=SC2086
    $COMPOSE_CMD -f "$DOCKER_COMPOSE_FILE" "$@"
}

# ==============================================================================
# Pre-flight Checks
# ==============================================================================
print_banner

log_info "Running pre-flight checks…"

# Docker
if ! command -v docker &>/dev/null; then
    log_error "Docker is not installed. Please install Docker Desktop: https://docs.docker.com/get-docker/"
    exit 1
fi
log_success "Docker found: $(docker --version)"

# Docker Compose
detect_compose

# Python 3
if command -v python3 &>/dev/null; then
    log_success "Python 3 found: $(python3 --version)"
elif command -v python &>/dev/null && python --version 2>&1 | grep -q "Python 3"; then
    log_success "Python 3 found: $(python --version)"
else
    log_warn "Python 3 not found — you can still run infrastructure, but seed-data.py requires Python 3."
fi

# Docker daemon running?
if ! docker info &>/dev/null; then
    log_error "Docker daemon is not running. Please start Docker Desktop and try again."
    exit 1
fi
log_success "Docker daemon is running"

# ==============================================================================
# Step 0 — Environment File
# ==============================================================================
log_step 0 "Preparing environment file"

ENV_FILE="${PROJECT_ROOT}/.env"
ENV_EXAMPLE="${PROJECT_ROOT}/.env.example"

if [ ! -f "$ENV_EXAMPLE" ]; then
    log_info "Creating sample .env.example…"
    cat > "$ENV_EXAMPLE" <<'ENVEOF'
# ==============================================================================
# Fraud Detection Platform — Environment Variables
# ==============================================================================

# --- Postgres ------------------------------------------------------------------
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=fraud_detection
POSTGRES_USER=fraud_admin
POSTGRES_PASSWORD=fraud_secret_change_me

# --- Redis ---------------------------------------------------------------------
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=redis_secret_change_me

# --- Kafka ---------------------------------------------------------------------
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_SCHEMA_REGISTRY_URL=http://localhost:8081

# --- Neo4j ---------------------------------------------------------------------
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=neo4j_secret_change_me

# --- Elasticsearch -------------------------------------------------------------
ELASTICSEARCH_HOST=localhost
ELASTICSEARCH_PORT=9200

# --- API Gateway ---------------------------------------------------------------
API_GATEWAY_PORT=8000
API_BASE_URL=http://localhost:8000

# --- JWT / Auth ----------------------------------------------------------------
JWT_SECRET=super_secret_jwt_key_change_in_prod
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=60

# --- ML Scoring ----------------------------------------------------------------
ML_MODEL_PATH=/models/fraud_model_v1.pkl
ML_SCORING_THRESHOLD=0.75

# --- Logging -------------------------------------------------------------------
LOG_LEVEL=INFO
ENVEOF
    log_success ".env.example created"
fi

if [ ! -f "$ENV_FILE" ]; then
    log_info "Creating .env from .env.example…"
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    log_success ".env file created — review and update secrets before production use"
else
    log_success ".env file already exists"
fi

# ==============================================================================
# Step 1 — Build Docker Images
# ==============================================================================
log_step 1 "Building all Docker images"
dc build --parallel 2>&1 | tail -5
log_success "Docker images built"

# ==============================================================================
# Step 2 — Start Infrastructure Services
# ==============================================================================
log_step 2 "Starting infrastructure services"

INFRA_SERVICES=(postgres redis kafka neo4j elasticsearch)
dc up -d "${INFRA_SERVICES[@]}"
log_success "Infrastructure containers started"

# ==============================================================================
# Step 3 — Wait for Infrastructure Health Checks
# ==============================================================================
log_step 3 "Waiting for infrastructure health checks"

HEALTH_TIMEOUT=180

wait_for_service "fraud-postgres"       "$HEALTH_TIMEOUT"
wait_for_service "fraud-redis"          "$HEALTH_TIMEOUT"
wait_for_service "fraud-kafka"          "$HEALTH_TIMEOUT"
wait_for_service "fraud-neo4j"          "$HEALTH_TIMEOUT"
wait_for_service "fraud-elasticsearch"  "$HEALTH_TIMEOUT"

log_success "All infrastructure services are healthy"

# ==============================================================================
# Step 4 — Start Schema Registry & Kafka UI
# ==============================================================================
log_step 4 "Starting Schema Registry & Kafka UI"

dc up -d schema-registry kafka-ui
sleep 5
log_success "Schema Registry and Kafka UI started"

# ==============================================================================
# Step 5 — Create Kafka Topics
# ==============================================================================
log_step 5 "Creating Kafka topics"

TOPICS_SCRIPT="${SCRIPT_DIR}/create-kafka-topics.sh"

if [ -f "$TOPICS_SCRIPT" ] && [ -x "$TOPICS_SCRIPT" ]; then
    bash "$TOPICS_SCRIPT"
else
    log_info "Running inline topic creation…"
    dc exec -T kafka kafka-topics --bootstrap-server localhost:9092 --create --if-not-exists --topic transaction.raw             --partitions 30 --replication-factor 1 2>/dev/null || true
    dc exec -T kafka kafka-topics --bootstrap-server localhost:9092 --create --if-not-exists --topic transaction.validated       --partitions 30 --replication-factor 1 2>/dev/null || true
    dc exec -T kafka kafka-topics --bootstrap-server localhost:9092 --create --if-not-exists --topic transaction.enriched        --partitions 20 --replication-factor 1 2>/dev/null || true
    dc exec -T kafka kafka-topics --bootstrap-server localhost:9092 --create --if-not-exists --topic fraud.scoring.requests      --partitions 20 --replication-factor 1 2>/dev/null || true
    dc exec -T kafka kafka-topics --bootstrap-server localhost:9092 --create --if-not-exists --topic fraud.scoring.results       --partitions 20 --replication-factor 1 2>/dev/null || true
    dc exec -T kafka kafka-topics --bootstrap-server localhost:9092 --create --if-not-exists --topic fraud.alerts                --partitions 10 --replication-factor 1 2>/dev/null || true
    dc exec -T kafka kafka-topics --bootstrap-server localhost:9092 --create --if-not-exists --topic fraud.alerts.high-priority  --partitions 10 --replication-factor 1 2>/dev/null || true
    dc exec -T kafka kafka-topics --bootstrap-server localhost:9092 --create --if-not-exists --topic fraud.cases                 --partitions 10 --replication-factor 1 2>/dev/null || true
    dc exec -T kafka kafka-topics --bootstrap-server localhost:9092 --create --if-not-exists --topic notification.email           --partitions 10 --replication-factor 1 2>/dev/null || true
    dc exec -T kafka kafka-topics --bootstrap-server localhost:9092 --create --if-not-exists --topic notification.sms             --partitions 10 --replication-factor 1 2>/dev/null || true
    dc exec -T kafka kafka-topics --bootstrap-server localhost:9092 --create --if-not-exists --topic notification.webhook         --partitions 10 --replication-factor 1 2>/dev/null || true
    dc exec -T kafka kafka-topics --bootstrap-server localhost:9092 --create --if-not-exists --topic audit.events                --partitions 20 --replication-factor 1 2>/dev/null || true
    dc exec -T kafka kafka-topics --bootstrap-server localhost:9092 --create --if-not-exists --topic monitoring.metrics           --partitions 10 --replication-factor 1 2>/dev/null || true
fi

log_success "Kafka topics created"

# ==============================================================================
# Step 6 — Start Application Services
# ==============================================================================
log_step 6 "Starting application microservices"

APP_SERVICES=(
    api-gateway
    transaction-service
    fraud-orchestrator
    rule-engine
    ml-scoring
    graph-analysis
    alert-service
    case-management
    notification-service
    audit-service
    monitoring-service
)

dc up -d "${APP_SERVICES[@]}"
log_success "Application containers started"

# ==============================================================================
# Step 7 — Wait for Application Health Checks
# ==============================================================================
log_step 7 "Waiting for application health checks"

APP_HEALTH_TIMEOUT=120

wait_for_service "fraud-api-gateway"         "$APP_HEALTH_TIMEOUT" || true
wait_for_service "fraud-transaction-service"  "$APP_HEALTH_TIMEOUT" || true
wait_for_service "fraud-orchestrator"         "$APP_HEALTH_TIMEOUT" || true
wait_for_service "fraud-rule-engine"          "$APP_HEALTH_TIMEOUT" || true
wait_for_service "fraud-ml-scoring"           "$APP_HEALTH_TIMEOUT" || true
wait_for_service "fraud-graph-analysis"       "$APP_HEALTH_TIMEOUT" || true
wait_for_service "fraud-alert-service"        "$APP_HEALTH_TIMEOUT" || true
wait_for_service "fraud-case-management"      "$APP_HEALTH_TIMEOUT" || true
wait_for_service "fraud-notification-service" "$APP_HEALTH_TIMEOUT" || true
wait_for_service "fraud-audit-service"        "$APP_HEALTH_TIMEOUT" || true
wait_for_service "fraud-monitoring-service"   "$APP_HEALTH_TIMEOUT" || true

# ==============================================================================
# Summary
# ==============================================================================
echo ""
echo -e "${CYAN}${BOLD}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                                                            ║"
echo "║         ✅  Local Environment Ready!                       ║"
echo "║                                                            ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║                                                            ║"
echo "║  Service URLs:                                             ║"
echo "║  ─────────────────────────────────────────────────────────  ║"
echo "║  API Gateway          http://localhost:8000                 ║"
echo "║  API Docs (Swagger)   http://localhost:8000/docs            ║"
echo "║  Kafka UI             http://localhost:9090                 ║"
echo "║  Neo4j Browser        http://localhost:7474                 ║"
echo "║  Elasticsearch        http://localhost:9200                 ║"
echo "║  Schema Registry      http://localhost:8081                 ║"
echo "║                                                            ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║                                                            ║"
echo "║  Next Steps:                                               ║"
echo "║  1. Seed test data:   python3 scripts/seed-data.py         ║"
echo "║  2. View API docs:    open http://localhost:8000/docs       ║"
echo "║  3. Monitor Kafka:    open http://localhost:9090            ║"
echo "║  4. View logs:        docker compose logs -f <service>     ║"
echo "║                                                            ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"
