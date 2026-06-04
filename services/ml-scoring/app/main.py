import asyncio
import logging
import sys
import os

# Ensure pb directory is in sys.path so generated grpc files can import each other
try:
    import fraud_common
    sys.path.append(os.path.join(os.path.dirname(fraud_common.__file__), 'pb'))
except ImportError:
    pass

import grpc
from grpc_reflection.v1alpha import reflection
from fraud_common.pb import ml_scoring_pb2, ml_scoring_pb2_grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

from app.service import MLScoringServiceServicer

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ml_scoring_service")

async def serve():
    # Initialize the gRPC server
    server = grpc.aio.server()
    
    # Register the ML Scoring Service
    ml_scoring_servicer = MLScoringServiceServicer()
    ml_scoring_pb2_grpc.add_MLScoringServiceServicer_to_server(ml_scoring_servicer, server)

    # Add Health Check service
    health_servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    health_servicer.set("fraud_platform.ml.MLScoringService", health_pb2.HealthCheckResponse.SERVING)

    # Add Reflection (optional, useful for testing with grpcurl)
    SERVICE_NAMES = (
        ml_scoring_pb2.DESCRIPTOR.services_by_name['MLScoringService'].full_name,
        health.SERVICE_NAME,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(SERVICE_NAMES, server)

    # Start listening on port 50052
    listen_addr = "[::]:50052"
    server.add_insecure_port(listen_addr)
    logger.info(f"Starting ML Scoring Service on {listen_addr}...")
    await server.start()
    
    # Graceful shutdown handler
    async def server_graceful_shutdown():
        logger.info("Starting graceful shutdown...")
        await server.stop(5)
    
    # Wait for termination
    await server.wait_for_termination()

if __name__ == "__main__":
    asyncio.run(serve())
