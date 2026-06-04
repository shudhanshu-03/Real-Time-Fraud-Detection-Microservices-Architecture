import logging
import time
from datetime import datetime
import grpc
from google.protobuf.timestamp_pb2 import Timestamp

from fraud_common.pb import graph_analysis_pb2
from fraud_common.pb import graph_analysis_pb2_grpc
from app.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)

class GraphAnalysisService(graph_analysis_pb2_grpc.GraphAnalysisServiceServicer):
    def __init__(self, neo4j_client: Neo4jClient):
        self.neo4j = neo4j_client

    def AnalyzeGraph(self, request, context):
        start_time = time.time()
        
        # 1. Add transaction to graph
        ts = request.timestamp.ToDatetime().isoformat() if request.HasField("timestamp") else datetime.utcnow().isoformat()
        
        try:
            self.neo4j.add_transaction_to_graph(
                tx_id=request.transaction_id,
                card=request.card_number,
                merchant=request.merchant_id,
                device=request.device_id,
                ip=request.ip_address,
                amount=request.amount,
                timestamp=ts
            )
        except Exception as e:
            logger.error(f"Error adding to graph: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Graph database error: {str(e)}")
            return graph_analysis_pb2.GraphAnalysisResult()

        # 2. Analyze Neighborhood
        patterns = []
        risk_factors = []
        graph_score = 0.0
        
        # Check Device Sharing
        cards_on_device = self.neo4j.check_device_sharing(request.device_id)
        if len(cards_on_device) > 1:
            graph_score += 0.4
            risk_factors.append(f"Card shares device with {len(cards_on_device)-1} other card(s)")
            patterns.append(graph_analysis_pb2.GraphPattern(
                pattern_type="DEVICE_SHARING_RING",
                description=f"Device {request.device_id} used by multiple cards",
                severity="HIGH" if len(cards_on_device) > 3 else "MEDIUM",
                confidence=0.8,
                involved_entities=cards_on_device + [request.device_id],
                edge_count=len(cards_on_device)
            ))
            
        # Check IP Cluster
        devices_on_ip = self.neo4j.check_ip_cluster(request.ip_address)
        if len(devices_on_ip) > 1:
            graph_score += 0.3
            risk_factors.append(f"IP associated with {len(devices_on_ip)} devices")
            patterns.append(graph_analysis_pb2.GraphPattern(
                pattern_type="IP_CLUSTER",
                description=f"IP {request.ip_address} used by multiple devices",
                severity="MEDIUM",
                confidence=0.7,
                involved_entities=devices_on_ip + [request.ip_address],
                edge_count=len(devices_on_ip)
            ))

        # Check Synthetic Fraud Ring
        connected_cards = self.neo4j.detect_fraud_ring(request.card_number)
        if len(connected_cards) > 0:
            graph_score += 0.5
            risk_factors.append(f"Card shares infrastructure with {len(connected_cards)} other card(s)")
            patterns.append(graph_analysis_pb2.GraphPattern(
                pattern_type="SYNTHETIC_IDENTITY_RING",
                description=f"Card linked to {len(connected_cards)} other distinct cards via shared devices and IPs",
                severity="CRITICAL",
                confidence=0.9,
                involved_entities=connected_cards + [request.card_number],
                edge_count=len(connected_cards) * 2
            ))
            
        # Normalize score
        graph_score = min(1.0, graph_score)
        
        analysis_time_ms = (time.time() - start_time) * 1000

        return graph_analysis_pb2.GraphAnalysisResult(
            graph_score=graph_score,
            patterns=patterns,
            risk_factors=risk_factors,
            connected_entities=len(cards_on_device) + len(devices_on_ip), # Approximate
            analysis_time_ms=analysis_time_ms,
            edges_traversed=len(cards_on_device) + len(devices_on_ip),
            traversal_depth=2
        )

    def DetectPatterns(self, request, context):
        # Placeholder for more intensive batch/async scan
        return self.AnalyzeGraph(request, context)

    def GetGraphHealth(self, request, context):
        try:
            stats = self.neo4j.get_stats()
            status = "SERVING"
            graph_status = "CONNECTED"
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            stats = {"nodes": 0, "edges": 0}
            status = "NOT_SERVING"
            graph_status = "DISCONNECTED"

        return graph_analysis_pb2.HealthResponse(
            status=status,
            service="graph-analysis-service",
            version="1.0.0",
            timestamp=Timestamp(seconds=int(time.time())),
            total_nodes=stats["nodes"],
            total_edges=stats["edges"],
            graph_db_status=graph_status,
            cache_hit_rate=0.0
        )
