import asyncio
import logging
import grpc
import sys

# Ensure shared and pb directories are in path
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared', 'fraud_common', 'pb'))

from fraud_common.pb import ml_scoring_pb2, ml_scoring_pb2_grpc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def run():
    target = 'localhost:8084'
    logger.info(f"Connecting to ML Scoring Service at {target}")
    
    async with grpc.aio.insecure_channel(target) as channel:
        stub = ml_scoring_pb2_grpc.MLScoringServiceStub(channel)
        
        request = ml_scoring_pb2.PredictionRequest(
            transaction_id="txn_test_12345",
            amount=15000.0,  # High amount should trigger UNUSUAL_AMOUNT flag
            merchant_category="electronic_store",
            channel="online",
            is_recurring=False,
            is_international=True,
            device_fingerprint="device_xyz_987",
            ip_address="192.168.1.100",
            location_lat=40.7128,
            location_lon=-74.0060,
            hour_of_day=3,  # Late night, triggers TIME_ANOMALY
            day_of_week=5,
            transaction_frequency=12.5,
            avg_transaction_amount=150.0,
            std_transaction_amount=20.0,
            max_transaction_amount=500.0,
            distinct_merchants=4,
            distinct_devices=2,
            distinct_countries=1,
            time_since_last_transaction=30.0,  # < 60s, triggers VELOCITY_SPIKE
            distance_from_last_transaction=1500.0,  # > 1000km, triggers IMPOSSIBLE_TRAVEL
        )
        
        logger.info(f"Sending PredictionRequest for {request.transaction_id}...")
        try:
            response = await stub.PredictFraud(request)
            logger.info("Received PredictionResult:")
            logger.info(f"  ML Score: {response.ml_score:.4f}")
            logger.info(f"  Anomaly Flags: {list(response.anomaly_flags)}")
            logger.info(f"  Model Version: {response.model_version}")
            logger.info(f"  Confidence: {response.confidence:.4f}")
            logger.info(f"  Prediction Time: {response.prediction_time_ms:.2f}ms")
            logger.info(f"  Feature Importances: {dict(response.feature_importances)}")
        except grpc.RpcError as e:
            logger.error(f"gRPC Call failed: {e.code()} - {e.details()}")

if __name__ == "__main__":
    asyncio.run(run())
