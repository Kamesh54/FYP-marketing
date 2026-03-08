"""
Graph-enhanced insights and analytics endpoints.
This module provides additional endpoints for graph-based recommendations and insights.
"""

import logging
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, Header, HTTPException
from datetime import datetime

logger = logging.getLogger(__name__)


def create_graph_routes(app: FastAPI, auth_module, db_module):
    """
    Create graph-enhanced routes and attach them to FastAPI app.
    
    Args:
        app: FastAPI application instance
        auth_module: Authentication module with get_current_user
        db_module: Database module with graph queries
    """
    
    try:
        from graph import get_graph_queries, is_graph_db_available
        GRAPH_AVAILABLE = True
    except Exception as e:
        logger.warning(f"Graph queries not available: {e}")
        GRAPH_AVAILABLE = False
    
    if not GRAPH_AVAILABLE:
        logger.info("Skipping graph routes - graph module not available")
        return
    
    # ==================== GRAPH INSIGHTS ENDPOINTS ====================
    
    @app.get("/insights/content-recommendations")
    async def get_content_recommendations(
        authorization: str = Header(None),
        limit: int = 5
    ):
        """Get personalized content recommendations based on knowledge graph."""
        try:
            payload = auth_module.get_current_user(authorization)
            user_id = payload['user_id']
            
            if not is_graph_db_available():
                return {"recommendations": [], "note": "Graph database not available"}
            
            queries = get_graph_queries()
            recommendations = queries.get_content_recommendations(str(user_id), limit)
            
            return {
                "recommendations": recommendations,
                "count": len(recommendations),
                "timestamp": datetime.now().isoformat()
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Content recommendations error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/insights/competitor-analysis")
    async def get_competitor_analysis(
        authorization: str = Header(None),
        brand_id: Optional[str] = None
    ):
        """Get competitor insights and market gaps."""
        try:
            payload = auth_module.get_current_user(authorization)
            user_id = payload['user_id']
            
            if not is_graph_db_available():
                return {"competitors": [], "note": "Graph database not available"}
            
            # Get brand_id from user if not provided
            if not brand_id:
                brand_profile = db_module.get_brand_profile(user_id)
                if not brand_profile:
                    raise HTTPException(status_code=400, detail="No brand profile found")
                brand_id = brand_profile.get('brand_id')
            
            queries = get_graph_queries()
            insights = queries.get_competitor_insights(brand_id)
            
            return {
                "insights": insights,
                "timestamp": datetime.now().isoformat()
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Competitor analysis error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/insights/campaign-summary")
    async def get_campaign_summary(
        authorization: str = Header(None)
    ):
        """Get user's campaign performance summary from knowledge graph."""
        try:
            payload = auth_module.get_current_user(authorization)
            user_id = payload['user_id']
            
            if not is_graph_db_available():
                return {"summary": {}, "note": "Graph database not available"}
            
            queries = get_graph_queries()
            summary = queries.get_user_campaign_summary(str(user_id))
            
            return {
                "summary": summary,
                "timestamp": datetime.now().isoformat()
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Campaign summary error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/insights/best-keywords")
    async def get_best_keywords(
        authorization: str = Header(None),
        brand_id: Optional[str] = None,
        days: int = 30,
        limit: int = 10
    ):
        """Get best-performing keywords for a brand."""
        try:
            payload = auth_module.get_current_user(authorization)
            user_id = payload['user_id']
            
            if not is_graph_db_available():
                return {"keywords": [], "note": "Graph database not available"}
            
            # Get brand_id from user if not provided
            if not brand_id:
                brand_profile = db_module.get_brand_profile(user_id)
                if not brand_profile:
                    raise HTTPException(status_code=400, detail="No brand profile found")
                brand_id = brand_profile.get('brand_id')
            
            queries = get_graph_queries()
            keywords = queries.get_best_performing_keywords(brand_id, days, limit)
            
            return {
                "keywords": keywords,
                "period_days": days,
                "count": len(keywords),
                "timestamp": datetime.now().isoformat()
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Best keywords error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/insights/similar-users")
    async def get_similar_users(
        authorization: str = Header(None),
        max_results: int = 5
    ):
        """Find similar users based on brand and content patterns."""
        try:
            payload = auth_module.get_current_user(authorization)
            user_id = payload['user_id']
            
            if not is_graph_db_available():
                return {"similar_users": [], "note": "Graph database not available"}
            
            queries = get_graph_queries()
            similar = queries.get_similar_users(str(user_id), max_results)
            
            return {
                "similar_users": similar,
                "count": len(similar),
                "timestamp": datetime.now().isoformat()
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Similar users error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/insights/content-performance")
    async def get_content_performance(
        authorization: str = Header(None),
        content_id: Optional[str] = None
    ):
        """Get content performance trends over time."""
        try:
            payload = auth_module.get_current_user(authorization)
            user_id = payload['user_id']
            
            if not is_graph_db_available():
                return {"trends": [], "note": "Graph database not available"}
            
            if not content_id:
                raise HTTPException(status_code=400, detail="content_id required")
            
            queries = get_graph_queries()
            trends = queries.get_content_performance_trends(content_id)
            
            return {
                "content_id": content_id,
                "trends": trends,
                "data_points": len(trends),
                "timestamp": datetime.now().isoformat()
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Content performance error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/insights/gap-analysis")
    async def get_gap_analysis(
        authorization: str = Header(None),
        brand_id: Optional[str] = None
    ):
        """Get content gap analysis by comparing with competitors."""
        try:
            payload = auth_module.get_current_user(authorization)
            user_id = payload['user_id']
            
            if not is_graph_db_available():
                return {"analysis": {}, "note": "Graph database not available"}
            
            # Get brand_id from user if not provided
            if not brand_id:
                brand_profile = db_module.get_brand_profile(user_id)
                if not brand_profile:
                    raise HTTPException(status_code=400, detail="No brand profile found")
                brand_id = brand_profile.get('brand_id')
            
            queries = get_graph_queries()
            analysis = queries.get_content_gap_analysis(brand_id)
            
            return {
                "analysis": analysis,
                "timestamp": datetime.now().isoformat()
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Gap analysis error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/insights/engagement-patterns")
    async def get_engagement_patterns(
        authorization: str = Header(None),
        days: int = 30
    ):
        """Get user's engagement patterns over recent period."""
        try:
            payload = auth_module.get_current_user(authorization)
            user_id = payload['user_id']
            
            if not is_graph_db_available():
                return {"patterns": {}, "note": "Graph database not available"}
            
            queries = get_graph_queries()
            patterns = queries.get_user_engagement_patterns(str(user_id), days)
            
            return {
                "patterns": patterns,
                "period_days": days,
                "timestamp": datetime.now().isoformat()
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Engagement patterns error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/health/graph")
    async def graph_health():
        """Get graph database health status."""
        try:
            if not is_graph_db_available():
                return {
                    "status": "unavailable",
                    "connected": False,
                    "message": "Graph module not configured"
                }
            
            queries = get_graph_queries()
            health = queries.get_graph_health_summary()
            
            return health
        except Exception as e:
            logger.error(f"Graph health check error: {e}")
            return {
                "status": "error",
                "connected": False,
                "error": str(e)
            }
    
    logger.info("Graph routes registered successfully")
