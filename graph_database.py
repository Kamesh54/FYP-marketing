"""
Neo4j Graph Database Module
Handles all graph database operations, connection management, and query execution.
Designed to work alongside SQLite for hybrid data storage.
"""

import os
import logging
import json
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from contextlib import contextmanager
from urllib.parse import urlparse

from neo4j import GraphDatabase, Driver, Session
from neo4j.exceptions import AuthError, ConnectionError as Neo4jConnectionError, ServiceUnavailable
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==================== CONFIGURATION ====================

# Neo4j Connection Configuration
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")
NEO4J_ENABLED = os.getenv("NEO4J_ENABLED", "False").lower() == "true"

# Connection pool settings
MAX_POOL_SIZE = int(os.getenv("NEO4J_POOL_SIZE", "50"))
CONNECTION_TIMEOUT = int(os.getenv("NEO4J_TIMEOUT", "30"))
SOCKET_KEEPALIVE = int(os.getenv("NEO4J_KEEPALIVE", "60"))

# ==================== GRAPH DATABASE CLIENT ====================

class GraphDatabaseClient:
    """
    Neo4j Graph Database Client with connection pooling, error handling, and utilities.
    Provides both low-level query execution and high-level convenience methods.
    """
    
    def __init__(self):
        """Initialize graph database client and driver."""
        self.driver: Optional[Driver] = None
        self.connected = False
        self.enable_kg = NEO4J_ENABLED
        
        if self.enable_kg:
            self._initialize_driver()
    
    def _initialize_driver(self) -> None:
        """Initialize Neo4j driver with connection pooling."""
        try:
            logger.info(f"Connecting to Neo4j at {NEO4J_URI}...")
            
            self.driver = GraphDatabase.driver(
                NEO4J_URI,
                auth=(NEO4J_USER, NEO4J_PASSWORD),
                max_pool_size=MAX_POOL_SIZE,
                connection_timeout=CONNECTION_TIMEOUT,
                socket_keep_alive_timeout=SOCKET_KEEPALIVE,
                encrypted=self._should_use_encryption(),
                trust=self._get_trust_setting()
            )
            
            # Verify connection
            self.driver.verify_connectivity()
            self.connected = True
            logger.info("✅ Neo4j connection established successfully")
            
            # Initialize database indexes and constraints
            self._initialize_schema()
            
        except AuthError as e:
            logger.error(f"❌ Neo4j Authentication Error: {e}")
            self.connected = False
            raise
        except Neo4jConnectionError as e:
            logger.error(f"❌ Neo4j Connection Error: {e}")
            self.connected = False
            raise
        except Exception as e:
            logger.error(f"❌ Neo4j Initialization Error: {e}")
            self.connected = False
            raise
    
    def _should_use_encryption(self) -> bool:
        """Determine if encryption should be enabled."""
        return NEO4J_URI.startswith("bolt+s://") or NEO4J_URI.startswith("neo4j+s://")
    
    def _get_trust_setting(self) -> str:
        """Get trust setting for SSL certificates."""
        if os.getenv("NEO4J_TRUST_CERTS", "TRUST_ALL_CERTIFICATES") == "TRUST_SYSTEM_CA_SIGNED_CERTIFICATES":
            return "TRUST_SYSTEM_CA_SIGNED_CERTIFICATES"
        return "TRUST_ALL_CERTIFICATES"
    
    @contextmanager
    def get_session(self, access_mode: str = "WRITE"):
        """
        Context manager for Neo4j session.
        
        Args:
            access_mode: "READ" or "WRITE"
        
        Yields:
            Neo4j session object
        """
        if not self.connected or not self.driver:
            logger.warning("Graph database not connected, skipping operation")
            yield None
            return
        
        session = self.driver.session(database=NEO4J_DATABASE)
        try:
            yield session
        except Exception as e:
            logger.error(f"Session error: {e}")
            raise
        finally:
            session.close()
    
    def _initialize_schema(self) -> None:
        """Initialize database schema with constraints and indexes."""
        if not self.connected:
            return
        
        constraints_and_indexes = [
            # Constraints on identifiers
            "CREATE CONSTRAINT user_id IF NOT EXISTS FOR (u:User) REQUIRE u.user_id IS UNIQUE",
            "CREATE CONSTRAINT brand_id IF NOT EXISTS FOR (b:Brand) REQUIRE b.brand_id IS UNIQUE",
            "CREATE CONSTRAINT campaign_id IF NOT EXISTS FOR (c:Campaign) REQUIRE c.campaign_id IS UNIQUE",
            "CREATE CONSTRAINT content_id IF NOT EXISTS FOR (c:Content) REQUIRE c.content_id IS UNIQUE",
            "CREATE CONSTRAINT keyword_id IF NOT EXISTS FOR (k:Keyword) REQUIRE k.keyword_id IS UNIQUE",
            "CREATE CONSTRAINT competitor_id IF NOT EXISTS FOR (c:Competitor) REQUIRE c.competitor_id IS UNIQUE",
            
            # Indexes for common queries
            "CREATE INDEX user_email IF NOT EXISTS FOR (u:User) ON (u.email)",
            "CREATE INDEX brand_name IF NOT EXISTS FOR (b:Brand) ON (b.brand_name)",
            "CREATE INDEX content_type IF NOT EXISTS FOR (c:Content) ON (c.content_type)",
            "CREATE INDEX keyword_term IF NOT EXISTS FOR (k:Keyword) ON (k.term)",
            "CREATE INDEX campaign_user IF NOT EXISTS FOR (c:Campaign) ON (c.user_id)",
            "CREATE INDEX competitor_domain IF NOT EXISTS FOR (c:Competitor) ON (c.domain)",
            "CREATE INDEX metric_platform IF NOT EXISTS FOR (m:Metric) ON (m.platform)",
            "CREATE INDEX created_at IF NOT EXISTS FOR (n) ON (n.created_at)",
        ]
        
        try:
            with self.get_session() as session:
                if session:
                    for constraint_or_index in constraints_and_indexes:
                        try:
                            session.run(constraint_or_index)
                            logger.debug(f"Schema initialized: {constraint_or_index[:50]}...")
                        except Exception as e:
                            # Constraint/index might already exist, which is fine
                            logger.debug(f"Schema update note: {str(e)[:100]}")
        except Exception as e:
            logger.warning(f"Schema initialization encountered issues: {e}")
    
    # ==================== CORE QUERY METHODS ====================
    
    def query(self, cypher: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict]:
        """
        Execute a Cypher query and return results.
        
        Args:
            cypher: Cypher query string
            parameters: Query parameters
        
        Returns:
            List of result records as dictionaries
        """
        if not self.connected:
            logger.warning("Graph database not connected")
            return []
        
        try:
            with self.get_session() as session:
                if not session:
                    return []
                
                result = session.run(cypher, parameters or {})
                records = [dict(record) for record in result]
                logger.debug(f"Query executed successfully, {len(records)} records returned")
                return records
        
        except Exception as e:
            logger.error(f"Query execution error: {e}\nCypher: {cypher}")
            return []
    
    def query_single(self, cypher: str, parameters: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
        """
        Execute a Cypher query and return single result.
        
        Args:
            cypher: Cypher query string
            parameters: Query parameters
        
        Returns:
            First result record as dictionary or None
        """
        results = self.query(cypher, parameters)
        return results[0] if results else None
    
    def execute_write(self, cypher: str, parameters: Optional[Dict[str, Any]] = None) -> int:
        """
        Execute a write operation (CREATE, UPDATE, DELETE).
        
        Args:
            cypher: Cypher query string
            parameters: Query parameters
        
        Returns:
            Number of nodes/relationships affected
        """
        if not self.connected:
            logger.warning("Graph database not connected")
            return 0
        
        try:
            with self.get_session() as session:
                if not session:
                    return 0
                
                result = session.run(cypher, parameters or {})
                summary = result.consume()
                
                affected = (
                    summary.counters.nodes_created +
                    summary.counters.nodes_deleted +
                    summary.counters.relationships_created +
                    summary.counters.relationships_deleted
                )
                
                logger.debug(f"Write operation completed, {affected} items affected")
                return affected
        
        except Exception as e:
            logger.error(f"Write operation error: {e}\nCypher: {cypher}")
            return 0
    
    # ==================== HIGH-LEVEL OPERATIONS ====================
    
    def create_node(
        self,
        label: str,
        properties: Dict[str, Any],
        merge: bool = True
    ) -> bool:
        """
        Create or merge a node in the graph.
        
        Args:
            label: Node label (e.g., "User", "Brand", "Keyword")
            properties: Node properties as dictionary
            merge: If True, merge (update if exists); if False, create new
        
        Returns:
            True if successful, False otherwise
        """
        if not properties:
            return False
        
        # Determine unique identifier for merge
        unique_key = None
        unique_key_prop = None
        if label == "User":
            unique_key_prop = "user_id"
            unique_key = properties.get("user_id")
        elif label == "Brand":
            unique_key_prop = "brand_id"
            unique_key = properties.get("brand_id")
        elif label == "Campaign":
            unique_key_prop = "campaign_id"
            unique_key = properties.get("campaign_id")
        elif label == "Content":
            unique_key_prop = "content_id"
            unique_key = properties.get("content_id")
        elif label == "Keyword":
            unique_key_prop = "keyword_id"
            unique_key = properties.get("keyword_id") or properties.get("term")
        
        if merge and unique_key:
            cypher = f"""
            MERGE (n:{label} {{{unique_key_prop}: $unique_key}})
            ON CREATE SET n = $props
            ON MATCH  SET n += $props
            RETURN n
            """
            props = {k: v for k, v in properties.items()}
        else:
            # Convert properties to Cypher format
            props_str = ", ".join([f"{k}: ${k}" for k in properties.keys()])
            cypher = f"CREATE (n:{label} {{{props_str}}}) RETURN n"
            props = properties

        try:
            if merge and unique_key:
                result = self.execute_write(cypher, {"unique_key": unique_key, "props": props})
            else:
                result = self.execute_write(cypher, props)
            return result > 0
        except Exception as e:
            logger.error(f"Failed to create {label} node: {e}")
            return False
    
    def create_relationship(
        self,
        node1_label: str,
        node1_id: str,
        node1_key: str,
        relationship_type: str,
        node2_label: str,
        node2_id: str,
        node2_key: str,
        properties: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Create a relationship between two nodes.
        
        Args:
            node1_label: First node label
            node1_id: First node identifier value
            node1_key: First node identifier key
            relationship_type: Relationship type (e.g., "OWNS", "TARGETS")
            node2_label: Second node label
            node2_id: Second node identifier value
            node2_key: Second node identifier key
            properties: Relationship properties
        
        Returns:
            True if successful
        """
        props_str = ""
        params = {
            "id1": node1_id,
            "id2": node2_id,
        }
        
        if properties:
            props_str = "{" + ", ".join([f"{k}: ${k}" for k in properties.keys()]) + "}"
            params.update(properties)
        
        cypher = f"""
        MATCH (a:{node1_label} {{{node1_key}: $id1}})
        MATCH (b:{node2_label} {{{node2_key}: $id2}})
        MERGE (a)-[r:{relationship_type}{props_str}]->(b)
        RETURN r
        """
        
        try:
            result = self.execute_write(cypher, params)
            return result > 0
        except Exception as e:
            logger.error(f"Failed to create relationship {relationship_type}: {e}")
            return False
    
    def update_node_properties(
        self,
        label: str,
        node_id: str,
        node_key: str,
        properties: Dict[str, Any]
    ) -> bool:
        """
        Update properties of an existing node.
        
        Args:
            label: Node label
            node_id: Node identifier value
            node_key: Node identifier key
            properties: Properties to update
        
        Returns:
            True if successful
        """
        if not properties:
            return False
        
        props_str = ", ".join([f"n.{k} = ${k}" for k in properties.keys()])
        cypher = f"MATCH (n:{label} {{{node_key}: $id}}) SET {props_str} RETURN n"
        
        params = {**properties, "id": node_id}
        
        try:
            result = self.execute_write(cypher, params)
            return result > 0
        except Exception as e:
            logger.error(f"Failed to update {label} node: {e}")
            return False
    
    def delete_node(self, label: str, node_id: str, node_key: str, cascade: bool = False) -> bool:
        """
        Delete a node from the graph.
        
        Args:
            label: Node label
            node_id: Node identifier value
            node_key: Node identifier key
            cascade: If True, delete relationships too
        
        Returns:
            True if successful
        """
        if cascade:
            cypher = f"MATCH (n:{label} {{{node_key}: $id}}) DETACH DELETE n RETURN COUNT(n)"
        else:
            cypher = f"MATCH (n:{label} {{{node_key}: $id}}) DELETE n RETURN COUNT(n)"
        
        try:
            result = self.execute_write(cypher, {"id": node_id})
            return result > 0
        except Exception as e:
            logger.error(f"Failed to delete {label} node: {e}")
            return False
    
    # ==================== RELATIONSHIP QUERIES ====================
    
    def get_node_relationships(
        self,
        label: str,
        node_id: str,
        node_key: str,
        relationship_type: Optional[str] = None,
        direction: str = "ALL"
    ) -> List[Dict]:
        """
        Get all relationships for a specific node.
        
        Args:
            label: Node label
            node_id: Node identifier value
            node_key: Node identifier key
            relationship_type: Optional specific relationship type
            direction: "IN", "OUT", or "ALL"
        
        Returns:
            List of related nodes with relationship details
        """
        rel_filter = f":{relationship_type}" if relationship_type else ""
        
        if direction == "IN":
            cypher = f"""
            MATCH (n:{label} {{{node_key}: $id}})<-[r{rel_filter}]-(related)
            RETURN related, r, TYPE(r) as rel_type
            """
        elif direction == "OUT":
            cypher = f"""
            MATCH (n:{label} {{{node_key}: $id}})-[r{rel_filter}]->(related)
            RETURN related, r, TYPE(r) as rel_type
            """
        else:
            cypher = f"""
            MATCH (n:{label} {{{node_key}: $id}})-[r{rel_filter}]-(related)
            RETURN related, r, TYPE(r) as rel_type
            """
        
        return self.query(cypher, {"id": node_id})
    
    def find_similar_nodes(
        self,
        label: str,
        node_id: str,
        node_key: str,
        similarity_threshold: float = 0.7,
        max_results: int = 10
    ) -> List[Dict]:
        """
        Find similar nodes based on shared relationships and properties.
        
        Args:
            label: Node label
            node_id: Node identifier value
            node_key: Node identifier key
            similarity_threshold: Minimum similarity score (0-1)
            max_results: Maximum number of results
        
        Returns:
            List of similar nodes with similarity scores
        """
        cypher = f"""
        MATCH (source:{label} {{{node_key}: $id}})
        MATCH (source)-[r1]->(related)-[r2]->(similar:{label})
        WHERE similar.{node_key} <> $id
        WITH similar, COUNT(*) as shared_connections
        RETURN similar, shared_connections
        ORDER BY shared_connections DESC
        LIMIT $limit
        """
        
        return self.query(cypher, {
            "id": node_id,
            "limit": max_results
        })
    
    def get_relationship_path(
        self,
        start_label: str,
        start_id: str,
        start_key: str,
        end_label: str,
        end_id: str,
        end_key: str,
        max_depth: int = 5
    ) -> List[Dict]:
        """
        Find relationship paths between two nodes.
        
        Args:
            start_label: Starting node label
            start_id: Starting node identifier value
            start_key: Starting node identifier key
            end_label: Ending node label
            end_id: Ending node identifier value
            end_key: Ending node identifier key
            max_depth: Maximum relationship depth to search
        
        Returns:
            List of paths between nodes
        """
        cypher = f"""
        MATCH path = shortestPath((start:{start_label} {{{start_key}: $start_id}})-[*1..{max_depth}]-(end:{end_label} {{{end_key}: $end_id}}))
        WITH [node in nodes(path) | {{label: labels(node)[0], id: node}}] as nodes_in_path,
             [rel in relationships(path) | {{type: type(rel)}}] as rels_in_path
        RETURN nodes_in_path, rels_in_path, LENGTH(path) as path_length
        """
        
        return self.query(cypher, {
            "start_id": start_id,
            "end_id": end_id
        })
    
    # ==================== AGGREGATION & ANALYTICS ====================
    
    def get_node_stats(self, label: str) -> Dict[str, Any]:
        """
        Get statistics for nodes of a specific label.
        
        Args:
            label: Node label
        
        Returns:
            Dictionary with count, creation stats, etc.
        """
        cypher = f"""
        MATCH (n:{label})
        WITH COUNT(n) as total_count,
             MIN(n.created_at) as earliest_creation,
             MAX(n.created_at) as latest_creation
        RETURN {{
            total_count: total_count,
            earliest_creation: earliest_creation,
            latest_creation: latest_creation
        }} as stats
        """
        
        result = self.query_single(cypher)
        return result.get("stats", {}) if result else {}
    
    def get_relationship_stats(self, relationship_type: str) -> Dict[str, Any]:
        """
        Get statistics for relationships of a specific type.
        
        Args:
            relationship_type: Relationship type
        
        Returns:
            Dictionary with relationship stats
        """
        cypher = f"""
        MATCH (a)-[r:{relationship_type}]->(b)
        WITH COUNT(r) as total_rels,
             COUNT(DISTINCT a) as unique_sources,
             COUNT(DISTINCT b) as unique_targets
        RETURN {{
            total_relationships: total_rels,
            unique_sources: unique_sources,
            unique_targets: unique_targets
        }} as stats
        """
        
        result = self.query_single(cypher)
        return result.get("stats", {}) if result else {}
    
    def get_graph_summary(self) -> Dict[str, Any]:
        """
        Get overall graph statistics and summary.
        
        Returns:
            Dictionary with comprehensive graph stats
        """
        cypher = """
        CALL apoc.meta.stats() YIELD nodeCount, relCount
        RETURN {
            total_nodes: nodeCount,
            total_relationships: relCount,
            timestamp: datetime()
        } as summary
        """
        
        try:
            result = self.query_single(cypher)
            return result.get("summary", {}) if result else {}
        except Exception as e:
            logger.debug(f"Summary query failed (apoc might not be available): {e}")
            # Fallback to basic counts
            nodes = self.query_single("MATCH (n) RETURN COUNT(n) as count")
            rels = self.query_single("MATCH ()-[r]-() RETURN COUNT(r) as count")
            return {
                "total_nodes": nodes.get("count", 0) if nodes else 0,
                "total_relationships": rels.get("count", 0) if rels else 0,
                "timestamp": datetime.now().isoformat()
            }
    
    # ==================== CLEANUP & MAINTENANCE ====================
    
    def clear_database(self, confirm: bool = False) -> bool:
        """
        Clear all data from the graph database (USE WITH CAUTION).
        
        Args:
            confirm: Must be True to actually clear database
        
        Returns:
            True if successful
        """
        if not confirm:
            logger.warning("Database clear requested but not confirmed")
            return False
        
        cypher = "MATCH (n) DETACH DELETE n"
        
        try:
            self.execute_write(cypher)
            logger.warning("⚠️  Graph database cleared")
            return True
        except Exception as e:
            logger.error(f"Failed to clear database: {e}")
            return False
    
    def close(self) -> None:
        """Close the Neo4j driver connection."""
        if self.driver:
            self.driver.close()
            self.connected = False
            logger.info("Neo4j driver closed")
    
    # ==================== TRANSACTION SUPPORT ====================
    
    @contextmanager
    def transaction(self):
        """
        Context manager for Neo4j transactions.
        
        Yields:
            Transaction context
        """
        if not self.connected:
            raise RuntimeError("Graph database not connected")
        
        with self.get_session() as session:
            if session:
                tx = session.begin_transaction()
                try:
                    yield tx
                    tx.commit()
                except Exception as e:
                    logger.error(f"Transaction error: {e}")
                    tx.rollback()
                    raise
                finally:
                    tx.close()


# ==================== SINGLETON INSTANCE ====================

# Global instance
_graph_client: Optional[GraphDatabaseClient] = None

def get_graph_client() -> GraphDatabaseClient:
    """
    Get or create the global graph database client instance.
    
    Returns:
        GraphDatabaseClient instance
    """
    global _graph_client
    if _graph_client is None:
        _graph_client = GraphDatabaseClient()
    return _graph_client


def initialize_graph_db() -> GraphDatabaseClient:
    """
    Initialize the graph database (call this on application startup).
    
    Returns:
        Initialized GraphDatabaseClient instance
    """
    client = get_graph_client()
    if client.connected:
        logger.info("✅ Graph database initialized successfully")
    else:
        logger.warning("⚠️  Graph database not connected - operating in SQLite-only mode")
    return client


def close_graph_db() -> None:
    """Close the graph database connection (call this on application shutdown)."""
    global _graph_client
    if _graph_client:
        _graph_client.close()
        _graph_client = None


# ==================== UTILITY FUNCTIONS ====================

def dict_to_cypher_props(data: Dict[str, Any]) -> str:
    """
    Convert Python dictionary to Cypher property string.
    
    Args:
        data: Dictionary to convert
    
    Returns:
        Cypher-formatted property string
    """
    props = []
    for key, value in data.items():
        if isinstance(value, str):
            props.append(f"{key}: '{value}'")
        elif isinstance(value, (int, float)):
            props.append(f"{key}: {value}")
        elif isinstance(value, bool):
            props.append(f"{key}: {str(value).lower()}")
        elif value is None:
            props.append(f"{key}: null")
        else:
            props.append(f"{key}: {json.dumps(value)}")
    return "{" + ", ".join(props) + "}"


def is_graph_db_available() -> bool:
    """
    Check if graph database is enabled and connected.
    
    Returns:
        True if graph database is available
    """
    client = get_graph_client()
    return client.connected


# ==================== EXAMPLE USAGE ====================

if __name__ == "__main__":
    """
    Example usage of the GraphDatabaseClient.
    """
    
    # Initialize client
    client = initialize_graph_db()
    
    if client.connected:
        # Example: Create a user node
        user_props = {
            "user_id": "user_123",
            "email": "user@example.com",
            "name": "John Doe",
            "tier": "premium",
            "created_at": datetime.now().isoformat()
        }
        client.create_node("User", user_props)
        print("✅ User node created")
        
        # Example: Create a brand node
        brand_props = {
            "brand_id": "brand_456",
            "brand_name": "Tech Corp",
            "industry": "technology",
            "website": "https://techcorp.example.com",
            "created_at": datetime.now().isoformat()
        }
        client.create_node("Brand", brand_props)
        print("✅ Brand node created")
        
        # Example: Create relationship
        client.create_relationship(
            "User", "user_123", "user_id",
            "OWNS",
            "Brand", "brand_456", "brand_id",
            {"since": datetime.now().isoformat()}
        )
        print("✅ Relationship created")
        
        # Example: Query relationship
        results = client.get_node_relationships("User", "user_123", "user_id")
        print(f"✅ Got {len(results)} relationships")
        
        # Example: Get graph summary
        summary = client.get_graph_summary()
        print(f"Graph Summary: {summary}")
        
        # Close connection
        close_graph_db()
    else:
        print("❌ Graph database not connected")
