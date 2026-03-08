# Neo4j Knowledge Graph Implementation

## 📋 Summary

This directory contains a complete Neo4j knowledge graph implementation for your Multi-Agent Content Marketing Platform. The system enables intelligent relationship management, semantic querying, and advanced analytics through a hybrid approach combining SQLite (transactional) and Neo4j (analytical).

---

## 📁 File Structure

```
graph/
├── __init__.py                 # Module exports and initialization
├── graph_database.py           # Neo4j client with connection pooling
├── graph_entities.py           # Entity schemas and constants
└── graph_mapper.py             # SQL-to-Graph synchronization
```

---

## 🚀 Quick Start

### 1. Setup Neo4j

**Option A: Docker (Recommended)**
```bash
docker-compose up -d
```

**Option B: Local Installation**
- Download from https://neo4j.com/download-center/
- Start Neo4j service

### 2. Configure Environment

Create `.env` file with:
```env
NEO4J_ENABLED=True
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_secure_password_here
```

> **Security Note:** For Aura cloud instances, use `neo4j+s://` URI scheme with your instance ID and credentials.

Or use the provided template:
```bash
cp .env.neo4j.example .env
```

### 3. Install Dependencies

```bash
pip install neo4j
```

### 4. Initialize in Your App

```python
from graph import initialize_graph_db, close_graph_db

# On startup
initialize_graph_db()

# On shutdown
close_graph_db()
```

### 5. Test Connection

```bash
python -c "from graph import initialize_graph_db; initialize_graph_db()"
```

Expected output: ✅ Neo4j connection established successfully

---

## 📚 Module Documentation

### graph_database.py

**Main class:** `GraphDatabaseClient`

**Key methods:**
- `query(cypher, parameters)` - Execute read queries
- `execute_write(cypher, parameters)` - Execute write operations
- `create_node(label, properties)` - Create nodes
- `create_relationship(...)` - Create relationships
- `get_node_relationships(...)` - Find related nodes
- `find_similar_nodes(...)` - Semantic similarity queries
- `get_graph_summary()` - Overall statistics

**Singleton access:**
```python
from graph import get_graph_client

client = get_graph_client()
```

### graph_entities.py

**Enumerations:**
- `NodeLabel` - Valid node types
- `RelationshipType` - Valid relationship types
- `ContentType`, `Platform`, `CampaignType`, etc.

**Schemas:**
- `NodeSchema` - Property definitions for each node
- `RelationshipSchema` - Properties for relationships

**Data classes:**
- `UserNode`, `BrandNode`, `KeywordNode` - Type-safe node creation

**Example:**
```python
from graph import NodeLabel, UserNode

# Type-safe node creation
user = UserNode(
    user_id="123",
    email="user@example.com",
    name="John Doe"
)

# Get schema
schema = NodeSchema.get_user_schema()
```

### graph_mapper.py

**Main class:** `GraphMapper`

**Key methods:**
- `sync_user_to_graph()` - Sync user from SQL
- `sync_brand_to_graph()` - Sync brand
- `sync_campaign_to_graph()` - Sync campaign
- `sync_content_to_graph()` - Sync content
- `sync_keyword_to_graph()` - Sync keywords
- `sync_competitor_to_graph()` - Sync competitors
- `sync_all_users_batch()` - Batch operations

**Example:**
```python
from graph import get_graph_mapper

mapper = get_graph_mapper()
success = mapper.sync_user_to_graph({
    "id": 1,
    "email": "user@example.com",
    "name": "John"
})
```

---

## 🔗 Knowledge Graph Schema

### Node Labels

| Label | Purpose | Unique Key |
|-------|---------|-----------|
| **User** | Platform users | user_id |
| **Brand** | User brands | brand_id |
| **Campaign** | Marketing campaigns | campaign_id |
| **Content** | Generated content | content_id |
| **Keyword** | SEO keywords | keyword_id |
| **Competitor** | Market competitors | competitor_id |
| **Metric** | Performance metrics | metric_id |
| **Agent** | AI agents | agent_id |
| **Workflow** | Agent workflows | workflow_id |

### Relationship Types

| Type | From → To | Purpose |
|------|-----------|---------|
| OWNS | User → Brand | User owns brand |
| TARGETS | Brand → Keyword | Brand targets keyword |
| COMPETES_WITH | Brand → Competitor | Brands compete |
| PART_OF | Content → Campaign | Content in campaign |
| APPEARS_IN | Keyword → Content | Keyword in content |
| HAS_METRICS | Content/Campaign → Metric | Performance data |
| EXECUTED_IN | Agent → Workflow | Agent usage |
| SIMILAR_TO | Node → Node | Semantic similarity |

---

## 💡 Use Cases

### 1. Intelligent Content Recommendations

```python
from graph import get_graph_client

client = get_graph_client()

# Find content similar to user's past selections
results = client.query("""
    MATCH (user:User {user_id: $user_id})-[:OWNS]->(brand:Brand)
    -[:TARGETS]->(keyword:Keyword)<-[:APPEARS_IN]-(content:Content)
    WHERE content.status = 'published'
    RETURN content ORDER BY content.engagement_rate DESC LIMIT 5
""", {"user_id": user_id})
```

### 2. Competitor Analysis

```python
# Track competitor keyword strategy
results = client.query("""
    MATCH (brand:Brand {brand_id: $brand_id})-[:COMPETES_WITH]->(competitor)
    -[:USES]->(keyword:Keyword)
    RETURN competitor.name, collect(keyword.term) as keywords
""", {"brand_id": brand_id})
```

### 3. Campaign Performance Prediction

```python
# Find similar campaigns and their outcomes
results = client.query("""
    MATCH (campaign:Campaign {campaign_id: $id})-[:HAS_CONTENT]->(content)
    -[:HAS_METRICS]->(metric:Metric)
    WITH campaign, AVG(metric.roi) as avg_roi
    MATCH (similar:Campaign)-[:SIMILAR_TO]->(campaign)
    -[:HAS_METRICS]->(m2:Metric)
    RETURN avg_roi, COUNT(m2) as data_points
""", {"id": campaign_id})
```

### 4. Workflow Optimization

```python
# Track agent performance across workflows
results = client.query("""
    MATCH (workflow:Workflow)-[:EXECUTED_IN]->(agent:Agent)
    WHERE workflow.optimization_score > 0.8
    RETURN workflow, AVG(agent.success_rate) as efficiency
    ORDER BY efficiency DESC
    LIMIT 10
""")
```

---

## 🔄 Synchronization Strategies

### Dual-Write Pattern

```python
# Write to both SQLite and Neo4j
from graph import get_graph_mapper

# Insert into SQLite
user_id = db.insert_user(user_data)

# Sync to Neo4j
mapper = get_graph_mapper()
mapper.sync_user_to_graph(user_data)
```

### Batch Migration

```python
# Migrate existing data
users = db.get_all_users()
mapper = get_graph_mapper(batch_size=100)
results = mapper.sync_all_users_batch(users)

print(f"Synced {results['successful']} users")
```

### Periodic Sync

```python
import schedule

def sync_daily():
    """Sync updated records daily."""
    updated_users = db.get_users_modified_since(datetime.now() - timedelta(days=1))
    mapper = get_graph_mapper()
    mapper.sync_all_users_batch(updated_users)

schedule.every().day.at("02:00").do(sync_daily)
```

---

## 🧪 Testing

### Connection Test

```python
from graph import get_graph_client

client = get_graph_client()
assert client.connected, "Not connected to Neo4j"
print("✅ Connection test passed")
```

### Query Test

```python
from graph import get_graph_client

client = get_graph_client()
results = client.query("MATCH (n:User) RETURN COUNT(n) as count")
print(f"Found {results[0]['count']} users")
```

### Full Test Suite

```bash
python -m pytest test_graph_integration.py -v
```

---

## 📊 Monitoring

### Check Graph Health

```python
from graph import get_graph_client

client = get_graph_client()
summary = client.get_graph_summary()

print(f"Nodes: {summary['total_nodes']}")
print(f"Relationships: {summary['total_relationships']}")
```

### Get Entity Statistics

```python
from graph import get_graph_client

client = get_graph_client()

# Stats for specific node type
user_stats = client.get_node_stats("User")
print(f"Total users: {user_stats['total_count']}")

# Stats for relationships
rel_stats = client.get_relationship_stats("OWNS")
print(f"OWNS relationships: {rel_stats['total_relationships']}")
```

### Query Performance

```python
# Enable query logging in Neo4j Browser
# http://localhost:7474 → System → Query Log

# Or programmatically
results = client.query("PROFILE MATCH (n) RETURN COUNT(n)")
```

---

## 🔒 Security Best Practices

### 1. Credentials

```python
# ✅ Use environment variables
from dotenv import load_dotenv
load_dotenv()

password = os.getenv("NEO4J_PASSWORD")

# ❌ Don't hardcode
password = "admin123"
```

### 2. Connection Encryption

For production, use encrypted connections:

```env
NEO4J_URI=neo4j+s://your-server.com:7687
NEO4J_TRUST_CERTS=TRUST_SYSTEM_CA_SIGNED_CERTIFICATES
```

### 3. Query Parameterization

```python
# ✅ Prevent injection with parameters
client.query("MATCH (u:User {email: $email}) RETURN u", {"email": user_email})

# ❌ String concatenation is vulnerable
cypher = f"MATCH (u:User {{email: '{email}'}}) RETURN u"
```

---

## 🐛 Troubleshooting

### Connection Issues

```bash
# Check if Neo4j is running
docker ps | grep neo4j

# Check Neo4j logs
docker logs neo4j

# Verify credentials
docker exec neo4j cypher-shell -u neo4j -p password "RETURN 1"
```

### Memory Issues

```env
# Increase Neo4j heap size
NEO4J_HEAP_SIZE=4G
```

### Query Timeout

```python
# Tests can timeout if Neo4j is slow to start
import time
time.sleep(5)  # Wait for Neo4j to fully start
```

---

## 📖 Additional Resources

**Documentation:**
- [NEO4J_SETUP.md](NEO4J_SETUP.md) - Complete setup guide
- [GRAPH_INTEGRATION.md](GRAPH_INTEGRATION.md) - Integration with your framework

**External:**
- [Neo4j Documentation](https://neo4j.com/docs/)
- [Cypher Query Language](https://neo4j.com/docs/cypher-manual/current/)
- [Python Driver Guide](https://neo4j.com/docs/api/python-driver/current/)

---

## 📞 Common Questions

### Q: Can I use graph without SQLite?
**A:** Yes, but we recommend both for transactional (SQLite) and analytical (Graph) use cases.

### Q: How do I backup the graph?
**A:** Use Docker volumes (see docker-compose.yml) or Neo4j backup tools.

### Q: What's the maximum graph size?
**A:** Neo4j handles billions of nodes/relationships. Community edition has no technical limits.

### Q: How do I debug queries?
**A:** Use Neo4j Browser (http://localhost:7474) or enable query profiling.

---

## ✅ Integration Checklist

- [ ] Installed neo4j package
- [ ] Set up Neo4j database (Docker or local)
- [ ] Configured .env file with Neo4j credentials
- [ ] Tested connection (`python -c "from graph import initialize_graph_db..."`)
- [ ] Added initialization to your FastAPI app
- [ ] Updated database.py with sync functions
- [ ] Created graph_queries.py with custom queries
- [ ] Added monitoring/health checks
- [ ] Ran test suite
- [ ] Documented your custom queries

---

## 🎯 Next Steps

1. **Quick Setup**: Follow Quick Start section above
2. **Integration**: Read [GRAPH_INTEGRATION.md](GRAPH_INTEGRATION.md)
3. **Advanced Setup**: Check [NEO4J_SETUP.md](NEO4J_SETUP.md)
4. **Custom Queries**: Add queries in graph/graph_queries.py
5. **Production**: Set up backups, monitoring, and optimization

---

**Created:** February 2026  
**Status:** Production Ready  
**Version:** 1.0.0
