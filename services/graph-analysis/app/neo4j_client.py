import logging
from neo4j import GraphDatabase
from typing import Dict, List

logger = logging.getLogger(__name__)


class Neo4jClient:
    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def add_transaction_to_graph(
        self, tx_id: str, card: str, merchant: str, device: str, ip: str, amount: float, timestamp: str
    ):
        query = """
        // Ensure nodes exist
        MERGE (c:Card {id: $card})
        MERGE (m:Merchant {id: $merchant})
        MERGE (d:Device {id: $device})
        MERGE (i:IP {id: $ip})
        
        // Create relationships
        MERGE (c)-[:HAS_DEVICE]->(d)
        MERGE (d)-[:HAS_IP]->(i)
        
        // Create transaction edge
        CREATE (c)-[t:TRANSACTED_AT {
            tx_id: $tx_id, 
            amount: $amount, 
            timestamp: $timestamp
        }]->(m)
        """
        with self.driver.session() as session:
            session.run(
                query,
                tx_id=tx_id,
                card=card,
                merchant=merchant,
                device=device,
                ip=ip,
                amount=amount,
                timestamp=timestamp,
            )
            logger.info(f"Added transaction {tx_id} to graph")

    def check_device_sharing(self, device: str) -> List[str]:
        """
        Check if a device is shared by multiple cards.
        Returns a list of card IDs that use this device.
        """
        query = """
        MATCH (c:Card)-[:HAS_DEVICE]->(d:Device {id: $device})
        RETURN c.id AS card_id
        """
        with self.driver.session() as session:
            result = session.run(query, device=device)
            return [record["card_id"] for record in result]

    def check_ip_cluster(self, ip: str) -> List[str]:
        """
        Check if an IP is associated with multiple devices.
        Returns a list of device IDs that use this IP.
        """
        query = """
        MATCH (d:Device)-[:HAS_IP]->(i:IP {id: $ip})
        RETURN d.id AS device_id
        """
        with self.driver.session() as session:
            result = session.run(query, ip=ip)
            return [record["device_id"] for record in result]

    def detect_fraud_ring(self, card: str) -> List[str]:
        """
        Detect a 2-hop fraud ring: Card -> Device -> IP -> Device -> OtherCard.
        Returns a list of connected card IDs that might be part of a synthetic ring.
        """
        query = """
        MATCH (c1:Card {id: $card})-[:HAS_DEVICE]->(d1:Device)-[:HAS_IP]->(i:IP)<-[:HAS_IP]-(d2:Device)<-[:HAS_DEVICE]-(c2:Card)
        WHERE c1 <> c2
        RETURN DISTINCT c2.id AS connected_card_id
        """
        with self.driver.session() as session:
            result = session.run(query, card=card)
            return [record["connected_card_id"] for record in result]

    def get_stats(self) -> Dict[str, int]:
        query = """
        MATCH (n)
        WITH count(n) as nodes
        MATCH ()-[r]->()
        RETURN nodes, count(r) as edges
        """
        with self.driver.session() as session:
            result = session.run(query).single()
            if result:
                return {"nodes": result["nodes"], "edges": result["edges"]}
        return {"nodes": 0, "edges": 0}
