# ==============================================================================
# Fraud Detection Platform - Local Development Environment Setup (PowerShell)
# ==============================================================================
# This script bootstraps the entire local development stack including:
#   - Infrastructure services (Postgres, Redis, Kafka, Neo4j, Elasticsearch)
#   - Schema Registry & Kafka UI
#   - Kafka topic creation
#   - All application microservices
#
# Usage:
#   .\scripts\setup-local.ps1
#
# Prerequisites:
#   - Docker Desktop (with Docker Compose v2)
#   - Python 3.8+
# ==============================================================================

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Split-Path -Parent $ScriptDir
$DockerComposeFile = Join-Path $ProjectRoot "infrastructure\docker\docker-compose.yml"

# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------
function Write-Banner {
    Write-Host ""
    Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "║                                                            ║" -ForegroundColor Cyan
    Write-Host "║       Fraud Detection Platform - Local Setup               ║" -ForegroundColor Cyan
    Write-Host "║                                                            ║" -ForegroundColor Cyan
    Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Bootstrapping the complete local development environment" -ForegroundColor Blue
    Write-Host "  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss K')" -ForegroundColor Blue
    Write-Host ""
}

function Write-Info    { param([string]$Message) Write-Host "[INFO]    $Message" -ForegroundColor Blue }
function Write-Ok      { param([string]$Message) Write-Host "[OK]      $Message" -ForegroundColor Green }
function Write-Warn    { param([string]$Message) Write-Host "[WARN]    $Message" -ForegroundColor Yellow }
function Write-Err     { param([string]$Message) Write-Host "[ERROR]   $Message" -ForegroundColor Red }
function Write-Step    { param([int]$Number, [string]$Title) Write-Host "`n> Step ${Number}: $Title" -ForegroundColor Magenta }

function Invoke-DockerCompose {
    <#
    .SYNOPSIS
        Wrapper around "docker compose -f <file> <args>"
    #>
    param([Parameter(ValueFromRemainingArguments)]$Args)
    $allArgs = @("compose", "-f", $DockerComposeFile) + $Args
    & docker @allArgs
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose command failed with exit code $LASTEXITCODE"
    }
}

function Wait-ForService {
    <#
    .SYNOPSIS
        Polls docker inspect health status until the container is healthy or timeout is reached.
    #>
    param(
        [Parameter(Mandatory)][string]$ContainerName,
        [int]$TimeoutSeconds = 120,
        [int]$IntervalSeconds = 3
    )

    $elapsed = 0
    Write-Host "  Waiting for $($ContainerName.PadRight(25))" -NoNewline -ForegroundColor White

    while ($elapsed -lt $TimeoutSeconds) {
        try {
            $status = docker inspect --format='{{.State.Health.Status}}' $ContainerName 2>$null
            if ($status -eq "healthy") {
                Write-Host " healthy (${elapsed}s)" -ForegroundColor Green
                return $true
            }
        }
        catch {
            # Container may not exist yet
        }

        Start-Sleep -Seconds $IntervalSeconds
        $elapsed += $IntervalSeconds
    }

    Write-Host " TIMEOUT after ${TimeoutSeconds}s" -ForegroundColor Red
    Write-Err "Service '$ContainerName' did not become healthy within ${TimeoutSeconds}s"
    return $false
}

# ==============================================================================
# Pre-flight Checks
# ==============================================================================
Write-Banner

Write-Info "Running pre-flight checks..."

# Docker
try {
    $dockerVersion = docker --version
    Write-Ok "Docker found: $dockerVersion"
}
catch {
    Write-Err "Docker is not installed. Please install Docker Desktop: https://docs.docker.com/get-docker/"
    exit 1
}

# Docker Compose v2
try {
    $composeVersion = docker compose version
    Write-Ok "Docker Compose found: $composeVersion"
}
catch {
    Write-Err "'docker compose' (v2) not found. Please update Docker Desktop."
    exit 1
}

# Python 3
try {
    $pythonVersion = python3 --version 2>$null
    if (-not $pythonVersion) { $pythonVersion = python --version 2>$null }
    if ($pythonVersion -match "Python 3") {
        Write-Ok "Python 3 found: $pythonVersion"
    }
    else {
        Write-Warn "Python 3 not found - seed-data.py requires Python 3."
    }
}
catch {
    Write-Warn "Python 3 not found - seed-data.py requires Python 3."
}

# Docker daemon
try {
    docker info 2>$null | Out-Null
    Write-Ok "Docker daemon is running"
}
catch {
    Write-Err "Docker daemon is not running. Please start Docker Desktop and try again."
    exit 1
}

# ==============================================================================
# Step 0 - Environment File
# ==============================================================================
Write-Step -Number 0 -Title "Preparing environment file"

$EnvFile    = Join-Path $ProjectRoot ".env"
$EnvExample = Join-Path $ProjectRoot ".env.example"

if (-not (Test-Path $EnvExample)) {
    Write-Info "Creating sample .env.example..."
    @"
# ==============================================================================
# Fraud Detection Platform - Environment Variables
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
"@ | Set-Content -Path $EnvExample -Encoding UTF8
    Write-Ok ".env.example created"
}

if (-not (Test-Path $EnvFile)) {
    Write-Info "Creating .env from .env.example..."
    Copy-Item -Path $EnvExample -Destination $EnvFile
    Write-Ok ".env file created - review and update secrets before production use"
}
else {
    Write-Ok ".env file already exists"
}

# ==============================================================================
# Step 1 - Build Docker Images
# ==============================================================================
Write-Step -Number 1 -Title "Building all Docker images"

try {
    Invoke-DockerCompose build --parallel
    Write-Ok "Docker images built"
}
catch {
    Write-Err "Failed to build Docker images: $_"
    exit 1
}

# ==============================================================================
# Step 2 - Start Infrastructure Services
# ==============================================================================
Write-Step -Number 2 -Title "Starting infrastructure services"

$infraServices = @("postgres", "redis", "kafka", "neo4j", "elasticsearch")

try {
    Invoke-DockerCompose up -d @infraServices
    Write-Ok "Infrastructure containers started"
}
catch {
    Write-Err "Failed to start infrastructure services: $_"
    exit 1
}

# ==============================================================================
# Step 3 - Wait for Infrastructure Health Checks
# ==============================================================================
Write-Step -Number 3 -Title "Waiting for infrastructure health checks"

$healthTimeout = 180

$infraContainers = @(
    "fraud-postgres",
    "fraud-redis",
    "fraud-kafka",
    "fraud-neo4j",
    "fraud-elasticsearch"
)

$allHealthy = $true
foreach ($container in $infraContainers) {
    $result = Wait-ForService -ContainerName $container -TimeoutSeconds $healthTimeout
    if (-not $result) { $allHealthy = $false }
}

if (-not $allHealthy) {
    Write-Err "Some infrastructure services failed to become healthy. Check 'docker ps' and logs."
    exit 1
}

Write-Ok "All infrastructure services are healthy"

# ==============================================================================
# Step 4 - Start Schema Registry & Kafka UI
# ==============================================================================
Write-Step -Number 4 -Title "Starting Schema Registry & Kafka UI"

try {
    Invoke-DockerCompose up -d schema-registry kafka-ui
    Start-Sleep -Seconds 5
    Write-Ok "Schema Registry and Kafka UI started"
}
catch {
    Write-Err "Failed to start Schema Registry / Kafka UI: $_"
    exit 1
}

# ==============================================================================
# Step 5 - Create Kafka Topics
# ==============================================================================
Write-Step -Number 5 -Title "Creating Kafka topics"

$topicsScript = Join-Path $ScriptDir "create-kafka-topics.sh"

if (Test-Path $topicsScript) {
    Write-Info "Delegating to create-kafka-topics.sh via docker exec..."
    try {
        docker exec fraud-kafka bash /scripts/create-kafka-topics.sh
        Write-Ok "Kafka topics created via script"
    }
    catch {
        Write-Warn "create-kafka-topics.sh failed, falling back to inline creation"
    }
}

# Inline fallback / ensure topics exist
$topics = @(
    @{ Name = "transaction.raw";             Partitions = 30 },
    @{ Name = "transaction.validated";       Partitions = 30 },
    @{ Name = "transaction.enriched";        Partitions = 20 },
    @{ Name = "fraud.scoring.requests";      Partitions = 20 },
    @{ Name = "fraud.scoring.results";       Partitions = 20 },
    @{ Name = "fraud.alerts";                Partitions = 10 },
    @{ Name = "fraud.alerts.high-priority";  Partitions = 10 },
    @{ Name = "fraud.cases";                 Partitions = 10 },
    @{ Name = "notification.email";          Partitions = 10 },
    @{ Name = "notification.sms";            Partitions = 10 },
    @{ Name = "notification.webhook";        Partitions = 10 },
    @{ Name = "audit.events";               Partitions = 20 },
    @{ Name = "monitoring.metrics";          Partitions = 10 }
)

foreach ($topic in $topics) {
    try {
        Invoke-DockerCompose exec -T kafka kafka-topics `
            --bootstrap-server localhost:9092 `
            --create --if-not-exists `
            --topic $topic.Name `
            --partitions $topic.Partitions `
            --replication-factor 1
    }
    catch {
        Write-Warn "Could not create topic $($topic.Name): $_"
    }
}

Write-Ok "Kafka topics created"

# ==============================================================================
# Step 6 - Start Application Services
# ==============================================================================
Write-Step -Number 6 -Title "Starting application microservices"

$appServices = @(
    "api-gateway",
    "transaction-service",
    "fraud-orchestrator",
    "rule-engine",
    "ml-scoring",
    "graph-analysis",
    "alert-service",
    "case-management",
    "notification-service",
    "audit-service",
    "monitoring-service"
)

try {
    Invoke-DockerCompose up -d @appServices
    Write-Ok "Application containers started"
}
catch {
    Write-Err "Failed to start application services: $_"
    exit 1
}

# ==============================================================================
# Step 7 - Wait for Application Health Checks
# ==============================================================================
Write-Step -Number 7 -Title "Waiting for application health checks"

$appHealthTimeout = 120

$appContainers = @(
    "fraud-api-gateway",
    "fraud-transaction-service",
    "fraud-orchestrator",
    "fraud-rule-engine",
    "fraud-ml-scoring",
    "fraud-graph-analysis",
    "fraud-alert-service",
    "fraud-case-management",
    "fraud-notification-service",
    "fraud-audit-service",
    "fraud-monitoring-service"
)

foreach ($container in $appContainers) {
    Wait-ForService -ContainerName $container -TimeoutSeconds $appHealthTimeout | Out-Null
}

# ==============================================================================
# Summary
# ==============================================================================
Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║                                                            ║" -ForegroundColor Cyan
Write-Host "║         Local Environment Ready!                           ║" -ForegroundColor Green
Write-Host "║                                                            ║" -ForegroundColor Cyan
Write-Host "╠══════════════════════════════════════════════════════════════╣" -ForegroundColor Cyan
Write-Host "║                                                            ║" -ForegroundColor Cyan
Write-Host "║  Service URLs:                                             ║" -ForegroundColor Cyan
Write-Host "║  -----------------------------------------------------------║" -ForegroundColor DarkCyan
Write-Host "║  API Gateway          http://localhost:8000                 ║" -ForegroundColor White
Write-Host "║  API Docs (Swagger)   http://localhost:8000/docs            ║" -ForegroundColor White
Write-Host "║  Kafka UI             http://localhost:9090                 ║" -ForegroundColor White
Write-Host "║  Neo4j Browser        http://localhost:7474                 ║" -ForegroundColor White
Write-Host "║  Elasticsearch        http://localhost:9200                 ║" -ForegroundColor White
Write-Host "║  Schema Registry      http://localhost:8081                 ║" -ForegroundColor White
Write-Host "║                                                            ║" -ForegroundColor Cyan
Write-Host "╠══════════════════════════════════════════════════════════════╣" -ForegroundColor Cyan
Write-Host "║                                                            ║" -ForegroundColor Cyan
Write-Host "║  Next Steps:                                               ║" -ForegroundColor Cyan
Write-Host "║  1. Seed test data:   python3 scripts/seed-data.py         ║" -ForegroundColor White
Write-Host "║  2. View API docs:    open http://localhost:8000/docs       ║" -ForegroundColor White
Write-Host "║  3. Monitor Kafka:    open http://localhost:9090            ║" -ForegroundColor White
Write-Host "║  4. View logs:        docker compose logs -f <service>     ║" -ForegroundColor White
Write-Host "║                                                            ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
