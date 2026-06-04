# ADR-001: FastAPI Over Spring Boot for Microservices Framework

| Field        | Value                                      |
|--------------|--------------------------------------------|
| **Status**   | Accepted                                   |
| **Date**     | 2026-05-30                                 |
| **Deciders** | Platform Architecture Team, ML Engineering |

---

## Context

The Real-Time Fraud Detection platform requires a microservices framework capable of handling **100 million+ transactions per day** with sub-100ms latency targets for scoring requests. The framework must seamlessly integrate with machine learning models, support high-concurrency workloads, and enable rapid iteration on fraud detection logic.

Two primary candidates were evaluated:

- **Spring Boot (Java/Kotlin)** — The established enterprise standard with a mature ecosystem, robust threading model, and proven performance on the JVM.
- **FastAPI (Python)** — A modern, async-first Python web framework built on Starlette and Pydantic, designed for high-performance API development.

### Key Requirements

1. **ML Model Integration**: Fraud scoring models are developed in Python using scikit-learn, XGBoost, and PyTorch. The framework must support native, low-latency model inference without cross-language serialization overhead.
2. **Async I/O at Scale**: Services must handle thousands of concurrent connections with non-blocking I/O for Kafka consumers, Redis lookups, database queries, and inter-service calls.
3. **Developer Velocity**: The team must iterate rapidly on detection rules and model pipelines. Short feedback loops and minimal boilerplate are essential.
4. **Data Validation**: Incoming transaction payloads are complex and variable. The framework must enforce strict schema validation with clear error reporting.
5. **Operational Maturity**: The framework must support production-grade observability (metrics, tracing, structured logging), health checks, and graceful shutdown.

---

## Decision

**We will adopt FastAPI as the primary microservices framework** for all fraud detection services, including the Transaction Ingestion Service, Fraud Scoring Engine, Rule Engine, and Alert Service.

### Rationale

#### 1. Unified Python Stack for ML Integration

The fraud detection pipeline is fundamentally an ML-driven system. Models are trained, validated, and exported in Python. By adopting FastAPI, we eliminate the **language boundary** between model development and model serving:

- Models are loaded directly into the service process via `joblib`, `pickle`, or framework-native loaders (e.g., `torch.load`).
- Feature engineering code written during model development is reused verbatim in production — no translation to Java required.
- The data science team can contribute directly to service logic, reducing handoff friction and translation bugs.
- Libraries like NumPy, Pandas, and scikit-learn are first-class citizens, avoiding JNI bridges or subprocess calls.

With Spring Boot, ML integration would require either:
- Deploying models behind a separate serving layer (e.g., TensorFlow Serving, Triton), adding network latency (~2-5ms per hop).
- Using ONNX Runtime via Java bindings, which introduces format conversion complexity and limits model flexibility.
- Maintaining a separate Python sidecar, negating the benefits of a unified stack.

#### 2. Async-First Architecture

FastAPI is built on **ASGI (Asynchronous Server Gateway Interface)** and leverages Python's `asyncio` event loop natively:

```python
@app.post("/v1/transactions/score", response_model=ScoringResponse)
async def score_transaction(transaction: TransactionPayload):
    # All I/O operations are non-blocking
    async with asyncio.TaskGroup() as tg:
        customer_profile = tg.create_task(redis_client.get_profile(transaction.customer_id))
        velocity_features = tg.create_task(feature_store.get_velocity(transaction.customer_id))
        device_fingerprint = tg.create_task(device_service.lookup(transaction.device_id))

    score = await scoring_engine.predict(
        transaction, customer_profile.result(), velocity_features.result(), device_fingerprint.result()
    )
    return ScoringResponse(score=score, transaction_id=transaction.id)
```

- Concurrent fan-out to Redis, feature stores, and downstream services is idiomatic and lightweight.
- Uvicorn with `uvloop` achieves **~80-90% of Go/Java throughput** for I/O-bound workloads while maintaining Python's expressiveness.
- WebSocket support is built-in for real-time dashboard streaming.

While Spring Boot's WebFlux (Project Reactor) offers similar async capabilities, the reactive programming model is significantly more complex, with a steeper learning curve and harder debugging experience.

#### 3. Developer Velocity and Iteration Speed

Fraud detection is an **adversarial domain** — attack patterns evolve continuously, requiring rapid rule updates and model redeployment:

- **Hot reload**: Uvicorn's `--reload` flag enables sub-second feedback during development.
- **Minimal boilerplate**: A complete endpoint with validation, documentation, and error handling requires ~50% fewer lines than the equivalent Spring Boot code.
- **Interactive documentation**: FastAPI auto-generates OpenAPI (Swagger) and ReDoc documentation from type hints — no annotation configuration required.
- **Type safety without ceremony**: Python type hints + Pydantic provide compile-time-like safety with runtime validation, without Java's verbose generics.

#### 4. Pydantic-Powered Data Validation

Transaction payloads in fraud detection are complex, nested, and vary by payment method, channel, and geography. Pydantic provides:

```python
class TransactionPayload(BaseModel):
    transaction_id: UUID
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: CurrencyCode  # ISO 4217 enum
    timestamp: datetime = Field(description="ISO 8601 transaction timestamp")
    customer_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    merchant: MerchantInfo
    payment_method: PaymentMethod  # Discriminated union
    device: Optional[DeviceFingerprint] = None
    geolocation: Optional[GeoLocation] = None

    @field_validator("timestamp")
    @classmethod
    def timestamp_not_future(cls, v: datetime) -> datetime:
        if v > datetime.now(UTC) + timedelta(minutes=5):
            raise ValueError("Transaction timestamp cannot be more than 5 minutes in the future")
        return v

    model_config = ConfigDict(
        json_schema_extra={"examples": [...]},
        str_strip_whitespace=True,
    )
```

- **Discriminated unions** handle polymorphic payment methods (card, ACH, wire, crypto) with type-safe parsing.
- **Custom validators** enforce domain-specific business rules at the schema level.
- **Serialization performance**: Pydantic v2 (Rust-backed) achieves validation speeds comparable to hand-written Java validation.
- **Schema evolution**: Models are versioned and backward-compatible, supporting rolling deployments.

---

## Consequences

### Positive

- **Zero-friction ML integration**: Models and feature engineering code run natively in-process, eliminating serialization overhead and cross-language bugs.
- **Faster iteration cycles**: New fraud rules and model versions can be developed, tested, and deployed in hours rather than days.
- **Reduced team cognitive load**: A single-language stack (Python) for ML, services, data pipelines, and scripting lowers onboarding time and context-switching cost.
- **Automatic API documentation**: OpenAPI specs are always in sync with the code, reducing integration friction with partner teams.
- **Strong ecosystem for fraud/ML**: Direct access to pandas, numpy, scikit-learn, shap (for model explainability), and the broader PyData ecosystem.

### Negative

- **Lower raw throughput than JVM**: For CPU-bound workloads, Python is ~3-5x slower than optimized Java. This is mitigated by:
  - Offloading CPU-intensive inference to compiled extensions (NumPy, ONNX Runtime, PyTorch C++ backend).
  - Horizontal scaling via Kubernetes — adding pods is operationally cheaper than optimizing JVM tuning.
  - Using Uvicorn with multiple workers to leverage multi-core CPUs.
- **GIL limitations**: Python's Global Interpreter Lock constrains true parallelism for CPU-bound tasks. Mitigations include:
  - `ProcessPoolExecutor` for CPU-bound model inference.
  - Async I/O for all network-bound operations (the majority of the workload).
  - Future migration path to Python 3.13+ free-threaded mode (PEP 703).
- **Less mature enterprise ecosystem**: Compared to Spring Boot's enterprise integrations (Spring Security, Spring Cloud), some capabilities require assembling individual libraries. This is acceptable given our Kubernetes-native infrastructure.

### Neutral

- **Deployment model**: FastAPI services are containerized identically to Spring Boot services — no operational difference in a Kubernetes environment.
- **Monitoring**: Prometheus metrics, OpenTelemetry tracing, and structured logging are well-supported in both ecosystems. We use `prometheus-fastapi-instrumentator` and `opentelemetry-instrumentation-fastapi`.

---

## Alternatives Considered

| Framework       | Verdict  | Reason for Rejection                                                                 |
|-----------------|----------|--------------------------------------------------------------------------------------|
| Spring Boot     | Rejected | Cross-language ML integration overhead; reactive programming complexity              |
| Go (Gin/Fiber)  | Rejected | Excellent performance but no native ML ecosystem; would require Python sidecar       |
| Node.js (Nest)  | Rejected | Poor ML/numerical computing support; single-threaded limitations for CPU-bound work  |
| Flask           | Rejected | No native async support; lacks built-in validation and OpenAPI generation             |

---

## References

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Pydantic v2 Performance Benchmarks](https://docs.pydantic.dev/latest/concepts/performance/)
- [Uvicorn + uvloop Benchmarks](https://www.techempower.com/benchmarks/)
- [PEP 703 — Making the Global Interpreter Lock Optional](https://peps.python.org/pep-0703/)
