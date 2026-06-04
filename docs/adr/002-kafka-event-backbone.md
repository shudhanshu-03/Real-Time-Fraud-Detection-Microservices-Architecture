# ADR-002: Apache Kafka as the Event Backbone

| Field        | Value                                          |
|--------------|-------------------------------------------------|
| **Status**   | Accepted                                        |
| **Date**     | 2026-05-30                                      |
| **Deciders** | Platform Architecture Team, Data Engineering    |

---

## Context

The Real-Time Fraud Detection platform processes **100 million+ transactions per day** (~1,150 TPS average, ~5,000+ TPS peak) across multiple ingestion channels (card networks, ACH, wire transfers, mobile payments). The event backbone must:

1. **Decouple producers from consumers**: Transaction ingestion must not block on downstream scoring, alerting, or analytics.
2. **Guarantee delivery**: Every transaction must be processed exactly once — missed transactions mean undetected fraud; duplicates mean false alerts and degraded customer experience.
3. **Enable stream processing**: Real-time feature computation (velocity checks, aggregation windows, pattern detection) requires a native stream processing capability.
4. **Support replay and reprocessing**: When fraud models are retrained or rules are updated, historical transactions must be replayable to validate detection improvements.
5. **Scale horizontally**: Throughput must grow linearly with partition count without architectural changes.
6. **Retain events durably**: Regulatory requirements mandate 7-year transaction retention; operational needs require at least 30 days of hot replay capability.

Three messaging systems were evaluated:

- **Apache Kafka** — Distributed, append-only commit log with stream processing capabilities.
- **RabbitMQ** — Traditional message broker with flexible routing (AMQP 0-9-1).
- **Amazon SQS/SNS** — Fully managed AWS messaging services.

---

## Decision

**We will adopt Apache Kafka as the central event backbone** for all inter-service communication, event sourcing, and stream processing in the fraud detection platform.

### Rationale

#### 1. Event Sourcing and Immutable Audit Log

Fraud detection is a regulated domain requiring complete, tamper-evident audit trails. Kafka's append-only commit log is architecturally aligned with this requirement:

- Every transaction event is **immutably persisted** in topic partitions with a monotonically increasing offset.
- The commit log serves as the **system of record** — all derived state (risk scores, alerts, customer profiles) can be reconstructed by replaying the log.
- Consumer offsets are managed independently per consumer group, enabling multiple teams to process the same event stream at their own pace.

```
Topic: transactions.raw
├── Partition 0: [offset 0] [offset 1] [offset 2] ... [offset N]
├── Partition 1: [offset 0] [offset 1] [offset 2] ... [offset N]
├── ...
└── Partition 31: [offset 0] [offset 1] [offset 2] ... [offset N]

Consumer Groups:
├── fraud-scoring-engine     → reads at real-time speed
├── analytics-pipeline       → reads at batch speed
├── compliance-auditor       → reads on-demand for investigations
└── model-retraining         → replays historical windows for training
```

RabbitMQ and SQS are **destructive consumers** — once a message is acknowledged, it is removed from the queue. Implementing event sourcing on these systems requires a separate event store (e.g., EventStoreDB), adding architectural complexity.

#### 2. Stream Processing with Kafka Streams and Faust

Real-time fraud detection requires computing **streaming features** — temporal aggregations, velocity checks, and behavioral patterns — over sliding time windows:

```python
# Faust stream processor for velocity features
@app.agent(transactions_topic)
async def compute_velocity(stream: StreamT[Transaction]) -> None:
    async for txn in stream.group_by(Transaction.customer_id):
        # Tumbling window: transactions per customer in last 5 minutes
        window = velocity_table[txn.customer_id].current()
        window.count += 1
        window.total_amount += txn.amount

        if window.count > VELOCITY_THRESHOLD:
            await high_velocity_alerts_topic.send(
                key=txn.customer_id,
                value=VelocityAlert(
                    customer_id=txn.customer_id,
                    window_count=window.count,
                    window_amount=window.total_amount,
                    triggered_by=txn.transaction_id,
                )
            )
```

Kafka's **co-partitioning** ensures that all transactions for a given customer are processed by the same stream processor instance, enabling stateful computations without external coordination.

Neither RabbitMQ nor SQS provide native stream processing. Implementing equivalent functionality would require bolting on Apache Flink or AWS Kinesis Data Analytics, adding operational overhead and latency.

#### 3. High Throughput and Low Latency

Kafka's architecture is optimized for sustained high throughput:

| Metric                     | Kafka           | RabbitMQ         | SQS              |
|----------------------------|-----------------|------------------|-------------------|
| **Throughput (msgs/sec)**  | 1M+ per broker  | ~50K per node    | ~3K per queue     |
| **p99 Latency (produce)**  | 2-5ms           | 1-3ms            | 10-20ms           |
| **p99 Latency (e2e)**      | 5-15ms          | 3-10ms           | 50-200ms          |
| **Scalability model**      | Partitions      | Queues           | Queues            |
| **Storage**                | Disk (zero-copy)| Memory + disk    | Managed           |

Key performance enablers:
- **Zero-copy transfer**: Kafka uses `sendfile()` to transfer data directly from disk to network, bypassing user-space copies.
- **Sequential I/O**: Append-only writes and sequential reads exploit OS page cache and SSD/HDD sequential performance.
- **Batching**: Producers batch records by partition, amortizing network overhead. Consumers fetch in large batches.
- **Compression**: LZ4 or Zstandard compression at the batch level reduces network bandwidth by 60-80% for JSON payloads.

#### 4. Exactly-Once Semantics (EOS)

Fraud detection cannot tolerate duplicate processing (double alerts, double scoring) or missed events (unscored transactions):

- **Idempotent producers** (`enable.idempotence=true`): Kafka assigns sequence numbers to each message per partition, deduplicating retries at the broker level.
- **Transactional producers**: Atomic writes across multiple partitions ensure that a scoring result and its corresponding state update are committed together or not at all.
- **Consumer offset commits within transactions**: The read-process-write cycle is atomic — a crash after processing but before commit does not result in reprocessing.

```python
# Transactional produce: score + audit log are atomic
async with producer.transaction():
    await producer.send(
        "transactions.scored",
        key=txn.transaction_id,
        value=scored_result,
    )
    await producer.send(
        "audit.scoring-decisions",
        key=txn.transaction_id,
        value=audit_record,
    )
    # Consumer offset is committed as part of the transaction
```

RabbitMQ supports publisher confirms and consumer acknowledgments but does not provide end-to-end exactly-once semantics across the produce-consume cycle. SQS offers at-least-once delivery with deduplication windows (5-minute) via FIFO queues, but this is insufficient for our latency and correctness requirements.

#### 5. Partitioning for Parallelism and Data Locality

Kafka topics are divided into **partitions**, each of which is an ordered, append-only log. This enables:

- **Parallel consumption**: Each partition is consumed by exactly one consumer within a consumer group, enabling linear scale-out.
- **Key-based routing**: Transactions are partitioned by `customer_id`, ensuring all events for a customer are processed in order by the same consumer instance.
- **Data locality**: Stateful stream processors (velocity counters, behavioral profiles) maintain local state for their assigned partitions, avoiding distributed coordination.

**Topic design for the fraud detection platform:**

| Topic                          | Partitions | Key             | Retention | Purpose                                    |
|--------------------------------|------------|-----------------|-----------|--------------------------------------------|
| `transactions.raw`            | 32         | `customer_id`   | 30 days   | Raw ingested transactions                  |
| `transactions.enriched`       | 32         | `customer_id`   | 30 days   | Transactions with computed features        |
| `transactions.scored`         | 32         | `transaction_id`| 90 days   | Scoring results with risk scores           |
| `alerts.fraud`                | 16         | `alert_id`      | 365 days  | Confirmed fraud alerts                     |
| `alerts.suspicious`           | 16         | `customer_id`   | 90 days   | Suspicious activity for review             |
| `audit.scoring-decisions`     | 32         | `transaction_id`| 7 years   | Complete audit trail of scoring decisions   |
| `models.feature-vectors`      | 32         | `customer_id`   | 7 days    | Computed feature vectors for model input   |
| `events.customer-profile`     | 16         | `customer_id`   | 30 days   | Customer profile change events             |

#### 6. Replay Capability for Debugging and Model Validation

Kafka's durable, offset-based storage enables **time-travel debugging** — a capability that is transformative for fraud detection:

- **Incident investigation**: When a fraud event is detected days after the fact, analysts can replay the original transaction stream to understand why the scoring engine missed it.
- **Model backtesting**: Before deploying a new model version, the team replays 30 days of production traffic through the candidate model to measure precision/recall improvements.
- **Rule validation**: New detection rules are validated by replaying historical events through a shadow consumer group.
- **Bug reproduction**: Production issues can be reproduced by resetting a consumer group's offsets to the problematic time window.

```bash
# Reset consumer group to replay transactions from a specific timestamp
kafka-consumer-groups.sh --bootstrap-server kafka:9092 \
  --group fraud-scoring-engine-shadow \
  --topic transactions.raw \
  --reset-offsets \
  --to-datetime 2026-05-15T00:00:00.000 \
  --execute
```

This is architecturally impossible with RabbitMQ (messages are deleted after acknowledgment) and impractical with SQS (14-day maximum retention, no offset-based replay).

---

## Consequences

### Positive

- **Complete audit trail**: Every transaction event is durably stored and replayable, satisfying regulatory requirements (PCI DSS, SOX, GDPR).
- **Decoupled architecture**: Producers and consumers evolve independently. New consumers (analytics, ML training, compliance) are added without modifying producers.
- **Real-time stream processing**: Native support for windowed aggregations, joins, and stateful computations via Kafka Streams / Faust.
- **Linear scalability**: Adding partitions and consumer instances scales throughput proportionally.
- **Operational replay**: Model backtesting, incident investigation, and bug reproduction leverage the same infrastructure.

### Negative

- **Operational complexity**: Kafka requires managing ZooKeeper (or KRaft in newer versions), brokers, schema registry, and Connect clusters. Mitigation: use **Confluent Cloud** or a managed Kafka offering for non-production environments; dedicated SRE team for production.
- **Learning curve**: Kafka's semantics (partitions, consumer groups, rebalancing, exactly-once configuration) are more complex than RabbitMQ's simple queue model. Mitigation: internal training sessions, shared client libraries with sane defaults, and runbooks.
- **Cost of retention**: Storing 30-90 days of high-volume event data requires significant disk (estimated 15-25 TB for 30 days at current volume). Mitigation: tiered storage (Confluent Tiered Storage or S3-backed) for cold data; aggressive compression (Zstandard).
- **Rebalancing storms**: Consumer group rebalances during deployments can cause temporary processing pauses. Mitigation: use **cooperative sticky rebalancing** (`CooperativeStickyAssignor`), incremental rolling deployments, and static group membership.

### Neutral

- **Schema management**: Kafka does not enforce schemas natively. We adopt **Confluent Schema Registry** with Avro/Protobuf schemas and compatibility checks (BACKWARD compatibility mode) to prevent breaking changes.
- **Monitoring**: Kafka exposes JMX metrics consumed by Prometheus via the JMX Exporter. Dashboards for consumer lag, broker health, and throughput are implemented in Grafana.

---

## Alternatives Considered

| System               | Verdict   | Reason for Rejection                                                                                              |
|----------------------|-----------|-------------------------------------------------------------------------------------------------------------------|
| RabbitMQ             | Rejected  | No durable replay; limited throughput at scale; no native stream processing; destructive consumption model         |
| Amazon SQS/SNS      | Rejected  | 14-day max retention; no offset-based replay; limited throughput per queue; vendor lock-in                        |
| Amazon Kinesis       | Evaluated | Strong streaming support but 7-day max retention (without enhanced fan-out); limited partition (shard) count       |
| Apache Pulsar        | Evaluated | Promising architecture (tiered storage, multi-tenancy) but smaller ecosystem and operational knowledge base        |
| Redis Streams        | Rejected  | Memory-bound storage; not suitable for high-volume, long-retention event sourcing                                 |

---

## References

- [Kafka: The Definitive Guide (O'Reilly)](https://www.confluent.io/resources/kafka-the-definitive-guide-v2/)
- [Exactly-Once Semantics in Apache Kafka](https://www.confluent.io/blog/exactly-once-semantics-are-possible-heres-how-apache-kafka-does-it/)
- [KRaft: Kafka Without ZooKeeper](https://developer.confluent.io/learn/kraft/)
- [Confluent Tiered Storage](https://docs.confluent.io/platform/current/kafka/tiered-storage.html)
- [Faust: Stream Processing for Python](https://faust-streaming.github.io/faust/)
