import json
import asyncio
import structlog
from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.config import settings
from app.grpc_clients.clients import grpc_clients
from app.orchestrator.score_aggregator import ScoreAggregator
from app.models.scoring import ScoringWeights, DecisionThresholds
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
import redis.asyncio as redis

logger = structlog.get_logger(__name__)


class OrchestratorApp:
    def __init__(self):
        self.consumer = None
        self.producer = None
        self.task = None
        self.redis_client = None

    async def start(self):
        await grpc_clients.connect()

        self.consumer = AIOKafkaConsumer(
            settings.input_topic,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id="fraud-orchestrator-group",
            value_deserializer=lambda x: json.loads(x.decode("utf-8")),
        )
        self.producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers, value_serializer=lambda x: json.dumps(x).encode("utf-8")
        )
        self.redis_client = redis.from_url(settings.redis_url)

        await self.consumer.start()
        await self.producer.start()

        self.task = asyncio.create_task(self.consume())
        logger.info("fraud_orchestrator.started")

    async def stop(self):
        if self.task:
            self.task.cancel()
        if self.consumer:
            await self.consumer.stop()
        if self.producer:
            await self.producer.stop()
        if self.redis_client:
            await self.redis_client.close()
        await grpc_clients.disconnect()
        logger.info("fraud_orchestrator.stopped")

    async def consume(self):
        logger.info("orchestrator_consume_loop_started")
        try:
            async for msg in self.consumer:
                logger.info("received_message", topic=msg.topic, partition=msg.partition)
                payload = msg.value.get("payload", msg.value)
                if not payload:
                    continue

                logger.info("processing_transaction", txn_id=payload.get("transaction_id"))

                # Fetch scores concurrently
                rule_task = asyncio.create_task(grpc_clients.evaluate_rule_engine(payload))
                ml_task = asyncio.create_task(grpc_clients.evaluate_ml_scoring(payload))
                graph_task = asyncio.create_task(grpc_clients.evaluate_graph_analysis(payload))

                rule_score, ml_score, graph_score = await asyncio.gather(rule_task, ml_task, graph_task)

                # Aggregate
                weights = ScoringWeights(w_rule=0.4, w_ml=0.4, w_graph=0.2, w_history=0.0)
                thresholds = DecisionThresholds()

                final_score = ScoreAggregator.aggregate(
                    rule_score=rule_score,
                    ml_score=ml_score,
                    graph_score=graph_score,
                    historical_score=0.0,
                    weights=weights,
                )

                decision = ScoreAggregator.make_decision(final_score, thresholds)

                # Publish evaluated event
                evaluated_event = {
                    "transaction_id": payload.get("transaction_id"),
                    "customer_id": payload.get("customer_id"),
                    "merchant_name": payload.get("merchant_name"),
                    "amount": payload.get("amount"),
                    "currency": payload.get("currency", "USD"),
                    "timestamp": payload.get("timestamp"),
                    "rule_score": rule_score,
                    "ml_score": ml_score,
                    "graph_score": graph_score,
                    "final_score": final_score * 100,  # Frontend expects 0-100
                    "decision": decision.value,
                    "type": payload.get("transaction_type", "CREDIT"),
                }

                await self.producer.send_and_wait(settings.output_topic, value=evaluated_event)
                logger.info("published_evaluated_event", txn_id=payload.get("transaction_id"))

                # Update KPIs in Redis
                if self.redis_client:
                    try:
                        await self.redis_client.incr("metrics:total_tx")
                        amount = float(payload.get("amount", 0.0))
                        await self.redis_client.incrbyfloat("metrics:total_volume", amount)
                        if decision.value == "block":
                            await self.redis_client.incr("metrics:blocked_tx")
                            await self.redis_client.incr("metrics:fraud_tx")
                        elif decision.value == "review":
                            await self.redis_client.incr("metrics:fraud_tx")
                    except Exception as redis_err:
                        logger.error("redis_metrics_error", error=str(redis_err))

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("consume_error", error=str(e))


orchestrator_app = OrchestratorApp()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await orchestrator_app.start()
    yield
    await orchestrator_app.stop()


app = FastAPI(title="Fraud Orchestrator", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}
