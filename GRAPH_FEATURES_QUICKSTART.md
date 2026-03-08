# Quick Start: Graph Integration Features

## 🚀 Getting Started

### 1. Access Graph Insights Endpoints

All endpoints require Bearer token authentication. Replace `TOKEN` with your JWT.

#### Content Recommendations
```bash
curl -X GET "http://localhost:8000/insights/content-recommendations?limit=5" \
  -H "Authorization: Bearer TOKEN"
```

#### Competitor Analysis
```bash
curl -X GET "http://localhost:8000/insights/competitor-analysis?brand_id=brand_123&limit=5" \
  -H "Authorization: Bearer TOKEN"
```

#### Campaign Summary
```bash
curl -X GET "http://localhost:8000/insights/campaign-summary" \
  -H "Authorization: Bearer TOKEN"
```

#### Best Performing Keywords
```bash
curl -X GET "http://localhost:8000/insights/best-keywords?brand_id=brand_123&days=30&limit=10" \
  -H "Authorization: Bearer TOKEN"
```

#### Similar Users Discovery
```bash
curl -X GET "http://localhost:8000/insights/similar-users?max_results=5" \
  -H "Authorization: Bearer TOKEN"
```

#### Content Performance Trends
```bash
curl -X GET "http://localhost:8000/insights/content-performance?content_id=content_123" \
  -H "Authorization: Bearer TOKEN"
```

#### Content Gap Analysis
```bash
curl -X GET "http://localhost:8000/insights/gap-analysis?brand_id=brand_123" \
  -H "Authorization: Bearer TOKEN"
```

#### Engagement Patterns
```bash
curl -X GET "http://localhost:8000/insights/engagement-patterns?days=30" \
  -H "Authorization: Bearer TOKEN"
```

#### Graph Health Status
```bash
curl -X GET "http://localhost:8000/health/graph" \
  -H "Authorization: Bearer TOKEN"
```

---

### 2. Using Graph Queries in Python

```python
from graph import get_graph_queries

# Get query interface
queries = get_graph_queries()

# Get content recommendations
recommendations = queries.get_content_recommendations(user_id="user_123", limit=5)

# Get competitor insights
insights = queries.get_competitor_insights(brand_id="brand_123")

# Get campaign summary
summary = queries.get_user_campaign_summary(user_id="user_123")

# Get best keywords
keywords = queries.get_best_performing_keywords(brand_id="brand_123", days=30)

# Get similar users
similar = queries.get_similar_users(user_id="user_123", max_results=5)

# Get performance trends
trends = queries.get_content_performance_trends(content_id="content_123")

# Get gap analysis
gaps = queries.get_content_gap_analysis(brand_id="brand_123")

# Get engagement patterns
patterns = queries.get_user_engagement_patterns(user_id="user_123", days=30)

# Get graph health
health = queries.get_graph_health_summary()
```

---

### 3. Campaign Planning with Graph Insights

```python
from campaign_planner import CampaignPlannerAgent

planner = CampaignPlannerAgent()

# Generate campaigns WITH competitor insights
proposals = planner.generate_proposals(
    theme="Digital Marketing",
    duration_days=7,
    brand_id="brand_123"  # Graph analyzes competitors
)

# Results include:
# - proposals[].recommended_keywords (from knowledge graph)
# - competitor_insights with market gaps
# - strategic positioning recommendations
print(f"Recommended Keywords: {proposals['proposals'][0]['recommended_keywords']}")
print(f"Market Gaps: {proposals['competitor_insights']['market_gaps']}")
```

---

### 4. Build Custom Analysis

```python
from graph import get_graph_queries

queries = get_graph_queries()

# Example: Find content gaps for a brand
brand_id = "brand_123"
gap_analysis = queries.get_content_gap_analysis(brand_id)

# Use insights to create targeted content
for gap in gap_analysis.get('gaps', []):
    print(f"Market Gap: {gap}")
    # Create content to fill this gap
    
# Find similar successful users
similar_users = queries.get_similar_users(brand_id, max_results=10)

# Analyze their winning keywords
for user in similar_users:
    user_id = user['user_id']
    keywords = queries.get_best_performing_keywords(user_id, days=30)
    print(f"User {user_id}'s top keywords: {keywords}")
```

---

## 📊 Response Examples

### Content Recommendations
```json
{
  "status": "success",
  "data": [
    {
      "id": "content_456",
      "title": "SEO Best Practices 2024",
      "relevance_score": 0.92,
      "target_keywords": ["seo", "ranking", "optimization"]
    },
    {
      "id": "content_789",
      "title": "Keyword Research Strategy",
      "relevance_score": 0.87,
      "target_keywords": ["keywords", "competition", "strategy"]
    }
  ]
}
```

### Campaign Proposals (with KG)
```json
{
  "campaign_id": "campaign_1705305600",
  "proposals": [
    {
      "tier": "budget",
      "budget": 350,
      "recommended_keywords": ["seo", "local-business", "digital-marketing"],
      "expected_ctr": 0.01,
      "creative": { ... }
    },
    {
      "tier": "balanced",
      "budget": 2100,
      "recommended_keywords": ["content-marketing", "brand-awareness", "engagement"],
      "expected_ctr": 0.025,
      "creative": { ... }
    }
  ],
  "competitor_insights": {
    "status": "available",
    "market_gaps": ["AI-driven marketing", "personalization"],
    "recommended_keywords": [...]
  }
}
```

### Graph Health
```json
{
  "status": "healthy",
  "total_nodes": 5432,
  "total_relationships": 12345,
  "node_breakdown": {
    "users": 234,
    "brands": 89,
    "campaigns": 156,
    "content": 2341,
    "keywords": 1202
  }
}
```

---

## 🧪 Running Tests

```bash
# Run all graph integration tests
pytest tests/test_graph_integration.py -v

# Run specific test class
pytest tests/test_graph_integration.py::TestGraphQueries -v

# Run with coverage
pytest tests/test_graph_integration.py --cov=graph --cov=campaign_planner

# Run end-to-end tests only
pytest tests/test_graph_integration.py -m integration -v
```

---

## 🔍 Monitoring Graph Health

The system automatically monitors graph health every 5 minutes. Check logs for:

```
Graph DB Health: healthy - Nodes: 5432, Relationships: 12345
```

Manual health check:
```python
from graph import get_graph_queries

queries = get_graph_queries()
health = queries.get_graph_health_summary()
print(f"Status: {health['status']}")
print(f"Nodes: {health['total_nodes']}")
print(f"Relationships: {health['total_relationships']}")
```

---

## ⚙️ Configuration

### Graph Database Connection
Edit `.env`:
```
NEO4J_URI=neo4j+s://your-aura-instance.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
```

### Health Monitoring Frequency
Edit `scheduler.py` line 341:
```python
CronTrigger(minute='*/5')  # Change to '*/10' for 10 minutes, '*/1' for 1 minute
```

### Query Result Limits
Edit `graph/graph_queries.py`:
```python
def get_content_recommendations(self, user_id, limit=5):  # Change default limit
```

---

## 🚨 Troubleshooting

### "Graph database not available"
- Check Neo4j connection in `.env`
- Verify Aura instance is running
- Look for error logs in orchestrator startup

### Routes returning 401 Unauthorized
- Verify JWT token is valid
- Check `Authorization` header format: `Bearer TOKEN`
- Ensure user is authenticated

### Empty results from queries
- Check if nodes exist in Neo4j
- Verify constraints and relationships are properly created
- Check `get_graph_health_summary()` for status

### Tests failing
- Run with `-v` flag for verbose output
- Check python version (3.10+ required)
- Ensure pytest installed: `pip install pytest`

---

## 📚 Full API Reference

See `IMPLEMENTATION_COMPLETE.md` for:
- Complete endpoint specifications
- Authentication details
- Response format specifications
- Error handling patterns

See `graph/graph_queries.py` for:
- Detailed Cypher queries
- Parameter specifications
- Return types and structures

See `campaign_planner.py` for:
- Campaign generation logic
- Competitor insights integration
- Proposal tier specifications

---

## 💡 Tips & Best Practices

1. **Always check graph health** before relying on insights
2. **Cache recommendations** if calling frequently
3. **Batch insights requests** to reduce query load
4. **Monitor logs** for performance and errors
5. **Use limits** to control response sizes
6. **Test endpoints** with different user/brand combinations
7. **Integrate gradually** - start with one endpoint
8. **Handle fallbacks** - graph may be temporarily unavailable

---

## 🎓 Examples

### Example 1: Generate Campaign with Market Insights
```python
from campaign_planner import CampaignPlannerAgent

planner = CampaignPlannerAgent()

# Get insights for the brand
proposals = planner.generate_proposals(
    theme="Sustainable Fashion",
    duration_days=14,
    brand_id="sustainable_brand_001"
)

# Select tier based on insights
selected_tier = "balanced"  # Good balance of cost/reach

# Use recommended keywords in campaign
keywords = proposals['proposals'][1]['recommended_keywords']
print(f"Campaign will use keywords: {keywords}")

# Identify market gaps
gaps = proposals['competitor_insights']['market_gaps']
print(f"Market gaps to target: {gaps}")
```

### Example 2: Find Similar Successful Users
```python
from graph import get_graph_queries

queries = get_graph_queries()

# Find similar users
similar = queries.get_similar_users("my_user_id", max_results=10)

# Get their best keywords
for user in similar:
    keywords = queries.get_best_performing_keywords(user['user_id'])
    print(f"User {user['user_id']} success keywords: {keywords}")

# Get their content performance
for user in similar:
    trends = queries.get_content_performance_trends(user['user_id'])
    print(f"User {user['user_id']} trends: {trends}")
```

### Example 3: Content Gap Analysis
```python
from graph import get_graph_queries

queries = get_graph_queries()

# Find gaps for your brand
gaps = queries.get_content_gap_analysis("my_brand_id")

# Create content for each gap
for gap in gaps['gaps']:
    print(f"Creating content for gap: {gap}")
    # ... create content piece for this gap

# Check performance trends
for content_id in ["content_1", "content_2"]:
    trends = queries.get_content_performance_trends(content_id)
    # Analyze to optimize future content
```

---

**For more information, see the main `IMPLEMENTATION_COMPLETE.md` documentation.**
