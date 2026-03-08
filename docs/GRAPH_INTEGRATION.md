# Knowledge Graph Integration Guide

## 📚 Overview

This guide explains how to integrate the Neo4j Knowledge Graph into your existing Multi-Agent Content Marketing Platform. The knowledge graph adds intelligent relationship management, semantic querying, and advanced analytics capabilities.

---

## 🔄 Integration Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Orchestrator (FastAPI)                   │
└────────┬─────────────────────────────┬──────────────────────┘
         │                             │
         ▼                             ▼
┌──────────────────┐        ┌──────────────────────┐
│   SQLite DB      │        │   Neo4j Graph DB     │
│  (Transactional) │◄──────►│  (Analytical)        │
│                  │        │                      │
│ • Users          │        │ • Node entities      │
│ • Sessions       │        │ • Relationships      │
│ • Content        │        │ • Patterns           │
│ • Campaigns      │        │ • Recommendations    │
└──────────────────┘        └──────────────────────┘
         ▲                             ▲
         │          Sync              │
         └─────────────────────────────┘
```

---

## 🚀 Step-by-Step Integration

### Step 1: Install Dependencies

Add to your `requirements.txt`:
```
neo4j>=5.0.0
```

Or install directly:
```bash
pip install neo4j
```

### Step 2: Configure Environment

Copy the environment template:
```bash
cp .env.neo4j.example .env
# Edit .env with your Neo4j credentials
```

Verify with Docker Compose:
```bash
docker-compose up -d
```

### Step 3: Initialize in Your Application

**In `orchestrator.py` or your main FastAPI app:**

```python
from contextlib import asynccontextmanager
from graph import initialize_graph_db, close_graph_db

# Startup and shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    # Startup
    logger.info("Initializing graph database...")
    initialize_graph_db()
    
    yield
    
    # Shutdown
    logger.info("Closing graph database...")
    close_graph_db()

# Apply to your FastAPI app
app = FastAPI(lifespan=lifespan)
```

### Step 4: Update Database Module

**In `database.py`, add sync functions:**

```python
from graph import get_graph_mapper

# After creating a user
def create_user(email: str, name: str, tier: str = "free"):
    """Create user in both SQLite and Neo4j."""
    # Insert into SQLite
    user_id = db.insert_user({
        "email": email,
        "name": name,
        "tier": tier
    })
    
    # Sync to Neo4j
    try:
        mapper = get_graph_mapper()
        mapper.sync_user_to_graph({
            "id": user_id,
            "email": email,
            "name": name,
            "tier": tier
        })
    except Exception as e:
        logger.warning(f"Failed to sync user to graph: {e}")
    
    return user_id
```

### Step 5: Enhance Intelligent Router

**In `intelligent_router.py`, add KG-based routing:**

```python
from graph import get_graph_client, is_graph_db_available

def classify_intent_with_context(
    user_message: str,
    user_id: str,
    conversation_history: List[Dict]
) -> Dict[str, Any]:
    """Classify intent with knowledge graph context."""
    
    # Get base intent classification
    intent = classify_intent_base(user_message)
    
    # Enhance with graph context if available
    if is_graph_db_available():
        client = get_graph_client()
        
        # Get user's past campaigns and preferences
        user_relationships = client.get_node_relationships(
            "User", user_id, "user_id", "OWNS"
        )
        
        # Get similar users for pattern matching
        similar_users = client.find_similar_nodes(
            "User", user_id, "user_id", max_results=5
        )
        
        # Enhance intent with historical context
        if user_relationships:
            intent["context"] = {
                "has_brands": len(user_relationships) > 0,
                "brand_count": len(user_relationships),
                "similar_users": len(similar_users)
            }
    
    return intent
```

### Step 6: Add Recommendation Engine

**Create `graph/graph_queries.py`:**

```python
from .graph_database import get_graph_client
from typing import List, Dict, Any

class GraphQueries:
    """High-level graph queries for recommendations and insights."""
    
    @staticmethod
    def get_content_recommendations(user_id: str, limit: int = 5) -> List[Dict]:
        """
        Get content recommendations based on:
        - User's brand preferences
        - Competitor analysis
        - Similar user patterns
        """
        client = get_graph_client()
        
        cypher = """
        MATCH (u:User {user_id: $user_id})-[:OWNS]->(brand:Brand)-[:TARGETS]->(keyword:Keyword)
        MATCH (competitor:Competitor)-[:USES]->(keyword)
        MATCH (content:Content)-[:APPEARS_IN]->(keyword)
        WHERE content.status = 'published'
        RETURN content, keyword, COUNT(*) as relevance_score
        ORDER BY relevance_score DESC
        LIMIT $limit
        """
        
        results = client.query(cypher, {"user_id": user_id, "limit": limit})
        return results
    
    @staticmethod
    def get_competitor_insights(brand_id: str) -> Dict[str, Any]:
        """Get market insights from competitor relationships."""
        client = get_graph_client()
        
        cypher = """
        MATCH (brand:Brand {brand_id: $brand_id})-[:COMPETES_WITH]->(competitor:Competitor)
        MATCH (competitor)-[:USES]->(keyword:Keyword)
        WITH competitor, keyword, COUNT(*) as keyword_count
        RETURN {
            competitor_name: competitor.competitor_name,
            total_keywords: keyword_count,
            threat_level: competitor.threat_level,
            keywords: collect(keyword.term)
        } as insights
        LIMIT 10
        """
        
        results = client.query(cypher, {"brand_id": brand_id})
        return {"competitors": results}
    
    @staticmethod
    def get_workflow_optimization(workflow_id: str) -> Dict[str, Any]:
        """Analyze workflow effectiveness from historical data."""
        client = get_graph_client()
        
        cypher = """
        MATCH (workflow:Workflow {workflow_id: $workflow_id})-[:EXECUTED_IN]->(agent:Agent)
        WITH workflow, agent, COUNT(*) as execution_count
        RETURN {
            workflow_name: workflow.workflow_name,
            agents: collect({
                agent_type: agent.agent_type,
                success_rate: agent.success_rate,
                avg_cost: agent.average_cost,
                executions: execution_count
            }),
            optimization_score: workflow.optimization_score
        } as analysis
        """
        
        result = client.query_single(cypher, {"workflow_id": workflow_id})
        return result or {}
```

### Step 7: Integrate with Campaign Planner

**Update `campaign_planner.py`:**

```python
from graph.graph_queries import GraphQueries

class CampaignPlannerAgent:
    def plan_campaign(self, brand_id: str, objective: str):
        """Plan campaign using KG insights."""
        
        # Get competitor insights
        insights = GraphQueries.get_competitor_insights(brand_id)
        
        # Get content recommendations
        recommendations = GraphQueries.get_content_recommendations(
            user_id=self.user_id, limit=5
        )
        
        # Build plan enhanced with graph data
        plan = {
            "objective": objective,
            "competitor_analysis": insights,
            "recommended_content": recommendations,
            "estimated_success": self._estimate_success(insights)
        }
        
        return plan
    
    def _estimate_success(self, insights: Dict) -> float:
        """Estimate campaign success based on competitor data."""
        # Use competitor insights to estimate probability
        if not insights.get("competitors"):
            return 0.5
        
        # Simple heuristic: lower threat = higher success probability
        threat_scores = [
            {"high": 0.3, "medium": 0.6, "low": 0.8}.get(
                c["threat_level"], 0.5
            )
            for c in insights["competitors"]
        ]
        
        return sum(threat_scores) / len(threat_scores) if threat_scores else 0.5
```

### Step 8: Update Memory Module

**Enhance `memory.py`:**

```python
from graph import get_graph_client

def write_campaign_entity_with_graph(entity: Dict[str, Any]) -> str:
    """Write campaign entity and create graph relationships."""
    
    # Write to Chroma as before
    entity_id = write_campaign_entity(entity)
    
    # Also create in graph
    try:
        client = get_graph_client()
        
        # Create campaign node
        campaign_props = {
            "campaign_id": entity_id,
            "campaign_name": entity.get("campaign_name", ""),
            "type": entity.get("content_type", ""),
            "created_at": datetime.now().isoformat()
        }
        
        client.create_node("Campaign", campaign_props)
        
        # Create relationships to keywords
        for keyword in entity.get("keywords", []):
            client.create_relationship(
                "Campaign", entity_id, "campaign_id",
                "TARGETS",
                "Keyword", keyword["id"], "keyword_id",
                {"relevance": keyword.get("relevance", 0.5)}
            )
    
    except Exception as e:
        logger.warning(f"Failed to sync to graph: {e}")
    
    return entity_id
```

### Step 9: Add Metrics Sync

**Update `metrics_collector.py`:**

```python
from graph import get_graph_mapper

class MetricsCollector:
    def collect_metrics_for_post(self, post_data: Dict) -> Dict:
        """Collect metrics and sync to graph."""
        
        # Collect metrics as before
        metrics = self._collect_base_metrics(post_data)
        
        # Sync to Neo4j
        try:
            mapper = get_graph_mapper()
            mapper.sync_metric_to_graph({
                "id": metrics["metric_id"],
                "platform": metrics["platform"],
                "impressions": metrics["impressions"],
                "engagement_rate": metrics["engagement_rate"],
                "roi": metrics["roi"]
            })
            
            # Link to content
            if metrics.get("content_id"):
                mapper.sync_content_metric_relationship(
                    metrics["content_id"],
                    metrics["metric_id"]
                )
        
        except Exception as e:
            logger.warning(f"Failed to sync metrics to graph: {e}")
        
        return metrics
```

### Step 10: Add Chat Endpoint Enhancement

**In `orchestrator.py`, enhance chat endpoint:**

```python
from graph import get_graph_client, is_graph_db_available

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest, authorization: str = Header(None)):
    """Enhanced chat with graph context."""
    
    # Existing chat logic...
    user_id = verify_token(authorization)
    
    # Enhance with graph context
    if is_graph_db_available():
        client = get_graph_client()
        
        # Get user's brand history
        user_brands = client.get_node_relationships(
            "User", user_id, "user_id", "OWNS"
        )
        
        # Add to context
        if user_brands:
            req.context = {
                "user_brands": [b.get("brand_id") for b in user_brands],
                "has_prior_campaigns": len(user_brands) > 0
            }
    
    # Continue with normal chat flow...
    response = await process_chat(req, user_id)
    
    return response
```

---

## 📊 Query Examples

### Find Similar Brands

```python
from graph import get_graph_client

client = get_graph_client()

# Find brands similar to the user's brand
results = client.find_similar_nodes(
    "Brand", 
    user_brand_id, 
    "brand_id",
    similarity_threshold=0.7,
    max_results=10
)
```

### Get Competitor Keywords

```python
cypher = """
MATCH (brand:Brand {brand_id: $brand_id})-[:COMPETES_WITH]->(competitor:Competitor)
MATCH (competitor)-[:USES]->(keyword:Keyword)
RETURN competitor.competitor_name, collect(keyword.term) as keywords
"""

results = client.query(cypher, {"brand_id": brand_id})
```

### Track Content Performance Over Time

```python
cypher = """
MATCH (content:Content)-[:HAS_METRICS]->(metric:Metric)
WHERE content.content_id = $content_id
RETURN metric.timestamp, metric.impressions, metric.engagement_rate
ORDER BY metric.timestamp
"""

performance = client.query(cypher, {"content_id": content_id})
```

### Find Best-Performing Workflows

```python
cypher = """
MATCH (workflow:Workflow)-[:EXECUTED_IN]->(agent:Agent)
WHERE workflow.success_rate > 0.8
RETURN workflow, COUNT(agent) as agent_count, AVG(agent.success_rate) as avg_success
ORDER BY workflow.optimization_score DESC
LIMIT 5
"""

best_workflows = client.query(cypher)
```

---

## 🔐 Security Considerations

### 1. Credential Management

```python
# ✅ Correct: Use environment variables
from dotenv import load_dotenv
load_dotenv()

neo4j_password = os.getenv("NEO4J_PASSWORD")

# ❌ Avoid: Hardcoded credentials
neo4j_password = "password123"  # Never do this!
```

### 2. Query Parameterization

```python
# ✅ Correct: Prevent injection
client.query("MATCH (u:User {email: $email}) RETURN u", {"email": user_email})

# ❌ Avoid: String concatenation
cypher = f"MATCH (u:User {{email: '{user_email}'}}) RETURN u"
```

### 3. Error Handling

```python
# ✅ Correct: Handle errors gracefully
try:
    results = client.query(cypher)
except Exception as e:
    logger.error(f"Query failed: {e}")
    # Fallback to SQLite
    results = db.fallback_query()

# ❌ Avoid: Exposing sensitive info
except Exception as e:
    raise ResponseOnlyException(str(e))  # Leaks internals
```

---

## 🧪 Testing the Integration

### Unit Test Example

```python
# test_graph_integration.py
import pytest
from graph import get_graph_client, get_graph_mapper

@pytest.fixture
def graph_client():
    """Provide graph client for tests."""
    return get_graph_client()

def test_create_user_node(graph_client):
    """Test creating user node."""
    if not graph_client.connected:
        pytest.skip("Graph database not available")
    
    user = {
        "user_id": "test_user_123",
        "email": "test@example.com",
        "name": "Test User",
        "tier": "free"
    }
    
    success = graph_client.create_node("User", user)
    assert success, "Failed to create user node"

def test_create_relationship(graph_client):
    """Test creating relationships."""
    if not graph_client.connected:
        pytest.skip("Graph database not available")
    
    success = graph_client.create_relationship(
        "User", "test_user_123", "user_id",
        "OWNS",
        "Brand", "brand_456", "brand_id"
    )
    assert success, "Failed to create relationship"

def test_query(graph_client):
    """Test querying graph."""
    if not graph_client.connected:
        pytest.skip("Graph database not available")
    
    results = graph_client.query("MATCH (n:User) RETURN COUNT(n) as count")
    assert len(results) > 0, "Query returned no results"
```

Run tests:
```bash
pytest test_graph_integration.py -v
```

---

## 📈 Monitoring & Maintenance

### Monitor Graph Health

```python
import logging
import schedule

logger = logging.getLogger(__name__)

def check_graph_health():
    """Check graph database health."""
    client = get_graph_client()
    
    if not client.connected:
        logger.error("Graph database disconnected!")
        return False
    
    summary = client.get_graph_summary()
    logger.info(f"Graph Stats: {summary}")
    
    # Check for anomalies
    if summary['total_nodes'] > 1000000:
        logger.warning("Graph has >1M nodes, consider optimization")
    
    return True

# Schedule periodic checks
schedule.every(1).hours.do(check_graph_health)
```

### Backup Neo4j Data

```bash
# Docker backup
docker exec neo4j neo4j-admin dump --to-path=/data/backup.dump

# Restore from backup
docker exec neo4j neo4j-admin load --from-path=/data/backup.dump --overwrite-existing
```

---

## 🎯 Next Steps

1. **Run Docker Compose**: `docker-compose up -d`
2. **Verify Connection**: `python test_neo4j_connection.py`
3. **Migrate Data**: `python migrate_to_neo4j.py`
4. **Test Queries**: Try examples in Neo4j Browser
5. **Update Your Code**: Follow integration steps above
6. **Monitor**: Set up health checks and logging

---

## 📞 Support

For issues:
1. Check [NEO4J_SETUP.md](NEO4J_SETUP.md) for troubleshooting
2. Review logs: `docker logs neo4j`
3. Test connection: `python -c "from graph import initialize_graph_db; initialize_graph_db()"`

