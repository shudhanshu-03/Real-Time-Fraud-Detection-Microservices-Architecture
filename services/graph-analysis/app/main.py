import os
import sys
import logging
from concurrent import futures
import grpc

try:
    import fraud_common

    sys.path.append(os.path.join(os.path.dirname(fraud_common.__file__), "pb"))
except ImportError:
    pass

from fraud_common.pb import graph_analysis_pb2_grpc
from app.service import GraphAnalysisService
from app.neo4j_client import Neo4jClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def serve():
    port = os.getenv("GRPC_PORT", "50053")
    neo4j_uri = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
    neo4j_user = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password = os.getenv("NEO4J_PASSWORD", "fraud_graph_pass")

    logger.info("Initializing Neo4j Client...")
    neo4j_client = Neo4jClient(uri=neo4j_uri, user=neo4j_user, password=neo4j_password)

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    graph_service = GraphAnalysisService(neo4j_client)

    graph_analysis_pb2_grpc.add_GraphAnalysisServiceServicer_to_server(graph_service, server)

    server.add_insecure_port(f"[::]:{port}")
    server.start()

    logger.info(f"Graph Analysis Service started on port {port}")

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        neo4j_client.close()
        server.stop(0)


if __name__ == "__main__":
    serve()
