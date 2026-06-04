import grpc
import structlog
import sys
import os

# Add pb directory to sys.path so generated files can find each other
pb_path = os.path.join(os.path.dirname(__file__), "..", "..", "shared", "fraud_common", "pb")
sys.path.insert(0, os.path.abspath(pb_path))

from shared.fraud_common.pb import rule_engine_pb2_grpc, rule_engine_pb2
from shared.fraud_common.pb import ml_scoring_pb2_grpc, ml_scoring_pb2
from shared.fraud_common.pb import graph_analysis_pb2_grpc, graph_analysis_pb2

logger = structlog.get_logger(__name__)


class FraudGrpcClients:
    def __init__(self):
        self.rule_engine_channel = None
        self.ml_scoring_channel = None
        self.graph_analysis_channel = None

        self.rule_client = None
        self.ml_client = None
        self.graph_client = None

    async def connect(self):
        logger.info("Connecting to gRPC services...")
        self.rule_engine_channel = grpc.aio.insecure_channel("rule-engine:50051")
        self.ml_scoring_channel = grpc.aio.insecure_channel("ml-scoring-service:50052")
        self.graph_analysis_channel = grpc.aio.insecure_channel("graph-analysis:50053")

        self.rule_client = rule_engine_pb2_grpc.RuleEngineServiceStub(self.rule_engine_channel)
        self.ml_client = ml_scoring_pb2_grpc.MLScoringServiceStub(self.ml_scoring_channel)
        self.graph_client = graph_analysis_pb2_grpc.GraphAnalysisServiceStub(self.graph_analysis_channel)
        logger.info("gRPC channels created.")

    async def disconnect(self):
        if self.rule_engine_channel:
            await self.rule_engine_channel.close()
        if self.ml_scoring_channel:
            await self.ml_scoring_channel.close()
        if self.graph_analysis_channel:
            await self.graph_analysis_channel.close()

    async def evaluate_rule_engine(self, payload: dict) -> float:
        try:
            tx_ctx = rule_engine_pb2.TransactionContext(
                transaction_id=payload.get("transaction_id", ""),
                amount=payload.get("amount", 0.0),
                merchant_id=payload.get("merchant_id", ""),
                card_number=payload.get("customer_id", ""),  # Map customer_id to card_number for now
            )
            req = rule_engine_pb2.RuleEvalRequest(transaction=tx_ctx)
            resp = await self.rule_client.EvaluateRules(req)
            return resp.rule_score
        except Exception as e:
            logger.error("rule_engine_error", error=str(e))
            return 0.0

    async def evaluate_ml_scoring(self, payload: dict) -> float:
        try:
            req = ml_scoring_pb2.PredictionRequest(
                transaction_id=payload.get("transaction_id", ""), amount=payload.get("amount", 0.0)
            )
            resp = await self.ml_client.PredictFraud(req)
            return resp.ml_score
        except Exception as e:
            logger.error("ml_scoring_error", error=str(e))
            return 0.0

    async def evaluate_graph_analysis(self, payload: dict) -> float:
        try:
            req = graph_analysis_pb2.GraphAnalysisRequest(
                transaction_id=payload.get("transaction_id", ""),
                card_number=payload.get("customer_id", ""),
                merchant_id=payload.get("merchant_id", ""),
                device_id=payload.get("device_fingerprint", ""),
                ip_address=payload.get("ip_address", ""),
                amount=payload.get("amount", 0.0),
            )
            resp = await self.graph_client.AnalyzeGraph(req)
            return resp.graph_score
        except Exception as e:
            logger.error("graph_analysis_error", error=str(e))
            return 0.0


grpc_clients = FraudGrpcClients()
