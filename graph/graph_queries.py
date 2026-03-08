"""
High-level graph queries for recommendations, insights, and analytics.
This module provides domain-specific query patterns for the knowledge graph.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from .graph_database import get_graph_client

logger = logging.getLogger(__name__)


class GraphQueries:
    """High-level graph queries for recommendations and insights."""
    
    def __init__(self):
        """Initialize with graph client."""
        self.client = get_graph_client()
    
    def get_content_recommendations(
        self, 
        user_id: str, 
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get content recommendations based on:
        - User's brand preferences
        - Competitor analysis
        - Similar user patterns
        """
        if not self.client.connected:
            logger.warning("Graph database not available for recommendations")
            return []
        
        cypher = """
        MATCH (u:User {user_id: $user_id})-[:OWNS]->(brand:Brand)-[:TARGETS]->(keyword:Keyword)
        MATCH (competitor:Competitor)-[:USES]->(keyword)
        MATCH (content:Content)-[:TARGETS]->(keyword)
        WHERE content.status = 'published' OR content.status IS NULL
        RETURN {
            content_id: content.content_id,
            content_type: content.content_type,
            title: content.title,
            relevance_score: COUNT(*),
            keywords: collect(DISTINCT keyword.term)
        } as recommendation
        ORDER BY recommendation.relevance_score DESC
        LIMIT $limit
        """
        
        try:
            results = self.client.query(cypher, {"user_id": user_id, "limit": limit})
            return [r.get("recommendation", {}) for r in results if r]
        except Exception as e:
            logger.error(f"Failed to get content recommendations: {e}")
            return []
    
    def get_competitor_insights(
        self, 
        brand_id: str, 
        limit: int = 10
    ) -> Dict[str, Any]:
        """Get market insights from competitor relationships."""
        if not self.client.connected:
            logger.warning("Graph database not available for competitor insights")
            return {"competitors": []}
        
        cypher = """
        MATCH (brand:Brand {brand_id: $brand_id})-[:COMPETES_WITH]->(competitor:Competitor)
        MATCH (competitor)-[:USES]->(keyword:Keyword)
        RETURN {
            competitor_name: competitor.competitor_name,
            competitor_domain: competitor.domain,
            threat_level: competitor.threat_level,
            total_keywords: COUNT(DISTINCT keyword.keyword_id),
            keywords: collect(DISTINCT keyword.term),
            last_updated: competitor.last_updated
        } as insight
        ORDER BY insight.total_keywords DESC
        LIMIT $limit
        """
        
        try:
            results = self.client.query(cypher, {"brand_id": brand_id, "limit": limit})
            return {
                "competitors": [r.get("insight", {}) for r in results if r],
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Failed to get competitor insights: {e}")
            return {"competitors": []}
    
    def get_user_campaign_summary(
        self, 
        user_id: str
    ) -> Dict[str, Any]:
        """Get user's campaign summary and metrics."""
        if not self.client.connected:
            logger.warning("Graph database not available for campaign summary")
            return {}
        
        cypher = """
        MATCH (u:User {user_id: $user_id})-[:OWNS]->(brand:Brand)-[:OWNS]->(campaign:Campaign)
        OPTIONAL MATCH (campaign)-[:CREATES]->(content:Content)
        OPTIONAL MATCH (content)-[:HAS_METRICS]->(metric:Metric)
        RETURN {
            user_id: u.user_id,
            brand_count: COUNT(DISTINCT brand.brand_id),
            campaign_count: COUNT(DISTINCT campaign.campaign_id),
            content_count: COUNT(DISTINCT content.content_id),
            avg_engagement_rate: AVG(metric.engagement_rate),
            total_impressions: SUM(metric.impressions),
            total_clicks: SUM(metric.clicks),
            brands: collect(DISTINCT {
                brand_id: brand.brand_id,
                brand_name: brand.brand_name
            })
        } as summary
        """
        
        try:
            result = self.client.query_single(cypher, {"user_id": user_id})
            return result.get("summary", {}) if result else {}
        except Exception as e:
            logger.error(f"Failed to get campaign summary: {e}")
            return {}
    
    def get_best_performing_keywords(
        self,
        brand_id: str,
        days: int = 30,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get best-performing keywords for a brand in the last N days."""
        if not self.client.connected:
            logger.warning("Graph database not available for keyword analysis")
            return []
        
        cypher = """
        MATCH (brand:Brand {brand_id: $brand_id})-[:TARGETS]->(keyword:Keyword)
        MATCH (keyword)<-[:APPEARS_IN]-(content:Content)-[:HAS_METRICS]->(metric:Metric)
        WHERE metric.timestamp > datetime(datetime().epochSeconds - ($days * 86400))
        RETURN {
            keyword_term: keyword.term,
            search_volume: keyword.search_volume,
            competition: keyword.competition,
            avg_ctr: AVG(metric.click_through_rate),
            total_impressions: SUM(metric.impressions),
            total_clicks: SUM(metric.clicks),
            avg_engagement_rate: AVG(metric.engagement_rate),
            content_count: COUNT(DISTINCT content.content_id)
        } as keyword_stats
        ORDER BY keyword_stats.total_clicks DESC
        LIMIT $limit
        """
        
        try:
            results = self.client.query(
                cypher, 
                {"brand_id": brand_id, "days": days, "limit": limit}
            )
            return [r.get("keyword_stats", {}) for r in results if r]
        except Exception as e:
            logger.error(f"Failed to get best-performing keywords: {e}")
            return []
    
    def get_similar_users(
        self,
        user_id: str,
        max_results: int = 5
    ) -> List[Dict[str, Any]]:
        """Find similar users based on brand and content patterns."""
        if not self.client.connected:
            logger.warning("Graph database not available for similar users")
            return []
        
        cypher = """
        MATCH (u1:User {user_id: $user_id})-[:OWNS]->(brand1:Brand)
        MATCH (u2:User)-[:OWNS]->(brand2:Brand)
        WHERE u1 <> u2 AND brand1.industry = brand2.industry
        
        OPTIONAL MATCH (brand1)-[:TARGETS]->(kw1:Keyword)
        OPTIONAL MATCH (brand2)-[:TARGETS]->(kw2:Keyword)
        
        WITH u1, u2, COUNT(DISTINCT kw1.keyword_id) as kw1_count,
             COUNT(DISTINCT kw2.keyword_id) as kw2_count,
             COUNT(DISTINCT CASE WHEN kw1 = kw2 THEN kw1.keyword_id END) as common_keywords
        
        RETURN {
            similar_user_id: u2.user_id,
            similarity_score: CASE WHEN (kw1_count + kw2_count) = 0 
                THEN 0 
                ELSE (2.0 * common_keywords) / (kw1_count + kw2_count) 
            END,
            common_keywords: common_keywords
        } as similarity
        ORDER BY similarity.similarity_score DESC
        LIMIT $max_results
        """
        
        try:
            results = self.client.query(
                cypher, 
                {"user_id": user_id, "max_results": max_results}
            )
            return [r.get("similarity", {}) for r in results if r]
        except Exception as e:
            logger.error(f"Failed to find similar users: {e}")
            return []
    
    def get_content_performance_trends(
        self,
        content_id: str,
        granularity: str = "day"  # day, week, month
    ) -> List[Dict[str, Any]]:
        """Get content performance trends over time."""
        if not self.client.connected:
            logger.warning("Graph database not available for trends")
            return []
        
        # Clamp granularity
        if granularity not in ["day", "week", "month"]:
            granularity = "day"
        
        cypher = """
        MATCH (content:Content {content_id: $content_id})-[:HAS_METRICS]->(metric:Metric)
        RETURN {
            timestamp: metric.timestamp,
            impressions: metric.impressions,
            clicks: metric.clicks,
            engagement_rate: metric.engagement_rate,
            platform: metric.platform
        } as trend
        ORDER BY trend.timestamp DESC
        LIMIT 100
        """
        
        try:
            results = self.client.query(cypher, {"content_id": content_id})
            trends = [r.get("trend", {}) for r in results if r]
            return sorted(trends, key=lambda x: x.get("timestamp", ""), reverse=False)
        except Exception as e:
            logger.error(f"Failed to get content performance trends: {e}")
            return []
    
    def get_graph_health_summary(self) -> Dict[str, Any]:
        """Get overall graph database health and statistics."""
        if not self.client.connected:
            return {
                "status": "disconnected",
                "connected": False
            }
        
        try:
            cypher = """
            MATCH (n) 
            WITH labels(n)[0] as node_type, COUNT(*) as count
            RETURN node_type, count
            """
            node_stats = self.client.query(cypher)
            
            cypher_rels = """
            MATCH ()-[r]->()
            WITH type(r) as rel_type, COUNT(*) as count
            RETURN rel_type, count
            """
            rel_stats = self.client.query(cypher_rels)
            
            return {
                "status": "healthy",
                "connected": True,
                "node_statistics": {
                    stat.get("node_type"): stat.get("count", 0) 
                    for stat in node_stats if stat
                },
                "relationship_statistics": {
                    stat.get("rel_type"): stat.get("count", 0) 
                    for stat in rel_stats if stat
                },
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Failed to get graph health: {e}")
            return {
                "status": "error",
                "connected": False,
                "error": str(e)
            }
    
    def get_content_gap_analysis(
        self,
        brand_id: str
    ) -> Dict[str, Any]:
        """Analyze content gaps by comparing user's content with competitors."""
        if not self.client.connected:
            logger.warning("Graph database not available for gap analysis")
            return {}
        
        cypher = """
        MATCH (brand:Brand {brand_id: $brand_id})-[:COMPETES_WITH]->(competitor:Competitor)
        MATCH (competitor)-[:USES]->(comp_kw:Keyword)
        OPTIONAL MATCH (brand)-[:TARGETS]->(our_kw:Keyword)
        RETURN {
            total_competitor_keywords: COUNT(DISTINCT comp_kw.keyword_id),
            keywords_we_target: COUNT(DISTINCT our_kw.keyword_id),
            missed_keywords: COUNT(DISTINCT CASE 
                WHEN NOT (our_kw.keyword_id = comp_kw.keyword_id) 
                THEN comp_kw.keyword_id END),
            gap_percentage: 100.0 * COUNT(DISTINCT CASE 
                WHEN NOT (our_kw.keyword_id = comp_kw.keyword_id) 
                THEN comp_kw.keyword_id END) / COUNT(DISTINCT comp_kw.keyword_id),
            missing_keywords: collect(DISTINCT CASE 
                WHEN NOT (our_kw.keyword_id = comp_kw.keyword_id) 
                THEN comp_kw.term END)
        } as gap_analysis
        """
        
        try:
            result = self.client.query_single(cypher, {"brand_id": brand_id})
            return result.get("gap_analysis", {}) if result else {}
        except Exception as e:
            logger.error(f"Failed to get content gap analysis: {e}")
            return {}
    
    def get_user_engagement_patterns(
        self,
        user_id: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """Analyze user engagement patterns over recent period."""
        if not self.client.connected:
            logger.warning("Graph database not available for engagement analysis")
            return {}
        
        cypher = """
        MATCH (u:User {user_id: $user_id})-[:OWNS]->(brand:Brand)-[:OWNS]->(campaign:Campaign)
            -[:CREATES]->(content:Content)-[:HAS_METRICS]->(metric:Metric)
        WHERE metric.timestamp > datetime(datetime().epochSeconds - ($days * 86400))
        RETURN {
            total_campaigns: COUNT(DISTINCT campaign.campaign_id),
            total_content: COUNT(DISTINCT content.content_id),
            avg_engagement_rate: AVG(metric.engagement_rate),
            avg_impressions: AVG(metric.impressions),
            total_clicks: SUM(metric.clicks),
            best_performing_platform: apoc.coll.flatten(
                collect(CASE WHEN metric.engagement_rate IS NOT NULL 
                THEN metric.platform END)
            )[0],
            preferred_content_type: apoc.coll.flatten(
                collect(CASE WHEN metric.engagement_rate IS NOT NULL 
                THEN content.content_type END)
            )[0]
        } as patterns
        """
        
        try:
            result = self.client.query_single(
                cypher, 
                {"user_id": user_id, "days": days}
            )
            return result.get("patterns", {}) if result else {}
        except Exception as e:
            logger.error(f"Failed to get engagement patterns: {e}")
            return {}


# Global instance
_graph_queries_instance = None


def get_graph_queries() -> GraphQueries:
    """Get or create global GraphQueries instance."""
    global _graph_queries_instance
    if _graph_queries_instance is None:
        _graph_queries_instance = GraphQueries()
    return _graph_queries_instance
