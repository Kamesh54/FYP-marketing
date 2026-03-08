# Neo4j Knowledge Graph Setup Guide

## 📋 Table of Contents
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Configuration](#configuration)
- [Initialization](#initialization)
- [Data Migration](#data-migration)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Best Practices](#best-practices)

---

## 🚀 Quick Start

### 1. Install Neo4j (Choose One)

**Option A: Docker (Local Development - Recommended)**
```bash
docker run --name neo4j \
  -p 7474:7474 \
  -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password \
  -d neo4j:latest
```

**Option B: Neo4j Aura (Cloud - Production Ready)**
1. Go to https://neo4j.com/cloud/aura/
2. Create a free instance
3. Save your credentials (you'll need them in step 2)

**Option C: Local Installation**
- Download from: https://neo4j.com/download-center/
- Follow platform-specific installation instructions

### 2. Add Environment Variables

Create or update `.env` file with **either** local Docker credentials **or** Neo4j Aura credentials:

#### Option A: Local Docker Setup (Development)
```env
# Neo4j Configuration - Local Docker
NEO4J_ENABLED=True
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_local_password
NEO4J_DATABASE=neo4j
```

#### Option B: Neo4j Aura Setup (Production/Cloud)
```env
# Neo4j Configuration - Aura Cloud
NEO4J_ENABLED=True
NEO4J_URI=neo4j+s://your-instance-id.databases.neo4j.io
NEO4J_USER=your_aura_username
NEO4J_PASSWORD=your_aura_password
NEO4J_DATABASE=neo4j
```

**To get your Aura credentials:**
1. Go to [neo4j.com/cloud/aura](https://neo4j.com/cloud/aura/)
2. Find your instance details
3. Copy the connection URI, username, and password
4. Paste into `.env` file above

### 3. Install Dependencies

```bash
pip install neo4j
```

Or if using `requirements.txt`:
```bash
pip install -r requirements.txt
```

### 4. Initialize Graph Database

**Basic Usage:**
```python
from graph import initialize_graph_db, close_graph_db

# Initialize on application startup
graph_client = initialize_graph_db()

# Check if connected
if graph_client.connected:
    print("✅ Graph database ready!")
else:
    print("❌ Graph database unavailable - using SQLite only")

# Don't forget to close on shutdown
close_graph_db()
```

**In FastAPI Application:**
```python
from fastapi import FastAPI
from graph import initialize_graph_db, close_graph_db

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    """Initialize graph database on app startup."""
    initialize_graph_db()
    print("✅ Graph database initialized")

@app.on_event("shutdown")
async def shutdown_event():
    """Close graph database on app shutdown."""
    close_graph_db()
    print("✅ Graph database closed")
```

**With Error Handling:**
```python
from graph import initialize_graph_db, close_graph_db
import logging

logger = logging.getLogger(__name__)

try:
    graph_client = initialize_graph_db()
    if graph_client.connected:
        logger.info("Graph database connected")
    else:
        logger.warning("Graph database not available, using SQLite only")
except Exception as e:
    logger.error(f"Failed to initialize graph database: {e}")
    # Application continues with SQLite only
finally:
    # Ensure cleanup on exit
    close_graph_db()
```

### 5. Verify Connection

```bash
python -c "from graph import initialize_graph_db; initialize_graph_db()"
```

Expected output:
```
✅ Neo4j connection established successfully
```

---

## 💻 Installation

### Prerequisites
- Python 3.8+
- Neo4j 4.4+ (Community or Enterprise)
- 2GB+ disk space for database

### Docker Installation (Recommended)

**Step 1: Install Docker**
- Windows/Mac: https://www.docker.com/products/docker-desktop
- Linux: `apt-get install docker.io`

**Step 2: Pull and Run Neo4j**
```bash
# Pull the latest Neo4j image
docker pull neo4j:latest

# Run container with persistence
docker run --name neo4j-graph \
  -p 7474:7474 \
  -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your_secure_password \
  -v neo4j_data:/data \
  -d neo4j:latest
```

**Step 3: Access Neo4j Browser**
- Visit: http://localhost:7474
- Username: `neo4j`
- Password: Your set password

**Step 4: Verify Installation**
```bash
docker ps | grep neo4j
```

### Local Installation

**Windows:**
```powershell
# Download and run installer from https://neo4j.com/download-center/
# Or use Chocolatey
choco install neo4j
```

**macOS:**
```bash
brew install neo4j
```

**Linux:**
```bash
# Download from https://neo4j.com/download-center/
wget https://dist.neo4j.org/neo4j-community-5.x.x-unix.tar.gz
tar -xzf neo4j-community-5.x.x-unix.tar.gz
cd neo4j-community-5.x.x
./bin/neo4j console
```

---

## 🔧 Configuration

### Environment Variables

**Which setup should I use?**

| Setup | URI Scheme | Best For | Notes |
|-------|-----------|----------|-------|
| **Local Docker** | `bolt://` | Development & Testing | Runs locally, free, no cloud account needed |
| **Neo4j Aura** | `neo4j+s://` | Production & Cloud | Managed cloud service, encrypted, scalable |

### Local Docker Configuration

**Required:**
```env
NEO4J_ENABLED=True
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_docker_password
NEO4J_DATABASE=neo4j
```

### Neo4j Aura Configuration

**Required:**
```env
NEO4J_ENABLED=True
NEO4J_URI=neo4j+s://your-instance-id.databases.neo4j.io
NEO4J_USER=your_aura_username
NEO4J_PASSWORD=your_aura_password
NEO4J_DATABASE=neo4j
```

**Note:** The Aura URI already includes encryption (`neo4j+s://`), so the driver will automatically handle secure connections.

### How to Get Aura Credentials

1. **Log in to Neo4j Cloud**
   - Go to https://neo4j.com/cloud/aura/
   - Sign in with your account

2. **Find Your Instance**
   - Navigate to your database instance
   - Click "Details" or "Copy URI"

3. **Copy Your Credentials**
   - **Connection URI:** `neo4j+s://xxxxx.databases.neo4j.io`
   - **Username:** Your instance username (shown in database details)
   - **Password:** Your database password (shown when you created the instance)

4. **Update .env File**
   ```bash
   NEO4J_ENABLED=True
   NEO4J_URI=neo4j+s://your-instance-id.databases.neo4j.io
   NEO4J_USER=your_username
   NEO4J_PASSWORD=your_password
   NEO4J_DATABASE=neo4j
   ```

### Environment Variable Setup

**Windows Command Prompt:**
```cmd
set NEO4J_URI=bolt://localhost:7687
set NEO4J_USER=neo4j
set NEO4J_PASSWORD=password
```

**Windows PowerShell:**
```powershell
$env:NEO4J_URI = "bolt://localhost:7687"
$env:NEO4J_USER = "neo4j"
$env:NEO4J_PASSWORD = "password"
```

**Linux/macOS:**
```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=password
```

**Or use .env file:**
```bash
# Create .env file
echo "NEO4J_URI=bolt://localhost:7687" >> .env
echo "NEO4J_USER=neo4j" >> .env
echo "NEO4J_PASSWORD=password" >> .env
```

### Connection URI Formats

- **Local (Default):** `bolt://localhost:7687`
- **Remote Server:** `bolt://your-server.com:7687`
- **Encrypted:** `neo4j+s://your-server.com:7687`
- **Cluster:** `neo4j+routing://cluster-host:7687`

### SSL/TLS Configuration

For encrypted connections in production:

```env
NEO4J_URI=neo4j+s://your-server.com:7687
NEO4J_TRUST_CERTS=TRUST_SYSTEM_CA_SIGNED_CERTIFICATES
```

---

## 🎯 Initialization

### Automatic Initialization

The framework handles initialization automatically:

```python
# In orchestrator.py or main app file
from graph import initialize_graph_db, close_graph_db

# Startup
@app.on_event("startup")
async def startup_event():
    initialize_graph_db()
    logger.info("Graph database initialized")

# Shutdown
@app.on_event("shutdown")
async def shutdown_event():
    close_graph_db()
    logger.info("Graph database closed")
```

### Manual Initialization

```python
from graph import get_graph_client

client = get_graph_client()

# Check connection
if client.connected:
    print("✅ Connected to Neo4j")
    
    # Get graph summary
    summary = client.get_graph_summary()
    print(f"Nodes: {summary['total_nodes']}")
    print(f"Relationships: {summary['total_relationships']}")
else:
    print("❌ Failed to connect to Neo4j")
```

### Schema Initialization

The schema (indexes and constraints) is automatically created on first connection:

```python
# In graph_database.py, called automatically during __init__
def _initialize_schema(self):
    """Initialize constraints and indexes."""
    # Creates:
    # - Unique constraints on IDs
    # - Indexes for common queries
    # - Performance optimizations
```

---

## 📊 Data Migration

### Strategy 1: Dual-Write Pattern (Recommended)

Simultaneously write to both databases:

```python
# In your update functions
from graph import get_graph_mapper

mapper = get_graph_mapper()

# Write to SQLite
db.insert_user(user_data)

# Write to Neo4j
mapper.sync_user_to_graph(user_data)
```

### Strategy 2: Batch Migration

Migrate existing data in batches:

```python
from graph import get_graph_mapper
import database as db

# Get all users from SQLite
mapper = get_graph_mapper(batch_size=100)
users = db.get_all_users()

# Sync to Neo4j
results = mapper.sync_all_users_batch(users)
print(f"✅ Synced {results['successful']} users")
print(f"❌ Failed {results['failed']} users")

# Check errors
if mapper.get_sync_errors():
    print("\nErrors:")
    for error in mapper.get_sync_errors():
        print(f"  - {error}")
```

### Strategy 3: Incremental Migration

Migrate data as it's accessed:

```python
# Lazy loading pattern
from graph import get_graph_mapper

def get_user_with_sync(user_id):
    # Get from SQLite
    user = db.get_user(user_id)
    
    # Sync to Neo4j if not already there
    mapper = get_graph_mapper()
    mapper.sync_user_to_graph(user)
    
    return user
```

### Complete Migration Script

```python
# migrate_to_neo4j.py
import logging
from datetime import datetime
from graph import get_graph_mapper
import database as db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_all_data():
    """Migrate all SQLite data to Neo4j."""
    mapper = get_graph_mapper(batch_size=100)
    
    logger.info("Starting data migration to Neo4j...")
    start_time = datetime.now()
    
    # Migrate users
    logger.info("Migrating users...")
    users = db.get_all_users()
    results = mapper.sync_all_users_batch(users)
    logger.info(f"Users: {results['successful']}/{results['total']} synced")
    
    # Migrate brands
    logger.info("Migrating brands...")
    brands = db.get_all_brands()
    for brand in brands:
        mapper.sync_brand_to_graph(brand)
        # Create user-brand relationships
        if brand.get('user_id'):
            mapper.sync_user_brand_relationship(brand['user_id'], brand['id'])
    
    # Migrate campaigns
    logger.info("Migrating campaigns...")
    campaigns = db.get_all_campaigns()
    for campaign in campaigns:
        mapper.sync_campaign_to_graph(campaign)
    
    # Migrate content
    logger.info("Migrating content...")
    content_items = db.get_all_content()
    for content in content_items:
        mapper.sync_content_to_graph(content)
    
    # Migrate keywords
    logger.info("Migrating keywords...")
    keywords = db.get_all_keywords()
    for keyword in keywords:
        mapper.sync_keyword_to_graph(keyword)
    
    # Migrate metrics
    logger.info("Migrating metrics...")
    metrics = db.get_all_metrics()
    for metric in metrics:
        mapper.sync_metric_to_graph(metric)
    
    # Print summary
    elapsed = datetime.now() - start_time
    logger.info(f"✅ Migration complete in {elapsed.total_seconds():.2f}s")
    
    # Report any errors
    if mapper.get_sync_errors():
        logger.warning(f"⚠️  {len(mapper.get_sync_errors())} errors occurred:")
        for error in mapper.get_sync_errors():
            logger.warning(f"  - {error}")

if __name__ == "__main__":
    migrate_all_data()
```

Run migration:
```bash
python migrate_to_neo4j.py
```

---

## ✅ Testing

### Connection Test

```python
# test_neo4j_connection.py
from graph import get_graph_client

def test_connection():
    client = get_graph_client()
    assert client.connected, "Not connected to Neo4j"
    print("✅ Connection test passed")

def test_query():
    client = get_graph_client()
    results = client.query("RETURN 1 as test")
    assert len(results) > 0, "Query failed"
    print("✅ Query test passed")

def test_write():
    client = get_graph_client()
    affected = client.execute_write(
        "CREATE (n:TestNode {test: 'data'}) RETURN n"
    )
    assert affected > 0, "Write failed"
    print("✅ Write test passed")

def test_schema():
    client = get_graph_client()
    summary = client.get_graph_summary()
    print(f"✅ Schema test passed")
    print(f"   Total nodes: {summary.get('total_nodes', 0)}")
    print(f"   Total relationships: {summary.get('total_relationships', 0)}")

if __name__ == "__main__":
    test_connection()
    test_query()
    test_write()
    test_schema()
```

Run tests:
```bash
python test_neo4j_connection.py
```

### Browser Verification

1. Open http://localhost:7474
2. Username: `neo4j`
3. Password: Your configured password
4. Try queries:

```cypher
// Get node count
MATCH (n) RETURN COUNT(n) as node_count

// Get relationship count
MATCH ()-[r]-() RETURN COUNT(r) as rel_count

// View all node labels
CALL db.labels() YIELD label RETURN label

// View all relationship types
CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType
```

---

## 🔧 Troubleshooting

### Connection Issues

**Error: "Connection refused"**
```
Solution: Ensure Neo4j is running
docker ps | grep neo4j
docker logs neo4j
```

**Error: "Authentication failed"**
```
Solution: Check credentials in .env
Reset Neo4j password in Docker:
docker exec neo4j cypher-shell -u neo4j -p old_password "ALTER USER neo4j SET PASSWORD 'new_password'"
```

**Error: "Database not available"**
```
Solution: Increase Neo4j startup time and try again
docker restart neo4j
sleep 10
python -c "from graph import initialize_graph_db; initialize_graph_db()"
```

### Performance Issues

**Slow Queries:**
```python
# Enable profiling
from graph import get_graph_client

client = get_graph_client()
results = client.query("PROFILE MATCH (n) RETURN COUNT(n)")
# Check execution plan in results
```

**Memory Issues:**
```env
# Increase Neo4j memory (in docker-compose or Neo4j config)
NEO4J_HEAP_SIZE=2G
NEO4J_PAGECACHE_SIZE=1G
```

### Data Issues

**Check Data Integrity:**
```python
from graph import get_graph_client

client = get_graph_client()

# Check for orphaned nodes
orphan_nodes = client.query("""
    MATCH (n)
    WHERE NOT (n)--()
    RETURN COUNT(n) as orphaned_count
""")

print(f"Orphaned nodes: {orphan_nodes}")
```

**Clear and Reinitialize:**
```python
from graph import get_graph_client

client = get_graph_client()

# Clear database (use extreme caution!)
confirm = input("Clear database? (yes/no): ")
if confirm == "yes":
    client.clear_database(confirm=True)
    print("Database cleared")

# Reinitialize schema
client._initialize_schema()
print("Schema reinitialized")
```

---

## 🎓 Best Practices

### 1. Connection Management

```python
# ✅ Correct: Use context managers
with client.get_session() as session:
    result = session.run("MATCH (n:User) RETURN n")

# ❌ Avoid: Manual session handling
session = client.driver.session()
result = session.run("MATCH (n:User) RETURN n")
# Don't forget to close!
```

### 2. Query Performance

```python
# ✅ Use parameters (prevents injection, better performance)
client.query("MATCH (u:User {email: $email}) RETURN u", {"email": "user@example.com"})

# ❌ Avoid: String concatenation
cypher = f"MATCH (u:User {{email: '{email}'}}) RETURN u"
```

### 3. Batch Operations

```python
# ✅ Correct: Process in batches
from graph import get_graph_mapper
mapper = get_graph_mapper(batch_size=100)
results = mapper.sync_all_users_batch(users)

# ❌ Avoid: One at a time
for user in users:
    mapper.sync_user_to_graph(user)  # Inefficient!
```

### 4. Error Handling

```python
# ✅ Correct: Graceful degradation
try:
    graph_result = get_kg_recommendation(user_id)
except Exception as e:
    logger.warning(f"KG query failed: {e}, using fallback")
    graph_result = get_db_recommendation(user_id)

# ❌ Avoid: Crash on error
graph_result = get_kg_recommendation(user_id)
```

### 5. Monitoring

```python
# Monitor graph health
from graph import get_graph_client
import logging

logger = logging.getLogger(__name__)
client = get_graph_client()

summary = client.get_graph_summary()
logger.info(f"Graph Stats: {summary['total_nodes']} nodes, {summary['total_relationships']} relationships")

# Set up periodic monitoring
import schedule

def check_graph_health():
    summary = client.get_graph_summary()
    if summary['total_nodes'] == 0:
        logger.warning("⚠️  Graph appears empty!")

schedule.every(1).hours.do(check_graph_health)
```

---

## 📚 Additional Resources

- [Neo4j Documentation](https://neo4j.com/docs/)
- [Cypher Query Language](https://neo4j.com/docs/cypher-manual/current/)
- [Neo4j Python Driver](https://neo4j.com/docs/api/python-driver/current/)
- [Query Performance Tuning](https://neo4j.com/docs/operations-manual/current/performance/)

---

## 🆘 Support

For issues with Neo4j integration:

1. Check logs: `docker logs neo4j`
2. Test connection: `python test_neo4j_connection.py`
3. Review configuration: `echo $NEO4J_URI`
4. Verify data: Open Neo4j Browser at http://localhost:7474

