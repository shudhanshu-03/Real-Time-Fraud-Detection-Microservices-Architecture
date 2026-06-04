import grpc
import time
from datetime import datetime
from google.protobuf.timestamp_pb2 import Timestamp
import sys
import os

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'shared'))
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'shared', 'fraud_common', 'pb'))

from fraud_common.pb import graph_analysis_pb2
from fraud_common.pb import graph_analysis_pb2_grpc

def run():
    print("Testing Graph Analysis gRPC Service...")
    
    # Wait for the service to start
    # Connect to localhost on port 50053
    with grpc.insecure_channel('localhost:50053') as channel:
        stub = graph_analysis_pb2_grpc.GraphAnalysisServiceStub(channel)
        
        # 1. Health check
        try:
            health_response = stub.GetGraphHealth(graph_analysis_pb2.HealthRequest())
            print(f"Health Status: {health_response.status}")
            print(f"Graph DB Status: {health_response.graph_db_status}")
            print(f"Nodes: {health_response.total_nodes}, Edges: {health_response.total_edges}")
        except Exception as e:
            print(f"Health check failed: {e}")
            return

        # 2. Add some transactions to simulate a device sharing ring
        print("\n--- Simulating Device Sharing Ring ---")
        device_id = "device_shared_123"
        cards = ["card_111", "card_222", "card_333"]
        
        for i, card in enumerate(cards):
            req = graph_analysis_pb2.GraphAnalysisRequest(
                transaction_id=f"tx_test_{i}",
                card_number=card,
                merchant_id="merchant_abc",
                device_id=device_id,
                ip_address="192.168.1.100",
                amount=100.0 + i,
                timestamp=Timestamp(seconds=int(time.time()))
            )
            print(f"Adding transaction for {card} using {device_id}...")
            res = stub.AnalyzeGraph(req)
            print(f"  Graph Score: {res.graph_score}")
            if res.patterns:
                for p in res.patterns:
                    print(f"  Pattern Detected: {p.pattern_type} ({p.severity}) - {p.description}")

        # 3. Check health again
        try:
            health_response = stub.GetGraphHealth(graph_analysis_pb2.HealthRequest())
            print(f"\nFinal Nodes: {health_response.total_nodes}, Edges: {health_response.total_edges}")
        except Exception as e:
            print(f"Final health check failed: {e}")


if __name__ == '__main__':
    run()
