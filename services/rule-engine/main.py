import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from grpc.aio import server as grpc_server

from rest_api import router as rules_router
import rule_engine_pb2_grpc
from grpc_server import RuleEngineServicer
from db import init_db, close_db
from redis_client import init_redis, close_redis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def start_grpc_server():
    server = grpc_server()
    rule_engine_pb2_grpc.add_RuleEngineServiceServicer_to_server(RuleEngineServicer(), server)
    server.add_insecure_port("[::]:50051")
    logger.info("Starting gRPC server on port 50051...")
    await server.start()
    return server


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing database...")
    await init_db()

    logger.info("Initializing redis...")
    await init_redis()

    logger.info("Starting background gRPC server...")
    grpc_task = asyncio.create_task(start_grpc_server())

    yield

    # Shutdown
    logger.info("Shutting down...")
    await close_db()
    await close_redis()

    server = await grpc_task
    await server.stop(0)


app = FastAPI(title="Rule Engine Service", lifespan=lifespan)

app.include_router(rules_router, prefix="/api/v1/rules")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "rule-engine"}


if __name__ == "__main__":
    import uvicorn

    # Use loop="asyncio" to prevent issues with gRPC aio server
    uvicorn.run("main:app", host="0.0.0.0", port=8003, log_level="info", loop="asyncio")
