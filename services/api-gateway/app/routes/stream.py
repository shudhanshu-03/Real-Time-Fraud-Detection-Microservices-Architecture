import asyncio
import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from aiokafka import AIOKafkaConsumer
from app.config import settings

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["stream"])


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)

        for dead_conn in disconnected:
            self.disconnect(dead_conn)


manager = ConnectionManager()

# Background Kafka consumer task
kafka_consumer_task = None


async def consume_evaluated_transactions():
    while True:
        try:
            consumer = AIOKafkaConsumer(
                "fraud.evaluated.transactions",
                bootstrap_servers=settings.kafka_bootstrap_servers,
                group_id="api-gateway-ws-group",
                value_deserializer=lambda x: x.decode("utf-8"),
            )

            await consumer.start()
            try:
                async for msg in consumer:
                    logger.info("broadcasting_transaction", offset=msg.offset)
                    await manager.broadcast(msg.value)
            finally:
                await consumer.stop()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("kafka_consumer_error", error=str(e))
            await asyncio.sleep(5)


def start_kafka_consumer():
    global kafka_consumer_task
    kafka_consumer_task = asyncio.create_task(consume_evaluated_transactions())


def stop_kafka_consumer():
    if kafka_consumer_task:
        kafka_consumer_task.cancel()


@router.websocket("/ws/live-feed")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # We just keep the connection open, no incoming messages expected
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
