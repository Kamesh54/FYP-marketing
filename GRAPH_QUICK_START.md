# Graph Module - Quick Usage Guide

## ✅ What Was Fixed

1. **Syntax Error** - Fixed missing parenthesis in `graph_database.py` line 31
2. **Import Statements** - Ensured all necessary functions are properly exported from the module
3. **Neo4j Compatibility** - Fixed compatibility issues with neo4j-driver 6.1.0

## 📝 Quick Reference

### Import the Module
```python
from graph import initialize_graph_db, close_graph_db, get_graph_client
```

### Initialize & Use
```python
# Initialize on startup
graph_client = initialize_graph_db()

# Check connection
if graph_client.connected:
    print("Connected to Neo4j")

# Use the client...
results = graph_client.query("MATCH (n:User) RETURN n LIMIT 5")

# Close on shutdown
close_graph_db()
```

### Get Existing Client
```python
from graph import get_graph_client

# Get singleton instance (after initialization)
client = get_graph_client()
```

## 🎯 Common Usage Patterns

### In FastAPI App
```python
from fastapi import FastAPI
from graph import initialize_graph_db, close_graph_db

app = FastAPI()

@app.on_event("startup")
async def startup():
    initialize_graph_db()

@app.on_event("shutdown")
async def shutdown():
    close_graph_db()
```

### With Error Handling
```python
try:
    graph_client = initialize_graph_db()
    if graph_client.connected:
        # Use graph database
        pass
except Exception as e:
    print(f"Neo4j unavailable: {e}")
    # Fall back to SQLite only
```

### With Data Sync
```python
from graph import initialize_graph_db, get_graph_mapper

# Initialize graph
initialize_graph_db()

# Get mapper for syncing data
mapper = get_graph_mapper()

# Sync user from SQLite to Neo4j
mapper.sync_user_to_graph({
    "id": 1,
    "email": "user@example.com",
    "name": "John Doe"
})
```

## ⚠️ Important Notes

1. **Always import before using** - Don't use `initialize_graph_db()` without importing it first
2. **Call initialize_graph_db() once** on startup (singleton pattern - subsequent calls return same instance)
3. **Call close_graph_db() on shutdown** to clean up resources
4. **NEO4J_ENABLED must be True** in .env for graph to actually connect (defaults to False)

## 🔍 Verify Installation

```bash
# Test from command line
python -c "from graph import initialize_graph_db; initialize_graph_db()"
```

Expected output:
```
Connecting to Neo4j at ...
Neo4j connection established successfully
Graph database initialized successfully
```

## 📚 Available Functions & Classes

```python
# Initialization
from graph import initialize_graph_db, close_graph_db, get_graph_client, is_graph_db_available

# Entity types
from graph import (
    NodeLabel, RelationshipType, 
    ContentType, Platform, CampaignType, CampaignStatus, ContentStatus, AgentType
)

# Database client
from graph import GraphDatabaseClient

# Mapper for syncing data
from graph import GraphMapper, get_graph_mapper

# Schema utilities
from graph import NodeSchema, RelationshipSchema, UserNode, BrandNode, KeywordNode
```

## 🆘 Common Errors & Solutions

### NameError: name 'initialize_graph_db' is not defined
**Solution:** Add import at top of file
```python
from graph import initialize_graph_db  # Don't forget this!
```

### Connection refused / Cannot connect to Neo4j
**Solution:** Ensure Neo4j is running and configured
```bash
# Check if Docker container is running
docker ps | grep neo4j

# Check .env file has correct credentials
cat .env | grep NEO4J
```

### NEO4J_ENABLED must be True
**Solution:** Set in .env file
```env
NEO4J_ENABLED=True
```

---

**Status:** Module is working correctly  
**Version:** Compatible with neo4j-driver 6.1.0+  
**Last Updated:** February 24, 2026
