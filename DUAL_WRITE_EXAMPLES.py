"""
Example: Dual-Write Implementation

This file shows practical examples of how to implement the dual-write pattern
in your existing code. Copy and adapt these examples to your modules.
"""

# ============================================================================
# EXAMPLE 1: In database.py - Wrapping SQLite insert operations
# ============================================================================

from graph.dual_write_helper import (
    sync_new_user,
    sync_new_brand,
    sync_new_campaign,
    sync_new_content,
)
import logging

logger = logging.getLogger(__name__)


class DatabaseWrapper:
    """Database operations with dual-write to Neo4j."""
    
    def insert_user(self, user_data):
        """
        Insert user to SQLite and Neo4j.
        
        Example:
            >>> db = DatabaseWrapper()
            >>> user_id = db.insert_user({
            ...     'email': 'john@example.com',
            ...     'name': 'John Doe'
            ... })
        """
        # Insert into SQLite
        user_id = self._sqlite_insert_user(user_data)
        
        # Sync to Neo4j (non-blocking)
        sync_new_user(user_data, user_id)
        
        logger.info(f"Created user {user_id}")
        return user_id
    
    def insert_brand(self, brand_data, user_id):
        """Insert brand and create OWNS relationship."""
        # Insert into SQLite
        brand_id = self._sqlite_insert_brand(brand_data)
        
        # Sync to Neo4j
        sync_new_brand(brand_data, brand_id)
        
        # Create relationship: User OWNS Brand
        from graph.dual_write_helper import create_kg_relationship
        create_kg_relationship(user_id, brand_id, 'OWNS')
        
        logger.info(f"Created brand {brand_id} for user {user_id}")
        return brand_id
    
    def _sqlite_insert_user(self, user_data):
        """Placeholder: actual SQLite insert logic."""
        # Your existing SQLite insert code here
        return 1  # Placeholder
    
    def _sqlite_insert_brand(self, brand_data):
        """Placeholder: actual SQLite insert logic."""
        return 1  # Placeholder


# ============================================================================
# EXAMPLE 2: In content_agent.py - Content generation with relationships
# ============================================================================

from graph.dual_write_helper import sync_new_content, create_kg_relationship
from datetime import datetime


class ContentAgent:
    """AI agent for content generation with knowledge graph updates."""
    
    def generate_content(self, campaign_id, keywords, content_brief):
        """
        Generate content and update knowledge graph.
        
        Creates:
        - Content node in Neo4j
        - HAS_CONTENT relationship from Campaign to Content
        - APPEARS_IN relationships from Keywords to Content
        """
        
        # Generate content
        content = {
            'title': self._generate_title(keywords),
            'body': self._generate_body(content_brief),
            'keywords': keywords,
            'status': 'published',
            'created_at': datetime.now().isoformat()
        }
        
        # Insert into SQLite
        content_id = self._sqlite_insert_content(content)
        
        # Sync content to Neo4j
        sync_new_content(content, content_id)
        
        # Create campaign -> content relationship
        create_kg_relationship(
            campaign_id,
            content_id,
            'HAS_CONTENT',
            {'generated_at': datetime.now().isoformat()}
        )
        
        # Create keyword -> content relationships
        for keyword in keywords:
            keyword_id = keyword.get('id')
            if keyword_id:
                create_kg_relationship(
                    keyword_id,
                    content_id,
                    'APPEARS_IN',
                    {
                        'position': keyword.get('position', 0),
                        'relevance': keyword.get('relevance', 0.5)
                    }
                )
        
        logger.info(f"Generated content {content_id} for campaign {campaign_id}")
        return content_id
    
    def _generate_title(self, keywords):
        """Generate title based on keywords."""
        return "Generated Title"
    
    def _generate_body(self, brief):
        """Generate content body."""
        return "Generated content..."
    
    def _sqlite_insert_content(self, content):
        """Insert content into SQLite."""
        return 1  # Placeholder


# ============================================================================
# EXAMPLE 3: In seo_agent.py - Keyword extraction with graph linking
# ============================================================================

from graph.dual_write_helper import sync_new_keyword, create_kg_relationship


class SEOAgent:
    """SEO optimization agent with keyword tracking."""
    
    def extract_keywords(self, content_text, brand_id):
        """
        Extract keywords and link to brand targets.
        
        Creates:
        - Keyword nodes in Neo4j
        - TARGETS relationships from Brand to Keywords
        """
        
        # Extract keywords
        keywords = self._extract_keywords_from_text(content_text)
        
        for keyword_data in keywords:
            # Insert into SQLite
            keyword_id = self._sqlite_insert_keyword(keyword_data)
            
            # Sync keyword to Neo4j
            sync_new_keyword(keyword_data, keyword_id)
            
            # Brand targets this keyword
            create_kg_relationship(
                brand_id,
                keyword_id,
                'TARGETS',
                {
                    'priority': keyword_data.get('priority', 'medium'),
                    'volume': keyword_data.get('search_volume', 0)
                }
            )
        
        logger.info(f"Extracted {len(keywords)} keywords for brand {brand_id}")
        return keywords
    
    def _extract_keywords_from_text(self, text):
        """Extract keywords from text."""
        return [{'term': 'example', 'volume': 1000}]
    
    def _sqlite_insert_keyword(self, keyword_data):
        """Insert keyword into SQLite."""
        return 1  # Placeholder


# ============================================================================
# EXAMPLE 4: In metrics_collector.py - Performance metrics with relationships
# ============================================================================

from graph.dual_write_helper import sync_new_metric, create_kg_relationship


class MetricsCollector:
    """Collect and track performance metrics."""
    
    def collect_content_metrics(self, content_id):
        """
        Collect metrics for content and link to knowledge graph.
        
        Creates:
        - Metric node in Neo4j
        - HAS_METRICS relationship from Content to Metric
        """
        
        # Collect metrics
        metrics = self._fetch_metrics_from_api(content_id)
        
        # Insert into SQLite
        metric_id = self._sqlite_insert_metric(metrics)
        
        # Sync metrics to Neo4j
        sync_new_metric(metrics, metric_id)
        
        # Content has these metrics
        create_kg_relationship(
            content_id,
            metric_id,
            'HAS_METRICS',
            {
                'collected_at': datetime.now().isoformat(),
                'source': 'analytics_api'
            }
        )
        
        logger.info(f"Collected metrics {metric_id} for content {content_id}")
        return metric_id
    
    def _fetch_metrics_from_api(self, content_id):
        """Fetch metrics from analytics API."""
        return {
            'views': 1000,
            'engagement': 0.45,
            'roi': 2.5
        }
    
    def _sqlite_insert_metric(self, metrics):
        """Insert metrics into SQLite."""
        return 1  # Placeholder


# ============================================================================
# EXAMPLE 5: Batch operations with dual-write
# ============================================================================

from graph.dual_write_helper import get_dual_write_manager


class BatchProcessor:
    """Process multiple items with dual-write."""
    
    def process_multiple_keywords(self, keywords, brand_id):
        """Process keywords in one operation."""
        
        manager = get_dual_write_manager()
        results = {
            'succeeded': 0,
            'failed': 0,
            'errors': []
        }
        
        for keyword in keywords:
            try:
                # Insert to SQLite
                keyword_id = self._sqlite_insert_keyword(keyword)
                
                # Sync to Neo4j
                success = manager.sync_keyword(keyword, keyword_id)
                
                if success:
                    # Create relationship
                    manager.create_relationship(
                        brand_id,
                        keyword_id,
                        'TARGETS'
                    )
                    results['succeeded'] += 1
                else:
                    results['failed'] += 1
                    results['errors'].append(f"Failed to sync keyword {keyword}")
            
            except Exception as e:
                results['failed'] += 1
                results['errors'].append(str(e))
        
        logger.info(
            f"Processed keywords - "
            f"Success: {results['succeeded']}, "
            f"Failed: {results['failed']}"
        )
        
        return results
    
    def _sqlite_insert_keyword(self, keyword):
        """Insert keyword into SQLite."""
        return 1  # Placeholder


# ============================================================================
# USAGE IN ORCHESTRATOR.py
# ============================================================================

"""
In your orchestrator.py, initialize and use like this:

from graph import initialize_graph_db, close_graph_db
from database import DatabaseWrapper
from content_agent import ContentAgent

# On startup
@app.on_event("startup")
async def startup():
    initialize_graph_db()

# In your routes/operations
@app.post("/create-user")
async def create_user(user_data: dict):
    db = DatabaseWrapper()
    user_id = db.insert_user(user_data)
    return {"user_id": user_id}

@app.post("/generate-content")
async def generate_content(campaign_id: int, keywords: list):
    agent = ContentAgent()
    content_id = agent.generate_content(campaign_id, keywords, "")
    return {"content_id": content_id}

# On shutdown
@app.on_event("shutdown")
async def shutdown():
    close_graph_db()
"""
