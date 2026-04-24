# Prompt Evolution Log: Brand Context Tracking

## What Was Added

You now have **complete prompt execution tracking** with brand context. The `/prompt-log` endpoint shows:

### 1. **Prompt Templates** (from `prompt_versions` table)
- System prompt used
- Agent name and context type
- Performance score
- Timestamp created

### 2. **Prompt Executions** (NEW - from `prompt_executions` table)
For each time a prompt is used:
- **Execution ID**: Unique identifier
- **Brand Info** (JSON): 
  - brand_name
  - brand_positioning
  - target_audience
  - key_products
  - tone_guidelines
- **Performance Metrics**:
  - performance_score
  - quality_score
  - brand_alignment_score
  - overall_score
- **Feedback**: Result/notes from execution
- **Timestamp**: When it was executed
- **Execution Time**: How long it took

---

## Database Schema

### New Table: `prompt_executions`

```sql
CREATE TABLE prompt_executions (
    execution_id TEXT PRIMARY KEY,
    prompt_id TEXT,                    -- Foreign key to prompt_versions
    agent_name TEXT NOT NULL,          -- e.g., "content_agent"
    context_type TEXT NOT NULL,        -- e.g., "blog", "social_post"
    brand_info TEXT DEFAULT '{}',      -- JSON with brand context
    performance_score REAL,            -- Overall score
    quality_score REAL,                -- Content quality
    brand_alignment_score REAL,        -- How well aligned with brand
    overall_score REAL,                -- Overall assessment
    feedback TEXT,                     -- Notes/feedback
    execution_time REAL,               -- Seconds to execute
    created_at TIMESTAMP               -- When executed
);
```

---

## How It Works

### 1. **Agent Execution** (`agent_adapters.py`)
When an agent generates content (e.g., `generate_blog()`):
```python
def generate_blog(
    business_details: str,
    brand_info: Optional[Dict] = None,  # NEW: Brand context
    ...
) -> Dict:
    # Generate content
    content = agent.generate_blog(...)
    
    # NEW: Log the execution with brand context
    log_prompt_execution(
        execution_id=f"exec_{uuid.uuid4().hex[:12]}",
        agent_name="content_agent",
        context_type="blog",
        brand_info=brand_info,  # Store brand details
        performance_score=content.get('quality_score'),
        feedback=f"Generated: {content.get('title')}"
    )
    
    return content
```

### 2. **API Returns Complete Picture** (`orchestrator.py`)
`GET /prompt-log` now returns:
```json
{
  "templates": [
    {
      "id": "pv_sample_001",
      "agent_name": "content_agent",
      "context_type": "blog",
      "prompt_text": "You are an expert blog specialist...",
      "performance_score": 0.92,
      "use_count": 25,
      "created_at": "2026-04-05T21:51:04"
    }
  ],
  "total_templates": 6,
  
  "executions": [
    {
      "execution_id": "exec_ecyclehub_blog_001",
      "agent_name": "content_agent",
      "context_type": "blog",
      "brand_info": {
        "brand_name": "eCycleHub",
        "brand_positioning": "Affordable e-bikes for urban commuters",
        "target_audience": "Eco-conscious professionals, 25-45",
        "key_products": ["Commuter Pro $1,200", "Urban Lite $900"],
        "tone_guidelines": "Friendly, conversational"
      },
      "performance_score": 0.89,
      "quality_score": 0.91,
      "brand_alignment_score": 0.87,
      "overall_score": 0.89,
      "feedback": "Blog: How e-bikes transform urban commuting",
      "execution_time": 12.5,
      "created_at": "2026-04-05T22:30:15"
    }
  ],
  "total_executions": 2,
  "agents": [
    {"agent_name": "content_agent", "context_type": "blog"},
    {"agent_name": "content_agent", "context_type": "social_post"}
  ]
}
```

---

## What You See in Prompt-Log

### Before (Generic)
```
Template: "You are a blog specialist..."
Performance: 0.92
Updated: Apr 5
```

### After (With Brand Context) ✨
```
Template: "You are a blog specialist..."
Performance: 0.92
Updated: Apr 5

Recent Executions:
├─ eCycleHub Blog Post
│  ├─ Brand: eCycleHub (Affordable e-bikes)
│  ├─ Audience: Eco-conscious professionals
│  ├─ Products: Commuter Pro, Urban Lite
│  ├─ Performance: 0.89
│  └─ Time: Apr 5, 10:30 PM
│
└─ TechFlow LinkedIn Post
   ├─ Brand: TechFlow (Enterprise automation)
   ├─ Audience: CTOs, DevOps teams
   ├─ Products: AutoFlow Pro, CloudSync
   ├─ Performance: 0.85
   └─ Time: Apr 5, 10:15 PM
```

---

## Key Benefits

1. **See What Prompts Actually Do**
   - Generic templates → Real execution context

2. **Track Performance Per Brand**
   - How did this prompt perform for eCycleHub? (0.89)
   - How did it perform for TechFlow? (0.85)

3. **Understand Audience Alignment**
   - brand_alignment_score shows how well prompt fit the brand

4. **Complete Audit Trail**
   - Which template + which brand + which audience + what score

---

## Updated Files

| File | Change |
|------|--------|
| `database.py` | Added `prompt_executions` table + `log_prompt_execution()` + `get_prompt_executions()` |
| `agent_adapters.py` | Updated `generate_blog()` and `generate_social()` to accept and log `brand_info` |
| `orchestrator.py` | Updated `/prompt-log` endpoint to return templates + executions with brand context |

---

## Next Steps

1. **Frontend** needs to update `/prompt-log` UI to display:
   - Templates section (existing)
   - Executions section (new) with brand details

2. **LangGraph nodes** in `langgraph_nodes.py` should pass `brand_info` from state to agent adapters

3. **Continuous logging**: Every agent call now logs execution with brand context

---

## API Examples

### Get all executions
```bash
curl http://localhost:8004/prompt-log?limit=100
```

### Filter by agent and context
```bash
curl http://localhost:8004/prompt-log?agent_name=content_agent&context_type=blog&limit=50
```

### Response includes both templates and executions
- Templates show generic prompt info
- Executions show real usage with brand context
- Compare how same prompt performs across different brands/audiences
