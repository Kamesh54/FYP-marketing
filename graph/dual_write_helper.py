"""
Dual-Write Helper Module

This module provides utilities for implementing the dual-write pattern:
simultaneously writing new data to both SQLite and Neo4j graphs for seamless
integration between transactional and analytical databases.

Usage:
    from graph.dual_write_helper import sync_new_user, sync_new_campaign, etc.
    
    # In your create functions:
    user_id = db.insert_user(user_data)
    sync_new_user(user_data, user_id)  # Automatically syncs to Neo4j
"""

import logging
from typing import Dict, Any, Optional, List
from graph import get_graph_mapper, is_graph_db_available

logger = logging.getLogger(__name__)


class DualWriteManager:
    """Manager for dual-write operations between SQLite and Neo4j."""
    
    def __init__(self):
        """Initialize the dual-write manager."""
        self.mapper = None
        self.enabled = is_graph_db_available()
        if self.enabled:
            try:
                self.mapper = get_graph_mapper()
                logger.info("Dual-write manager initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize dual-write: {e}")
                self.enabled = False
    
    def sync_user(self, user_data: Dict[str, Any], user_id: Optional[int] = None) -> bool:
        """
        Sync user to Neo4j after creating in SQLite.
        
        Args:
            user_data: User data dictionary
            user_id: Optional user ID (will use user_data['id'] if not provided)
        
        Returns:
            True if sync successful or graph disabled, False on error
        """
        if not self.enabled or not self.mapper:
            return True
        
        try:
            if user_id:
                user_data = {**user_data, 'id': user_id}
            
            self.mapper.sync_user_to_graph(user_data)
            logger.debug(f"Synced user {user_id or user_data.get('id')} to Neo4j")
            return True
        except Exception as e:
            logger.error(f"Failed to sync user: {e}")
            return False
    
    def sync_brand(self, brand_data: Dict[str, Any], brand_id: Optional[int] = None) -> bool:
        """Sync brand to Neo4j and create user-brand relationship."""
        if not self.enabled or not self.mapper:
            return True
        
        try:
            if brand_id:
                brand_data = {**brand_data, 'id': brand_id}
            
            self.mapper.sync_brand_to_graph(brand_data)
            
            # Create user-brand relationship if user_id exists
            user_id = brand_data.get('user_id')
            brand_id_val = brand_id or brand_data.get('id')
            if user_id and brand_id_val:
                self.mapper.sync_user_brand_relationship(str(user_id), str(brand_id_val))
            
            logger.debug(f"Synced brand {brand_id or brand_data.get('id')} to Neo4j")
            return True
        except Exception as e:
            logger.error(f"Failed to sync brand: {e}")
            return False
    
    def sync_campaign(self, campaign_data: Dict[str, Any], campaign_id: Optional[int] = None) -> bool:
        """Sync campaign to Neo4j and create user-campaign relationship."""
        if not self.enabled or not self.mapper:
            return True
        
        try:
            if campaign_id:
                campaign_data = {**campaign_data, 'id': campaign_id}
            
            self.mapper.sync_campaign_to_graph(campaign_data)
            
            # Create user-campaign relationship if user_id exists
            user_id = campaign_data.get('user_id')
            campaign_id_val = campaign_id or campaign_data.get('id')
            if user_id and campaign_id_val:
                self.mapper.sync_user_campaign_relationship(str(user_id), str(campaign_id_val))
            
            logger.debug(f"Synced campaign {campaign_id or campaign_data.get('id')} to Neo4j")
            return True
        except Exception as e:
            logger.error(f"Failed to sync campaign: {e}")
            return False
    
    def sync_content(self, content_data: Dict[str, Any], content_id: Optional[int] = None) -> bool:
        """Sync content to Neo4j."""
        if not self.enabled or not self.mapper:
            return True
        
        try:
            if content_id:
                content_data = {**content_data, 'id': content_id}
            
            self.mapper.sync_content_to_graph(content_data)
            logger.debug(f"Synced content {content_id or content_data.get('id')} to Neo4j")
            return True
        except Exception as e:
            logger.error(f"Failed to sync content: {e}")
            return False
    
    def sync_keyword(self, keyword_data: Dict[str, Any], keyword_id: Optional[int] = None) -> bool:
        """Sync keyword to Neo4j."""
        if not self.enabled or not self.mapper:
            return True
        
        try:
            if keyword_id:
                keyword_data = {**keyword_data, 'id': keyword_id}
            
            self.mapper.sync_keyword_to_graph(keyword_data)
            logger.debug(f"Synced keyword {keyword_id or keyword_data.get('id')} to Neo4j")
            return True
        except Exception as e:
            logger.error(f"Failed to sync keyword: {e}")
            return False
    
    def sync_competitor(self, competitor_data: Dict[str, Any], competitor_id: Optional[int] = None, brand_id: Optional[int] = None) -> bool:
        """Sync competitor to Neo4j and optionally create relationship with brand."""
        if not self.enabled or not self.mapper:
            return True
        
        try:
            if competitor_id:
                competitor_data = {**competitor_data, 'id': competitor_id}
            
            self.mapper.sync_competitor_to_graph(competitor_data)
            
            # Create brand-competitor relationship if brand_id exists
            competitor_id_val = competitor_id or competitor_data.get('id')
            threat_level = competitor_data.get('threat_level', 'medium')
            if brand_id and competitor_id_val:
                self.mapper.sync_brand_competitor_relationship(str(brand_id), str(competitor_id_val), threat_level)
            
            logger.debug(f"Synced competitor {competitor_id or competitor_data.get('id')} to Neo4j")
            return True
        except Exception as e:
            logger.error(f"Failed to sync competitor: {e}")
            return False
    
    def sync_metric(self, metric_data: Dict[str, Any], metric_id: Optional[int] = None) -> bool:
        """Sync metric to Neo4j."""
        if not self.enabled or not self.mapper:
            return True
        
        try:
            if metric_id:
                metric_data = {**metric_data, 'id': metric_id}
            
            self.mapper.sync_metric_to_graph(metric_data)
            logger.debug(f"Synced metric {metric_id or metric_data.get('id')} to Neo4j")
            return True
        except Exception as e:
            logger.error(f"Failed to sync metric: {e}")
            return False
    
    def create_relationship(self, from_node_id: str, to_node_id: str, 
                          relationship_type: str, properties: Optional[Dict] = None) -> bool:
        """
        Create a relationship between two nodes in Neo4j.
        
        Args:
            from_node_id: ID of source node
            to_node_id: ID of target node
            relationship_type: Type of relationship (e.g., 'OWNS', 'TARGETS')
            properties: Optional relationship properties
        
        Returns:
            True if successful or graph disabled, False on error
        """
        if not self.enabled or not self.mapper:
            return True
        
        try:
            self.mapper.create_relationship(
                from_node_id, 
                to_node_id, 
                relationship_type, 
                properties or {}
            )
            logger.debug(f"Created relationship {from_node_id}-[{relationship_type}]->{to_node_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to create relationship: {e}")
            return False


# Singleton instance
_dual_write_manager = None


def get_dual_write_manager() -> DualWriteManager:
    """Get the singleton DualWriteManager instance."""
    global _dual_write_manager
    if _dual_write_manager is None:
        _dual_write_manager = DualWriteManager()
    return _dual_write_manager


# Convenience functions for common operations
def sync_new_user(user_data: Dict[str, Any], user_id: Optional[int] = None) -> bool:
    """Sync a newly created user to Neo4j."""
    return get_dual_write_manager().sync_user(user_data, user_id)


def sync_new_brand(brand_data: Dict[str, Any], brand_id: Optional[int] = None) -> bool:
    """Sync a newly created brand to Neo4j."""
    return get_dual_write_manager().sync_brand(brand_data, brand_id)


def sync_new_campaign(campaign_data: Dict[str, Any], campaign_id: Optional[int] = None) -> bool:
    """Sync a newly created campaign to Neo4j."""
    return get_dual_write_manager().sync_campaign(campaign_data, campaign_id)


def sync_new_content(content_data: Dict[str, Any], content_id: Optional[int] = None) -> bool:
    """Sync newly created content to Neo4j."""
    return get_dual_write_manager().sync_content(content_data, content_id)


def sync_new_keyword(keyword_data: Dict[str, Any], keyword_id: Optional[int] = None) -> bool:
    """Sync a newly extracted keyword to Neo4j."""
    return get_dual_write_manager().sync_keyword(keyword_data, keyword_id)


def sync_new_competitor(competitor_data: Dict[str, Any], competitor_id: Optional[int] = None, brand_id: Optional[int] = None) -> bool:
    """Sync a newly found competitor to Neo4j."""
    return get_dual_write_manager().sync_competitor(competitor_data, competitor_id, brand_id)


def sync_new_metric(metric_data: Dict[str, Any], metric_id: Optional[int] = None) -> bool:
    """Sync newly collected metrics to Neo4j."""
    return get_dual_write_manager().sync_metric(metric_data, metric_id)


def create_kg_relationship(from_node_id: str, to_node_id: str, 
                         relationship_type: str, properties: Optional[Dict] = None) -> bool:
    """Create a relationship between two nodes in the knowledge graph."""
    return get_dual_write_manager().create_relationship(
        from_node_id, to_node_id, relationship_type, properties
    )
