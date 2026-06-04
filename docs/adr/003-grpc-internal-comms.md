# ADR-003: gRPC for Internal Service Communication

| Field        | Value                                                |
|--------------|------------------------------------------------------|
| **Status**   | Accepted                                             |
| **Date**     | 2026-05-30                                           |
| **Deciders** | Platform Architecture Team, Fraud Scoring Team       |

---

## Context

The Real-Time Fraud Detection platform consists of multiple microservices that communicate synchronously for latency-sensitive operations — most critically, the **scoring path** where the Transaction Ingestion Service calls the Fraud Scoring Engine, which in turn calls the Feature Store, Rule Engine, and Model Serving components. This scoring path must complete within a **50ms latency budget** to avoid degrading the customer payment experience.

The platform must choose a communication protocol for internal (service-to-service) calls that optimizes for:

1. **Latency**: Every millisecond matters in the scoring path. Protocol overhead must be minimized.
2. **Type Safety**: Fraud scoring payloads are complex (100+ fields across transaction, customer, device, and merchant data). Schema mismatches between services cause silent data corruption or runtime failures.
3. **Bandwidth Efficiency**: At 100M+ transactions/day, even small per-message overhead multiplies to significant bandwidth cost.
4. **Streaming**: Some operations (batch scoring, model explanation, real-time monitoring) benefit from bidirectional streaming.
5. **Cross-team contracts**: Service interfaces must be explicitly defined, versioned, and enforceable at compile time.

Two primary options were evaluated:

- **REST (HTTP/1.1 + JSON)** — The ubiquitous standard for web APIs.
- **gRPC (HTTP/2 + Protocol Buffers)** — A high-performance RPC framework with binary serialization.

---

## Decision

**We will adopt gRPC as the primary protocol for all internal service-to-service communication**, particularly on the latency-critical scoring path. **REST (HTTP/1.1 + JSON) will be retained for all external-facing APIs** (partner integrations, dashboard backends, management endpoints).

### Rationale

#### 1. Binary Protocol Efficiency

gRPC uses **Protocol Buffers (protobuf)** as its default serialization format, a binary encoding that is dramatically more efficient than JSON:

| Metric                    | JSON (REST)      | Protobuf (gRPC)  | Improvement |
|---------------------------|------------------|-------------------|-------------|
| **Serialization size**    | ~1,200 bytes     | ~280 bytes        | **~4.3x**   |
| **Serialization time**    | ~45 µs           | ~5 µs             | **~9x**     |
| **Deserialization time**  | ~60 µs           | ~4 µs             | **~15x**    |
| **CPU usage (ser/deser)** | High (string parsing) | Low (binary)  | **~5-8x**   |

*Benchmark: Typical fraud scoring request with 120 fields (transaction + customer + device + merchant context), measured on Python 3.12 with `betterproto` and `orjson`.*

At 100M transactions/day:
- **JSON**: ~120 GB/day of internal network traffic for scoring requests alone.
- **Protobuf**: ~28 GB/day — a **92 GB/day reduction** in internal bandwidth.

This efficiency compounds across the scoring fan-out pattern where the Scoring Engine calls 3-5 downstream services per transaction.

#### 2. Strong Typing with Protocol Buffers

Protobuf enforces a **schema-first contract** between services, catching integration errors at compile time rather than runtime:

```protobuf
// fraud_scoring/v1/scoring.proto

syntax = "proto3";
package fraud_scoring.v1;

import "google/protobuf/timestamp.proto";
import "google/protobuf/wrappers.proto";

service FraudScoringService {
  // Synchronous single-transaction scoring
  rpc ScoreTransaction(ScoreRequest) returns (ScoreResponse);

  // Bidirectional streaming for batch scoring
  rpc ScoreTransactionStream(stream ScoreRequest) returns (stream ScoreResponse);

  // Server-streaming for model explanation
  rpc ExplainScore(ExplainRequest) returns (stream ExplainResponse);
}

message ScoreRequest {
  string transaction_id = 1;
  TransactionData transaction = 2;
  CustomerContext customer = 3;
  DeviceFingerprint device = 4;
  MerchantInfo merchant = 5;
  map<string, FeatureValue> precomputed_features = 6;
}

message ScoreResponse {
  string transaction_id = 1;
  double risk_score = 2;           // 0.0 - 1.0
  RiskLevel risk_level = 3;
  repeated RuleMatch triggered_rules = 4;
  map<string, double> feature_contributions = 5;  // SHAP values
  google.protobuf.Timestamp scored_at = 6;
  string model_version = 7;
  int32 scoring_latency_us = 8;    // Microseconds
}

enum RiskLevel {
  RISK_LEVEL_UNSPECIFIED = 0;
  LOW = 1;
  MEDIUM = 2;
  HIGH = 3;
  CRITICAL = 4;
}

message RuleMatch {
  string rule_id = 1;
  string rule_name = 2;
  double confidence = 3;
  string explanation = 4;
}

message TransactionData {
  string amount = 1;              // Decimal as string for precision
  string currency = 2;            // ISO 4217
  google.protobuf.Timestamp timestamp = 3;
  PaymentMethod payment_method = 4;
  TransactionType type = 5;
  google.protobuf.StringValue pos_entry_mode = 6;  // Optional field
}
```

Benefits of schema-first design:
- **Breaking change detection**: The protobuf compiler and linting tools (e.g., `buf lint`, `buf breaking`) catch backward-incompatible changes before they reach production.
- **Documentation as code**: The `.proto` files serve as the authoritative service contract, always in sync with the implementation.
- **Field presence tracking**: Protobuf distinguishes between "field not set" and "field set to default value" via optional fields and wrapper types, preventing subtle bugs in fraud scoring logic.
- **Enum safety**: Risk levels, transaction types, and payment methods are defined as enums with explicit values, eliminating magic strings.

With REST/JSON, schema enforcement relies on runtime validation (Pydantic, JSON Schema) and is only as reliable as the discipline of updating shared schema packages.

#### 3. Bidirectional Streaming

gRPC's HTTP/2 foundation enables four communication patterns, three of which are critical for fraud detection:

**Unary RPC** — Standard request/response for single-transaction scoring:
```python
# Client: Transaction Ingestion Service
async with grpc.aio.insecure_channel("fraud-scoring:50051") as channel:
    stub = FraudScoringServiceStub(channel)
    response = await stub.ScoreTransaction(score_request, timeout=0.05)  # 50ms timeout
```

**Server streaming** — Model explanation returns feature contributions incrementally:
```python
# Client requests explanation, server streams SHAP values as they're computed
async for explanation_chunk in stub.ExplainScore(explain_request):
    await send_to_dashboard(explanation_chunk)
```

**Bidirectional streaming** — Batch scoring for bulk reprocessing:
```python
# Both sides stream concurrently — requests flow in, scores flow out
async def score_batch(transactions: AsyncIterator[ScoreRequest]):
    async for response in stub.ScoreTransactionStream(transactions):
        await publish_scored_result(response)
```

REST/JSON over HTTP/1.1 cannot support streaming natively. Workarounds (WebSockets, Server-Sent Events) add complexity and are not standardized for RPC patterns.

#### 4. Code Generation Across Languages

Protobuf definitions generate **type-safe client and server stubs** in all languages used in the platform:

```bash
# Generate Python stubs with betterproto (async-native)
buf generate --template buf.gen.yaml

# Generates:
# ├── fraud_scoring/v1/scoring_pb2.py          # Message classes
# ├── fraud_scoring/v1/scoring_pb2_grpc.py      # Service stubs
# └── fraud_scoring/v1/scoring_grpc.py          # Async client/server
```

- **No hand-written HTTP clients**: gRPC stubs provide typed method calls (`stub.ScoreTransaction(request)`) instead of manual URL construction, header management, and JSON parsing.
- **Consistent serialization**: All services use the same protobuf definitions, eliminating the "my JSON doesn't match your JSON" class of bugs.
- **Polyglot ready**: If specific services are later rewritten in Go or Rust for performance, gRPC stubs regenerate seamlessly — the protocol and contracts remain identical.

#### 5. ~10x Faster Than REST for Internal Calls

End-to-end benchmarks on the scoring path demonstrate significant performance advantages:

| Metric                           | REST (HTTP/1.1 + JSON) | gRPC (HTTP/2 + Protobuf) | Improvement   |
|----------------------------------|------------------------|--------------------------|---------------|
| **Single call latency (p50)**    | 8.2 ms                 | 0.9 ms                   | **~9.1x**     |
| **Single call latency (p99)**    | 22.5 ms                | 2.8 ms                   | **~8.0x**     |
| **Throughput (reqs/sec/conn)**   | 4,200                  | 38,000                   | **~9.0x**     |
| **Connection overhead**          | New TCP per request*   | Multiplexed on 1 conn   | Significant   |
| **Payload size (scoring req)**   | 1,200 bytes            | 280 bytes                | **~4.3x**     |
| **CPU (serialization)**          | 12% of request time    | 1.5% of request time     | **~8x**       |

*\*HTTP/1.1 with keep-alive reuses connections but cannot multiplex — requests on the same connection are serialized (head-of-line blocking).*

The performance gains come from:
1. **HTTP/2 multiplexing**: Multiple concurrent RPCs over a single TCP connection, eliminating connection setup overhead and head-of-line blocking.
2. **Binary framing**: HTTP/2 frames are binary, not text-parsed.
3. **Header compression (HPACK)**: Repeated headers (e.g., `Content-Type`, auth tokens) are compressed across requests.
4. **Protobuf encoding**: As detailed in section 1.
5. **Connection pooling**: gRPC channels maintain persistent connections with automatic reconnection.

In the scoring path, where the Scoring Engine fans out to 3-5 downstream services, gRPC saves **~20-35ms per transaction** compared to REST — the difference between meeting and missing the 50ms latency budget.

---

## REST for External APIs

External-facing APIs retain REST (HTTP/1.1 + JSON) for the following reasons:

- **Developer friendliness**: Partners, fintech integrators, and internal dashboard teams expect REST APIs with JSON payloads. Requiring gRPC tooling would increase integration friction.
- **Browser compatibility**: Dashboard frontends and admin UIs use `fetch()` / `axios` — they cannot natively call gRPC endpoints (gRPC-Web exists but adds complexity).
- **Debugging ease**: JSON payloads are human-readable, making `curl`, Postman, and browser DevTools effective debugging tools.
- **Ecosystem maturity**: API gateways (Kong, Envoy), rate limiters, and OAuth2 middleware have first-class REST support.

**Architecture boundary:**

```
External World                    │  Internal Mesh (Kubernetes)
                                  │
Partner APIs ──── REST/JSON ────► │ ┌──────────────────────────────────────┐
                                  │ │  API Gateway (Envoy)                 │
Dashboard UI ──── REST/JSON ────► │ │    │                                 │
                                  │ │    ▼                                 │
Mobile Apps ───── REST/JSON ────► │ │  Ingestion Service                   │
                                  │ │    │ gRPC                            │
                                  │ │    ├──► Fraud Scoring Engine         │
                                  │ │    │      │ gRPC     │ gRPC          │
                                  │ │    │      ▼          ▼               │
                                  │ │    │    Feature    Rule Engine       │
                                  │ │    │    Store                        │
                                  │ │    │ gRPC                            │
                                  │ │    └──► Alert Service                │
                                  │ └──────────────────────────────────────┘
```

---

## Consequences

### Positive

- **Sub-millisecond serialization**: Protobuf encoding/decoding is ~10x faster than JSON, reclaiming latency budget for actual business logic.
- **Compile-time contract enforcement**: Breaking changes to service interfaces are caught during CI/CD, not in production.
- **Bandwidth reduction**: ~75% reduction in internal network traffic compared to JSON, reducing cloud networking costs.
- **Native streaming**: Bidirectional streaming enables batch scoring, real-time monitoring feeds, and incremental model explanations without architectural workarounds.
- **Connection efficiency**: HTTP/2 multiplexing eliminates connection pool management complexity and head-of-line blocking.

### Negative

- **Debugging complexity**: Binary protobuf payloads are not human-readable. Mitigation:
  - **gRPC reflection** is enabled on all services for `grpcurl` and `grpcui` inspection.
  - **Envoy proxy** logs decoded protobuf messages in JSON format for debugging.
  - **Distributed tracing** (OpenTelemetry) captures gRPC metadata and timing for request correlation.
- **Tooling learning curve**: Teams must learn protobuf schema design, `buf` CLI, and gRPC interceptor patterns. Mitigation: internal proto style guide, shared interceptor libraries, and training sessions.
- **Schema evolution discipline**: Protobuf field numbering and backward compatibility rules require careful management. Mitigation:
  - `buf breaking` checks run in CI on every PR that modifies `.proto` files.
  - Reserved field numbers for deprecated fields.
  - Additive-only changes enforced by policy.
- **Load balancing complexity**: gRPC's persistent HTTP/2 connections bypass L4 load balancers (connections are long-lived, so new pods don't receive traffic). Mitigation:
  - **L7 load balancing** via Envoy sidecar proxy (Istio service mesh) or Kubernetes headless services with client-side balancing.
  - gRPC `round_robin` or `pick_first` with `dns:///` resolver for client-side LB.

### Neutral

- **Health checking**: gRPC defines a [standard health checking protocol](https://github.com/grpc/grpc/blob/master/doc/health-checking.md) that integrates with Kubernetes liveness/readiness probes via `grpc_health_probe`.
- **Interceptors**: gRPC interceptors (middleware) provide the same cross-cutting concern patterns (auth, logging, metrics, tracing) as REST middleware, with a slightly different API.
- **Deadlines/timeouts**: gRPC's native deadline propagation automatically chains timeouts across the call graph — if the ingestion service sets a 50ms deadline, downstream services see the remaining time budget.

---

## Implementation Details

### Proto Repository Structure

```
proto/
├── buf.yaml                    # Buf module configuration
├── buf.gen.yaml                # Code generation configuration
├── buf.lock                    # Dependency lock file
├── fraud_scoring/
│   └── v1/
│       ├── scoring.proto       # Scoring service definition
│       ├── models.proto        # Shared message types
│       └── enums.proto         # Shared enums
├── feature_store/
│   └── v1/
│       └── features.proto      # Feature retrieval service
├── rule_engine/
│   └── v1/
│       └── rules.proto         # Rule evaluation service
├── alert/
│   └── v1/
│       └── alerts.proto        # Alert management service
└── common/
    └── v1/
        ├── pagination.proto    # Shared pagination messages
        ├── error_details.proto # Structured error responses
        └── health.proto        # Health check service
```

### gRPC Configuration Standards

```python
# Shared gRPC channel configuration
GRPC_CHANNEL_OPTIONS = [
    ("grpc.keepalive_time_ms", 10000),           # Send keepalive every 10s
    ("grpc.keepalive_timeout_ms", 5000),          # Wait 5s for keepalive ack
    ("grpc.keepalive_permit_without_calls", True), # Keepalive even when idle
    ("grpc.http2.max_pings_without_data", 0),     # Unlimited pings
    ("grpc.max_receive_message_length", 4 * 1024 * 1024),  # 4MB max message
    ("grpc.default_compression_algorithm", CompressionAlgorithm.gzip),
]

# Interceptors applied to all channels
STANDARD_INTERCEPTORS = [
    OpenTelemetryClientInterceptor(),    # Distributed tracing
    PrometheusClientInterceptor(),       # Metrics (latency, error rate)
    RetryInterceptor(max_retries=2, backoff_ms=100),  # Automatic retry
    DeadlineInterceptor(default_timeout_ms=50),       # Default 50ms deadline
]
```

---

## Alternatives Considered

| Protocol           | Verdict   | Reason for Rejection                                                                                    |
|--------------------|-----------|----------------------------------------------------------------------------------------------------------|
| REST (HTTP/1.1)    | Rejected (internal) | ~10x higher latency, no multiplexing, JSON serialization overhead, no streaming                |
| REST (HTTP/2)      | Evaluated | HTTP/2 benefits without schema enforcement or code generation; JSON overhead remains                    |
| GraphQL            | Rejected  | Designed for flexible client queries, not machine-to-machine RPC; no streaming; overhead of query parsing |
| Apache Thrift      | Evaluated | Similar binary protocol but smaller ecosystem, less active development, weaker streaming support         |
| Cap'n Proto        | Evaluated | Zero-copy serialization is compelling but very small ecosystem; limited language support                  |
| Custom TCP/Binary  | Rejected  | Maximum performance but unmaintainable; no tooling, no observability integration                         |

---

## References

- [gRPC Official Documentation](https://grpc.io/docs/)
- [Protocol Buffers Language Guide](https://protobuf.dev/programming-guides/proto3/)
- [Buf: Modern Protobuf Tooling](https://buf.build/docs/)
- [gRPC Health Checking Protocol](https://github.com/grpc/grpc/blob/master/doc/health-checking.md)
- [Envoy gRPC Bridging](https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/other_protocols/grpc)
- [gRPC Load Balancing](https://grpc.io/blog/grpc-load-balancing/)
