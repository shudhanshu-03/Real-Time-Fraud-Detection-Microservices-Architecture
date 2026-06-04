#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Fraud Detection Platform — Kafka Topic Provisioner
# ==============================================================================
# Creates all required Kafka topics for the fraud detection event pipeline.
#
# Usage:
#   # From host (via docker exec):
#   docker exec fraud-kafka bash /scripts/create-kafka-topics.sh
#
#   # Directly inside the Kafka container:
#   ./create-kafka-topics.sh
#
#   # With custom replication factor (e.g. for staging/prod):
#   ./create-kafka-topics.sh --replication-factor 3
#
# Environment Variables:
#   KAFKA_BOOTSTRAP_SERVER  - Bootstrap server address (default: localhost:9092)
# ==============================================================================

# ---------------------------------------------------------------------------
# Color Constants
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Configuration

KAFKA_BOOTSTRAP_SERVER="${KAFKA_BOOTSTRAP_SERVER:-localhost:9092}"
REPLICATION_FACTOR="${1:-1}"

# If a named argument was passed, parse it
for arg in "$@"; do
    case "$arg" in
        --replication-factor=*) REPLICATION_FACTOR="${arg#*=}" ;;
        --replication-factor)   shift; REPLICATION_FACTOR="${1:-1}" ;;
    esac
done

# Detect kafka-topics binary

KAFKA_BIN=""
if command -v kafka-topics &>/dev/null; then
    KAFKA_BIN="kafka-topics"
elif command -v kafka-topics.sh &>/dev/null; then
    KAFKA_BIN="kafka-topics.sh"
elif [ -x "/opt/kafka/bin/kafka-topics.sh" ]; then
    KAFKA_BIN="/opt/kafka/bin/kafka-topics.sh"
elif [ -x "/opt/bitnami/kafka/bin/kafka-topics.sh" ]; then
    KAFKA_BIN="/opt/bitnami/kafka/bin/kafka-topics.sh"
elif [ -x "/usr/bin/kafka-topics" ]; then
    KAFKA_BIN="/usr/bin/kafka-topics"
else
    echo -e "${RED}[ERROR]${NC} kafka-topics binary not found. Are you inside a Kafka container?"
    exit 1
fi

# Helper Functions

log_info()    { echo -e "${BLUE}[INFO]${NC}    $*"; }
log_success() { echo -e "${GREEN}[OK]${NC}      $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}    $*"; }
log_error()   { echo -e "${RED}[ERROR]${NC}   $*"; }

TOPICS_CREATED=0
TOPICS_EXISTED=0
TOPICS_FAILED=0

create_topic() {
    local name="$1"
    local partitions="$2"
    local replication="${3:-$REPLICATION_FACTOR}"
    local retention_ms="$4"

    printf "  %-40s" "$name"

    output=$($KAFKA_BIN \
        --bootstrap-server "$KAFKA_BOOTSTRAP_SERVER" \
        --create \
        --if-not-exists \
        --topic "$name" \
        --partitions "$partitions" \
        --replication-factor "$replication" \
        --config retention.ms="$retention_ms" 2>&1) && rc=0 || rc=$?

    if [ $rc -eq 0 ]; then
        if echo "$output" | grep -qi "already exists"; then
            echo -e "${YELLOW}exists${NC}  (p=${partitions} rf=${replication} ret=${retention_ms}ms)"
            TOPICS_EXISTED=$((TOPICS_EXISTED + 1))
        else
            echo -e "${GREEN}created${NC} (p=${partitions} rf=${replication} ret=${retention_ms}ms)"
            TOPICS_CREATED=$((TOPICS_CREATED + 1))
        fi
    else
        echo -e "${RED}FAILED${NC}"
        log_error "  $output"
        TOPICS_FAILED=$((TOPICS_FAILED + 1))
    fi
}

# ==============================================================================
# Banner
# ==============================================================================
echo -e "${CYAN}${BOLD}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                                                            ║"
echo "║       Kafka Topic Provisioner — Fraud Detection Platform   ║"
echo "║                                                            ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"
log_info "Bootstrap server : ${BOLD}${KAFKA_BOOTSTRAP_SERVER}${NC}"
log_info "Replication factor: ${BOLD}${REPLICATION_FACTOR}${NC}"
log_info "Binary           : ${BOLD}${KAFKA_BIN}${NC}"
echo ""

# Topic Definitions

# Retention constants (milliseconds)

RETENTION_1D=86400000
RETENTION_7D=604800000
RETENTION_30D=2592000000
RETENTION_90D=7776000000

echo -e "${BOLD}Transaction Pipeline${NC}"
echo -e "${CYAN}────────────────────────────────────────────────────────${NC}"
create_topic "transaction.raw"              30  "$REPLICATION_FACTOR"  "$RETENTION_7D"
create_topic "transaction.validated"        30  "$REPLICATION_FACTOR"  "$RETENTION_7D"
create_topic "transaction.enriched"         20  "$REPLICATION_FACTOR"  "$RETENTION_7D"
echo ""

echo -e "${BOLD}Fraud Scoring${NC}"
echo -e "${CYAN}────────────────────────────────────────────────────────${NC}"
create_topic "fraud.scoring.requests"       20  "$REPLICATION_FACTOR"  "$RETENTION_1D"
create_topic "fraud.scoring.results"        20  "$REPLICATION_FACTOR"  "$RETENTION_7D"
echo ""

echo -e "${BOLD}Fraud Alerts & Cases${NC}"
echo -e "${CYAN}────────────────────────────────────────────────────────${NC}"
create_topic "fraud.alerts"                 10  "$REPLICATION_FACTOR"  "$RETENTION_30D"
create_topic "fraud.alerts.high-priority"   10  "$REPLICATION_FACTOR"  "$RETENTION_30D"
create_topic "fraud.cases"                  10  "$REPLICATION_FACTOR"  "$RETENTION_30D"
echo ""

echo -e "${BOLD}Rules & ML Models${NC}"
echo -e "${CYAN}────────────────────────────────────────────────────────${NC}"
create_topic "fraud.rules.updates"           5  "$REPLICATION_FACTOR"  "$RETENTION_30D"
create_topic "fraud.ml.model-updates"        5  "$REPLICATION_FACTOR"  "$RETENTION_30D"
echo ""

echo -e "${BOLD}Graph Analysis${NC}"
echo -e "${CYAN}────────────────────────────────────────────────────────${NC}"
create_topic "fraud.graph.updates"          10  "$REPLICATION_FACTOR"  "$RETENTION_7D"
echo ""

echo -e "${BOLD}Notifications${NC}"
echo -e "${CYAN}────────────────────────────────────────────────────────${NC}"
create_topic "notification.email"           10  "$REPLICATION_FACTOR"  "$RETENTION_7D"
create_topic "notification.sms"             10  "$REPLICATION_FACTOR"  "$RETENTION_7D"
create_topic "notification.webhook"         10  "$REPLICATION_FACTOR"  "$RETENTION_7D"
echo ""

echo -e "${BOLD}Audit & Compliance${NC}"
echo -e "${CYAN}────────────────────────────────────────────────────────${NC}"
create_topic "audit.events"                 20  "$REPLICATION_FACTOR"  "$RETENTION_90D"
create_topic "audit.access-log"             10  "$REPLICATION_FACTOR"  "$RETENTION_90D"
echo ""

echo -e "${BOLD}Monitoring${NC}"
echo -e "${CYAN}────────────────────────────────────────────────────────${NC}"
create_topic "monitoring.metrics"           10  "$REPLICATION_FACTOR"  "$RETENTION_7D"
create_topic "monitoring.health"             5  "$REPLICATION_FACTOR"  "$RETENTION_1D"
echo ""

echo -e "${BOLD}Dead Letter Queues${NC}"
echo -e "${CYAN}────────────────────────────────────────────────────────${NC}"
create_topic "dlq.transaction"              10  "$REPLICATION_FACTOR"  "$RETENTION_30D"
create_topic "dlq.fraud-scoring"            10  "$REPLICATION_FACTOR"  "$RETENTION_30D"
create_topic "dlq.notifications"             5  "$REPLICATION_FACTOR"  "$RETENTION_30D"
echo ""


# Summary

TOTAL=$((TOPICS_CREATED + TOPICS_EXISTED + TOPICS_FAILED))

echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  Summary${NC}"
echo -e "${CYAN}────────────────────────────────────────────────────────────${NC}"
echo -e "  Total topics processed : ${BOLD}${TOTAL}${NC}"
echo -e "  Created                : ${GREEN}${TOPICS_CREATED}${NC}"
echo -e "  Already existed        : ${YELLOW}${TOPICS_EXISTED}${NC}"
echo -e "  Failed                 : ${RED}${TOPICS_FAILED}${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
echo ""

if [ "$TOPICS_FAILED" -gt 0 ]; then
    log_error "${TOPICS_FAILED} topic(s) failed to create — check errors above"
    exit 1
else
    log_success "All ${TOTAL} Kafka topics are ready"
fi
