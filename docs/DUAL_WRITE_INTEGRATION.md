# Dual-Write Pattern - Integration Guide

## Overview

The dual-write pattern automatically syncs new data to both SQLite and Neo4j. Every time you create a user, campaign, content, etc., it's automatically written to both databases.

## Quick Integration

### Step 1: Import the helper
```python
from graph.dual_write_helper import (
    sync_new_user,
    sync_new_brand,
    sync_new_campaign,
    sync_new_content,
    sync_new_keyword,
    sync_new_competitor,
    sync_new_metric,
    create_kg_relationship
)
```

### Step 2: Add one line after each create operation
```python
# Example: Creating a user
user_id = db.insert_user(user_data)
sync_new_user(user_data, user_id)  # ← Add this line!
```

## Integration Examples by Module

### database.py (SQLite Layer)

**Before:**
```python
def insert_user(user_data):
    """Insert user into SQLite."""
    result = db.execute(insert_query, user_data)
    return result.lastrowid
```

**After:**
```python
from graph.dual_write_helper import sync_new_user

def insert_user(user_data):
    """Insert user into SQLite and sync to Neo4j."""
    result = db.execute(insert_query, user_data)
    user_id = result.lastrowid
    
    # Sync to Neo4j
    sync_new_user(user_data, user_id)
    
    return user_id
```

### content_agent.py (Content Generation)

**Before:**
```python
def generate_content(campaign_id, keywords):
    """Generate content for campaign."""
    content = create_content_piece(keywords)
    content_id = db.insert_content(content)
    return content_id
```

**After:**
```python
from graph.dual_write_helper import sync_new_content, create_kg_relationship

def generate_content(campaign_id, keywords):
    """Generate content and sync to knowledge graph."""
    content = create_content_piece(keywords)
    content_id = db.insert_content(content)
    
    # Sync to Neo4j
    sync_new_content(content, content_id)
    
    # Create relationships
    create_kg_relationship(
        campaign_id, 
        content_id, 
        'HAS_CONTENT',
        {'generated_at': datetime.now().isoformat()}
    )
    
    # Link keywords to content
    for keyword in keywords:
        create_kg_relationship(
            keyword['id'],
            content_id,
            'APPEARS_IN',
            {'position': keyword.get('position', 0)}
        )
    
    return content_id
```

### seo_agent.py (Keyword Extraction)

**Before:**
```python
def extract_keywords(content):
    """Extract and store keywords."""
    keywords = keyword_extractor.extract(content)
    for kw in keywords:
        kw_id = db.insert_keyword(kw)
    return keywords
```

**After:**
```python
from graph.dual_write_helper import sync_new_keyword

def extract_keywords(content):
    """Extract keywords and sync to knowledge graph."""
    keywords = keyword_extractor.extract(content)
    for kw in keywords:
        kw_id = db.insert_keyword(kw)
        # Sync each keyword
        sync_new_keyword(kw, kw_id)
    return keywords
```

### CompetitorGapAnalyzerAgent.py (Competitor Analysis)

**Before:**
```python
def analyze_competitors(brand_id):
    """Find and analyze competitors."""
    competitors = find_competitors(brand_id)
    for comp in competitors:
        comp_id = db.insert_competitor(comp)
    return competitors
```

**After:**
```python
from graph.dual_write_helper import sync_new_competitor, create_kg_relationship

def analyze_competitors(brand_id):
    """Find competitors and create knowledge graph connections."""
    competitors = find_competitors(brand_id)
    for comp in competitors:
        comp_id = db.insert_competitor(comp)
        # Sync competitor
        sync_new_competitor(comp, comp_id)
        # Create relationship
        create_kg_relationship(
            brand_id,
            comp_id,
            'COMPETES_WITH',
            {'analysis_date': datetime.now().isoformat()}
        )
    return competitors
```

### metrics_collector.py (Metrics Collection)

**Before:**
```python
def collect_metrics(content_id):
    """Collect performance metrics for content."""
    metrics = fetch_metrics(content_id)
    metric_id = db.insert_metrics(metrics)
    return metric_id
```

**After:**
```python
from graph.dual_write_helper import sync_new_metric, create_kg_relationship

def collect_metrics(content_id):
    """Collect metrics and update knowledge graph."""
    metrics = fetch_metrics(content_id)
    metric_id = db.insert_metrics(metrics)
    
    # Sync metrics
    sync_new_metric(metrics, metric_id)
    
    # Link metrics to content
    create_kg_relationship(
        content_id,
        metric_id,
        'HAS_METRICS',
        {'collected_at': datetime.now().isoformat()}
    )
    
    return metric_id
```

## Implementation Checklist

- [ ] Import `dual_write_helper` functions where needed
- [ ] Add `sync_new_*()` calls in `database.py` insert functions
- [ ] Add relationship creation after related entities are created
- [ ] Test with new data creation
- [ ] Monitor logs for sync errors
- [ ] Verify data appears in Neo4j Browser

## Testing the Dual-Write

### Verify with Neo4j Browser

1. **Open Neo4j Browser** at http://localhost:7474 (or your Aura instance)
2. **Create a test user:**
   ```python
   from database import insert_user
   user_id = insert_user({
       'email': 'test@example.com',
       'name': 'Test User'
   })
   ```

3. **Check if it appears in Neo4j:**
   ```cypher
   MATCH (u:User {email: 'test@example.com'}) RETURN u
   ```

4. **Expected result:** Should see the user node

### Monitor Logs

```bash
# Watch for sync messages in logs
tail -f app.log | grep "Synced"
```

Expected output:
```
DEBUG - Synced user 123 to Neo4j
DEBUG - Created relationship 123-[OWNS]->456
```

## Error Handling

The dual-write is **non-blocking** - if Neo4j sync fails, the SQLite write still succeeds:

```python
# This will always return the user_id, even if Neo4j sync fails
user_id = insert_user(user_data)
# Even if Neo4j is down, user still gets added to SQLite
```

This ensures your application continues working even if Neo4j becomes unavailable.

## Best Practices

1. **Always call sync after insert:**
   ```python
   # ✅ Good
   id = db.insert_user(data)
   sync_new_user(data, id)
   
   # ❌ Bad - Neo4j never gets updated
   id = db.insert_user(data)
   ```

2. **Include all relevant data:**
   ```python
   # ✅ Good - passes complete data
   sync_new_content({
       'id': id,
       'title': title,
       'body': body,
       'status': 'published',
       'created_at': datetime.now()
   }, content_id)
   
   # ❌ Bad - missing important fields
   sync_new_content({'title': title}, content_id)
   ```

3. **Create relationships right after creation:**
   ```python
   # ✅ Good - relationships created immediately
   campaign_id = insert_campaign(cam_data)
   sync_new_campaign(cam_data, campaign_id)
   
   content_id = insert_content(content_data)
   sync_new_content(content_data, content_id)
   
   create_kg_relationship(campaign_id, content_id, 'HAS_CONTENT')
   
   # ❌ Bad - relationships created later, data incomplete
   ```

4. **Use meaningful relationship types:**
   ```python
   # Common relationships to use:
   # User relationships:
   create_kg_relationship(user_id, brand_id, 'OWNS')
   
   # Brand relationships:
   create_kg_relationship(brand_id, keyword_id, 'TARGETS')
   create_kg_relationship(brand_id, competitor_id, 'COMPETES_WITH')
   
   # Campaign relationships:
   create_kg_relationship(campaign_id, content_id, 'HAS_CONTENT')
   create_kg_relationship(campaign_id, metric_id, 'HAS_METRICS')
   
   # Content relationships:
   create_kg_relationship(content_id, keyword_id, 'APPEARS_IN')
   create_kg_relationship(content_id, metric_id, 'HAS_METRICS')
   ```

## Monitoring & Maintenance

### Check sync health:
```python
from graph import get_graph_mapper

mapper = get_graph_mapper()
errors = mapper.get_sync_errors()
print(f"Sync errors: {len(errors)}")
for error in errors[:5]:  # Show first 5
    print(f"  - {error}")
```

### Clear old sync errors:
```python
mapper.clear_sync_errors()
```

### Query graph stats:
```python
from graph import get_graph_client

client = get_graph_client()
summary = client.get_graph_summary()
print(f"Total nodes: {summary['total_nodes']}")
print(f"Total relationships: {summary['total_relationships']}")
```

## Common Issues

### Q: What if Neo4j is down?
**A:** The dual-write will fail gracefully and log a warning. Your SQLite database continues to work. Data won't sync until Neo4j comes back up.

### Q: Can I batch sync later?
**A:** Yes! You can run the migration script anytime to sync old data that was created when Neo4j was unavailable.

### Q: Does dual-write slow things down?
**A:** Minimally - the sync happens asynchronously and doesn't block your SQLite writes. Graph operations are non-blocking.

### Q: Can I disable it temporarily?
**A:** Yes - set `NEO4J_ENABLED=False` in `.env` to disable all graph operations without changing code.

---

**Status:** Ready to implement  
**Effort:** Low - just add 1-2 lines per create operation  
**Benefit:** Automatic knowledge graph building as you use the system
