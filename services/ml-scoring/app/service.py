import logging
import time
import grpc
from google.protobuf.timestamp_pb2 import Timestamp

from fraud_common.pb import ml_scoring_pb2
from fraud_common.pb import ml_scoring_pb2_grpc
from app.model_engine import MockModelEngine

logger = logging.getLogger(__name__)

class MLScoringServiceServicer(ml_scoring_pb2_grpc.MLScoringServiceServicer):
    def __init__(self):
        self.model_engine = MockModelEngine()
        logger.info("MLScoringServiceServicer initialized with MockModelEngine.")

    async def PredictFraud(self, request, context):
        start_time = time.perf_counter()
        
        try:
            # Perform inference using the mock model engine
            prediction = self.model_engine.predict(request)
            
            end_time = time.perf_counter()
            prediction_time_ms = (end_time - start_time) * 1000
            
            result = ml_scoring_pb2.PredictionResult(
                ml_score=prediction["score"],
                anomaly_flags=prediction["flags"],
                model_version=prediction["model_version"],
                confidence=prediction["confidence"],
                prediction_time_ms=prediction_time_ms,
                feature_importances=prediction.get("feature_importances", {})
            )
            
            logger.info(f"Scored transaction {request.transaction_id} -> {prediction['score']:.4f} in {prediction_time_ms:.2f}ms")
            return result
            
        except Exception as e:
            logger.error(f"Error predicting fraud for {request.transaction_id}: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            raise

    async def GetModelInfo(self, request, context):
        return ml_scoring_pb2.ModelInfo(
            model_id="xgboost-ensemble-v1",
            version="1.0.0",
            accuracy=0.95,
            precision=0.89,
            recall=0.91,
            f1_score=0.90,
            auc_roc=0.98,
            last_trained="2026-05-30T00:00:00Z",
            status="ACTIVE",
            traffic_percentage=100.0,
            total_predictions=1337
        )

    async def GetMLHealth(self, request, context):
        now = Timestamp()
        now.GetCurrentTime()
        return ml_scoring_pb2.HealthResponse(
            status="SERVING",
            service="ml-scoring-service",
            version="1.0.0",
            timestamp=now,
            loaded_models=1,
            gpu_utilization=0.0,
            avg_inference_latency_ms=12.5
        )
