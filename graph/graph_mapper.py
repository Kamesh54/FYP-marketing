"""
Entity-to-Graph Mapper
Synchronizes SQLite data to Neo4j and maintains consistency between the two data stores.
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import json

from .graph_database import get_graph_client

logger = logging.getLogger(__name__)

# ==================== BATCH OPERATIONS ====================

class GraphMapper:
    """Handles mapping and synchronization between SQL entities and graph nodes."""
    
    def __init__(self, batch_size: int = 100):
        """
        Initialize the mapper.
        
        Args:
            batch_size: Number of records to process in each batch
        """
        self.client = get_graph_client()
        self.batch_size = batch_size
        self.sync_errors = []
    
    # ==================== USER SYNCHRONIZATION ====================
    
    def sync_user_to_graph(self, user_data: Dict[str, Any]) -> bool:
        """
        Sync a user from SQL to graph database.
        
        Args:
            user_data: User data dictionary from SQLite
        
        Returns:
            True if successful
        """
        try:
            properties = {
                "user_id": str(user_data.get("id")),
                "email": user_data.get("email", ""),
                "name": user_data.get("name", ""),
                "tier": user_data.get("tier", "free"),
                "created_at": user_data.get("created_at", datetime.now().isoformat()),
                "updated_at": datetime.now().isoformat(),
                "is_active": user_data.get("is_active", True)
            }
            
            # Add optional fields
            if "preferences" in user_data:
                try:
                    properties["preferences"] = json.dumps(user_data["preferences"])
                except:
                    pass
            
            return self.client.create_node("User", properties, merge=True)
        
        except Exception as e:
            logger.error(f"Failed to sync user: {e}")
            self.sync_errors.append(f"User sync error: {e}")
            return False
    
    def sync_users_batch(self, users: List[Dict[str, Any]]) -> Tuple[int, int]:
        """
        Sync multiple users in batch.
        
        Args:
            users: List of user data dictionaries
        
        Returns:
            Tuple of (successful, failed) count
        """
        successful = 0
        failed = 0
        
        for user in users:
            if self.sync_user_to_graph(user):
                successful += 1
            else:
                failed += 1
        
        logger.info(f"User batch sync: {successful} successful, {failed} failed")
        return successful, failed
    
    # ==================== BRAND SYNCHRONIZATION ====================
    
    def sync_brand_to_graph(self, brand_data: Dict[str, Any]) -> bool:
        """
        Sync a brand from SQL to graph database.
        
        Args:
            brand_data: Brand data dictionary from SQLite
        
        Returns:
            True if successful
        """
        try:
            # Accept both 'id' and 'brand_id' as the primary key
            bid = brand_data.get("brand_id") or brand_data.get("id")
            properties = {
                "brand_id": str(bid) if bid is not None else None,
                "brand_name": brand_data.get("brand_name", ""),
                "industry": brand_data.get("industry", ""),
                # Normalise: DB stores website_url, callers may pass website
                "website": brand_data.get("website_url") or brand_data.get("website", ""),
                "description": brand_data.get("description", ""),
                "created_at": brand_data.get("created_at", datetime.now().isoformat()),
                "updated_at": datetime.now().isoformat(),
                "market_position": brand_data.get("market_position", "unknown")
            }

            if properties["brand_id"] is None:
                logger.warning("sync_brand_to_graph: no brand_id — skipping")
                return False

            return self.client.create_node("Brand", properties, merge=True)
        
        except Exception as e:
            logger.error(f"Failed to sync brand: {e}")
            self.sync_errors.append(f"Brand sync error: {e}")
            return False
    
    def sync_user_brand_relationship(self, user_id: str, brand_id: str, role: str = "owner") -> bool:
        """
        Create OWNS relationship between user and brand.
        
        Args:
            user_id: User identifier
            brand_id: Brand identifier
            role: User's role with the brand
        
        Returns:
            True if successful
        """
        try:
            properties = {
                "role": role,
                "since": datetime.now().isoformat()
            }
            
            return self.client.create_relationship(
                "User", str(user_id), "user_id",
                "OWNS",
                "Brand", str(brand_id), "brand_id",
                properties
            )
        
        except Exception as e:
            logger.error(f"Failed to sync user-brand relationship: {e}")
            self.sync_errors.append(f"Relationship sync error: {e}")
            return False
    
    def sync_brand_competitor_relationship(self, brand_id: str, competitor_id: str, threat_level: str = "medium") -> bool:
        """
        Create COMPETES_WITH relationship between brand and competitor.
        
        Args:
            brand_id: Brand identifier
            competitor_id: Competitor identifier
            threat_level: Threat level (low, medium, high)
        
        Returns:
            True if successful
        """
        try:
            properties = {
                "threat_level": threat_level,
                "since": datetime.now().isoformat()
            }
            
            return self.client.create_relationship(
                "Brand", str(brand_id), "brand_id",
                "COMPETES_WITH",
                "Competitor", str(competitor_id), "competitor_id",
                properties
            )
        
        except Exception as e:
            logger.error(f"Failed to sync brand-competitor relationship: {e}")
            self.sync_errors.append(f"Relationship sync error: {e}")
            return False
    
    # ==================== CAMPAIGN SYNCHRONIZATION ====================
    
    def sync_campaign_to_graph(self, campaign_data: Dict[str, Any]) -> bool:
        """
        Sync a campaign from SQL to graph database.
        
        Args:
            campaign_data: Campaign data dictionary from SQLite
        
        Returns:
            True if successful
        """
        try:
            properties = {
                "campaign_id": str(campaign_data.get("id")),
                "campaign_name": campaign_data.get("campaign_name", ""),
                "user_id": str(campaign_data.get("user_id", "")),
                "brand_id": str(campaign_data.get("brand_id", "")),
                "campaign_type": campaign_data.get("campaign_type", "content"),
                "objective": campaign_data.get("objective", ""),
                "status": campaign_data.get("status", "planning"),
                "budget": float(campaign_data.get("budget", 0)),
                "budget_spent": float(campaign_data.get("budget_spent", 0)),
                "created_at": campaign_data.get("created_at", datetime.now().isoformat()),
                "updated_at": datetime.now().isoformat()
            }
            
            if "start_date" in campaign_data:
                properties["start_date"] = campaign_data["start_date"]
            if "end_date" in campaign_data:
                properties["end_date"] = campaign_data["end_date"]
            
            success = self.client.create_node("Campaign", properties, merge=True)
            
            if success:
                # Create relationship with brand
                self.client.create_relationship(
                    "Brand", campaign_data.get("brand_id"), "brand_id",
                    "HAS_CONTENT",
                    "Campaign", campaign_data.get("id"), "campaign_id"
                )
            
            return success
        
        except Exception as e:
            logger.error(f"Failed to sync campaign: {e}")
            self.sync_errors.append(f"Campaign sync error: {e}")
            return False
    
    # ==================== CONTENT SYNCHRONIZATION ====================
    
    def sync_content_to_graph(self, content_data: Dict[str, Any]) -> bool:
        """
        Sync content from SQL to graph database.
        
        Args:
            content_data: Content data dictionary from SQLite
        
        Returns:
            True if successful
        """
        try:
            # generated_content schema: id (UUID), type, content (JSON), session_id, metadata (JSON)
            # Accept both 'id' (DB PK / UUID) and 'content_id' callers may pass
            cid = content_data.get("content_id") or content_data.get("id")
            if not cid:
                logger.warning("sync_content_to_graph: no content id — skipping")
                return False

            # Try to extract title from content JSON
            title = content_data.get("title", "")
            if not title:
                raw = content_data.get("content", "")
                if isinstance(raw, str) and raw.startswith("{"):
                    try:
                        parsed = json.loads(raw)
                        title = (
                            parsed.get("title") or
                            parsed.get("blog_title") or
                            parsed.get("subject") or ""
                        )
                    except Exception:
                        pass
                elif isinstance(raw, dict):
                    title = raw.get("title") or raw.get("blog_title") or ""

            # Normalise content_type: 'type' column in DB, 'content_type' in some callers
            content_type = (
                content_data.get("content_type") or
                content_data.get("type") or
                "blog_post"
            )

            properties = {
                "content_id": str(cid),
                "content_type": content_type,
                "title": title,
                "description": content_data.get("description", ""),
                "platform": content_data.get("platform", "blog"),
                "status": content_data.get("status", "draft"),
                "seo_score": float(content_data.get("seo_score") or 0),
                "engagement_rate": float(content_data.get("engagement_rate") or 0),
                "impressions": int(content_data.get("impressions") or 0),
                "clicks": int(content_data.get("clicks") or 0),
                "created_at": content_data.get("created_at", datetime.now().isoformat()),
                "updated_at": datetime.now().isoformat()
            }

            if properties["content_id"] is None:
                logger.warning("sync_content_to_graph: no content_id — skipping")
                return False
            
            # Handle tags as JSON
            if "tags" in content_data:
                try:
                    tags = content_data["tags"]
                    if isinstance(tags, str):
                        properties["tags"] = json.dumps(json.loads(tags))
                    else:
                        properties["tags"] = json.dumps(tags)
                except:
                    pass
            
            success = self.client.create_node("Content", properties, merge=True)
            
            # Create relationship with campaign if campaign_id exists
            if success and content_data.get("campaign_id"):
                self.client.create_relationship(
                    "Content", content_data.get("id"), "content_id",
                    "PART_OF",
                    "Campaign", content_data.get("campaign_id"), "campaign_id"
                )
            
            return success
        
        except Exception as e:
            logger.error(f"Failed to sync content: {e}")
            self.sync_errors.append(f"Content sync error: {e}")
            return False
    
    # ==================== KEYWORD SYNCHRONIZATION ====================
    
    def sync_keyword_to_graph(self, keyword_data: Dict[str, Any]) -> bool:
        """
        Sync keyword from SQL to graph database.
        
        Args:
            keyword_data: Keyword data dictionary from SQLite
        
        Returns:
            True if successful
        """
        try:
            properties = {
                "keyword_id": str(keyword_data.get("id")),
                "term": keyword_data.get("term", ""),
                "search_volume": int(keyword_data.get("search_volume", 0)),
                "competition_level": keyword_data.get("competition_level", "medium"),
                "difficulty_score": float(keyword_data.get("difficulty_score", 0)),
                "intent": keyword_data.get("intent", "general"),
                "created_at": keyword_data.get("created_at", datetime.now().isoformat())
            }
            
            return self.client.create_node("Keyword", properties, merge=True)
        
        except Exception as e:
            logger.error(f"Failed to sync keyword: {e}")
            self.sync_errors.append(f"Keyword sync error: {e}")
            return False
    
    def sync_brand_keyword_relationship(
        self,
        brand_id: str,
        keyword_id: str,
        priority: float = 0.5
    ) -> bool:
        """
        Create TARGETS relationship between brand and keyword.
        
        Args:
            brand_id: Brand identifier
            keyword_id: Keyword identifier
            priority: Priority level (0-1)
        
        Returns:
            True if successful
        """
        try:
            properties = {
                "priority": priority,
                "confidence": 0.8,
                "added_date": datetime.now().isoformat()
            }
            
            return self.client.create_relationship(
                "Brand", brand_id, "brand_id",
                "TARGETS",
                "Keyword", keyword_id, "keyword_id",
                properties
            )
        
        except Exception as e:
            logger.error(f"Failed to sync brand-keyword relationship: {e}")
            self.sync_errors.append(f"Relationship sync error: {e}")
            return False
    def sync_user_campaign_relationship(self, user_id: str, campaign_id: str) -> bool:
        """
        Create OWNS relationship between user and campaign.
        
        Args:
            user_id: User identifier
            campaign_id: Campaign identifier
        
        Returns:
            True if successful
        """
        try:
            properties = {
                "owner": True,
                "since": datetime.now().isoformat()
            }
            
            return self.client.create_relationship(
                "User", str(user_id), "user_id",
                "OWNS",
                "Campaign", str(campaign_id), "campaign_id",
                properties
            )
        
        except Exception as e:
            logger.error(f"Failed to sync user-campaign relationship: {e}")
            self.sync_errors.append(f"Relationship sync error: {e}")
            return False
    
    # ==================== COMPETITOR SYNCHRONIZATION ====================
    
    def sync_competitor_to_graph(self, competitor_data: Dict[str, Any]) -> bool:
        """
        Sync competitor from SQL to graph database.
        
        Args:
            competitor_data: Competitor data dictionary from SQLite
        
        Returns:
            True if successful
        """
        try:
            # Use domain as stable fallback when DB id is None
            cid = competitor_data.get("id") or competitor_data.get("competitor_id")
            domain = competitor_data.get("domain") or competitor_data.get("competitor_name", "unknown")
            unique_id = str(cid) if cid is not None else domain
            properties = {
                "competitor_id": unique_id,
                "competitor_name": competitor_data.get("competitor_name", ""),
                "domain": domain,
                "industry": competitor_data.get("industry", ""),
                "market_share": float(competitor_data.get("market_share", 0)),
                "keyword_count": int(competitor_data.get("keyword_count", 0)),
                "average_seo_score": float(competitor_data.get("average_seo_score", 0)),
                "threat_level": competitor_data.get("threat_level", "medium"),
                "created_at": competitor_data.get("created_at", datetime.now().isoformat()),
                "updated_at": datetime.now().isoformat()
            }

            return self.client.create_node("Competitor", properties, merge=True)
        
        except Exception as e:
            logger.error(f"Failed to sync competitor: {e}")
            self.sync_errors.append(f"Competitor sync error: {e}")
            return False
    
    def sync_brand_competitor_relationship(
        self,
        brand_id: str,
        competitor_id: str
    ) -> bool:
        """
        Create COMPETES_WITH relationship between brand and competitor.
        
        Args:
            brand_id: Brand identifier
            competitor_id: Competitor identifier
        
        Returns:
            True if successful
        """
        try:
            return self.client.create_relationship(
                "Brand", brand_id, "brand_id",
                "COMPETES_WITH",
                "Competitor", competitor_id, "competitor_id",
                {"since": datetime.now().isoformat()}
            )
        
        except Exception as e:
            logger.error(f"Failed to sync brand-competitor relationship: {e}")
            self.sync_errors.append(f"Relationship sync error: {e}")
            return False
    
    # ==================== METRIC SYNCHRONIZATION ====================
    
    def sync_metric_to_graph(self, metric_data: Dict[str, Any]) -> bool:
        """
        Sync metric from SQL to graph database.
        
        Args:
            metric_data: Metric data dictionary from SQLite
        
        Returns:
            True if successful
        """
        try:
            properties = {
                "metric_id": str(metric_data.get("id")),
                "platform": metric_data.get("platform", ""),
                "metric_type": metric_data.get("metric_type", "engagement"),
                "impressions": int(metric_data.get("impressions", 0)),
                "clicks": int(metric_data.get("clicks", 0)),
                "engagements": int(metric_data.get("engagements", 0)),
                "conversions": int(metric_data.get("conversions", 0)),
                "roi": float(metric_data.get("roi", 0)),
                "engagement_rate": float(metric_data.get("engagement_rate", 0)),
                "timestamp": metric_data.get("timestamp", datetime.now().isoformat()),
                "period": metric_data.get("period", "daily")
            }
            
            return self.client.create_node("Metric", properties, merge=True)
        
        except Exception as e:
            logger.error(f"Failed to sync metric: {e}")
            self.sync_errors.append(f"Metric sync error: {e}")
            return False
    
    def sync_content_metric_relationship(
        self,
        content_id: str,
        metric_id: str
    ) -> bool:
        """
        Create HAS_METRICS relationship between content and metric.
        
        Args:
            content_id: Content identifier
            metric_id: Metric identifier
        
        Returns:
            True if successful
        """
        try:
            return self.client.create_relationship(
                "Content", content_id, "content_id",
                "HAS_METRICS",
                "Metric", metric_id, "metric_id"
            )
        
        except Exception as e:
            logger.error(f"Failed to sync content-metric relationship: {e}")
            self.sync_errors.append(f"Relationship sync error: {e}")
            return False
    
    # ==================== BULK OPERATIONS ====================
    
    def sync_all_users_batch(self, users: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Batch sync all users with progress tracking.
        
        Args:
            users: List of user data
        
        Returns:
            Dictionary with statistics
        """
        total = len(users)
        successful = 0
        failed = 0
        
        for i in range(0, total, self.batch_size):
            batch = users[i:i + self.batch_size]
            s, f = self.sync_users_batch(batch)
            successful += s
            failed += f
            
            if (i + self.batch_size) % (self.batch_size * 5) == 0:
                logger.info(f"Progress: {i + self.batch_size}/{total} users synced")
        
        logger.info(f"✅ User sync complete: {successful} successful, {failed} failed")
        return {"total": total, "successful": successful, "failed": failed}
    
    def get_sync_errors(self) -> List[str]:
        """
        Get list of sync errors.
        
        Returns:
            List of error messages
        """
        return self.sync_errors
    
    def clear_sync_errors(self) -> None:
        """Clear the error log."""
        self.sync_errors = []
    
    def create_relationship(self, from_node_id: str, to_node_id: str, 
                          relationship_type: str, properties: Optional[Dict[str, Any]] = None) -> bool:
        """
        Create a generic relationship between two nodes.
        
        This is a flexible method that infers node types from ID patterns.
        
        Args:
            from_node_id: ID of source node (will determine node type)
            to_node_id: ID of target node (will determine node type)
            relationship_type: Type of relationship
            properties: Optional relationship properties
        
        Returns:
            True if successful
        """
        try:
            # Infer node types and key names from IDs or relationship type
            from_label, from_key = self._infer_node_type(from_node_id)
            to_label, to_key = self._infer_node_type(to_node_id)
            
            return self.client.create_relationship(
                from_label, str(from_node_id), from_key,
                relationship_type,
                to_label, str(to_node_id), to_key,
                properties or {}
            )
        except Exception as e:
            logger.error(f"Failed to create relationship: {e}")
            self.sync_errors.append(f"Relationship creation error: {e}")
            return False
    
    def _infer_node_type(self, node_id: str) -> Tuple[str, str]:
        """
        Infer node type and key from node ID.
        
        Args:
            node_id: Node identifier
        
        Returns:
            Tuple of (node_label, node_key)
        """
        node_id_str = str(node_id)
        
        # Try to infer from ID format or use defaults
        if node_id_str.startswith("user_"):
            return ("User", "user_id")
        elif node_id_str.startswith("brand_"):
            return ("Brand", "brand_id")
        elif node_id_str.startswith("comp_") or node_id_str.startswith("competitor_"):
            return ("Competitor", "competitor_id")
        elif node_id_str.startswith("campaign_"):
            return ("Campaign", "campaign_id")
        elif node_id_str.startswith("content_"):
            return ("Content", "content_id")
        elif node_id_str.startswith("keyword_"):
            return ("Keyword", "keyword_id")
        else:
            # Default: assume it's a numeric ID (from database)
            # Try common numeric IDs - return most likely based on context
            return ("Brand", "brand_id")


# ==================== SINGLETON INSTANCE ====================

_mapper: Optional[GraphMapper] = None

def get_graph_mapper(batch_size: int = 100) -> GraphMapper:
    """
    Get or create the global graph mapper instance.
    
    Args:
        batch_size: Batch size for operations
    
    Returns:
        GraphMapper instance
    """
    global _mapper
    if _mapper is None:
        _mapper = GraphMapper(batch_size=batch_size)
    return _mapper


if __name__ == "__main__":
    """Example usage of the graph mapper."""
    
    mapper = get_graph_mapper()
    
    # Example: Sync a user
    sample_user = {
        "id": 123,
        "email": "user@example.com",
        "name": "John Doe",
        "tier": "premium"
    }
    
    if mapper.sync_user_to_graph(sample_user):
        print("✅ User synced successfully")
    else:
        print("❌ User sync failed")
    
    # Example: Sync a brand
    sample_brand = {
        "id": 456,
        "brand_name": "Tech Corp",
        "industry": "technology",
        "website": "https://techcorp.example.com"
    }
    
    if mapper.sync_brand_to_graph(sample_brand):
        print("✅ Brand synced successfully")
        # Create relationship
        if mapper.sync_user_brand_relationship("123", "456"):
            print("✅ User-Brand relationship created")
    
    # Print errors if any
    if mapper.get_sync_errors():
        print("\nSync Errors:")
        for error in mapper.get_sync_errors():
            print(f"  - {error}")
