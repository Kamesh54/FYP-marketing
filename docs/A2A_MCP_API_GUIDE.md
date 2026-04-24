# A2A & MCP Protocol - Comprehensive API Guide

## Table of Contents
1. [Overview](#overview)
2. [Authentication](#authentication)
3. [A2A Protocol (Agent-to-Agent)](#a2a-protocol)
4. [MCP (Model Context Protocol)](#mcp-protocol)
5. [Implementation Examples](#implementation-examples)
6. [Error Handling](#error-handling)
7. [Best Practices](#best-practices)

---

## Overview

The FYP Marketing Platform uses two primary communication protocols:

| Protocol | Purpose | Use Case |
|----------|---------|----------|
| **A2A** | Agent-to-Agent task delegation | Inter-agent communication, orchestration |
| **MCP** | LLM tool invocation | Groq LLM accessing platform tools |

Both protocols use JSON-RPC 2.0 for request/response semantics.

---

## Authentication

### JWT Bearer Token

All endpoints (except `.well-known/agent.json` and `/health`) require JWT authentication.

```bash
curl -H "Authorization: Bearer <JWT_TOKEN>" \
  http://localhost:8004/a2a
```

### Token Format
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Token Generation
See `auth.py` for token generation:
```python
import jwt
import os
from datetime import datetime, timedelta

jwt_secret = os.getenv("JWT_SECRET")
payload = {
    "sub": "agent-id",
    "exp": datetime.utcnow() + timedelta(hours=24),
    "iat": datetime.utcnow()
}
token = jwt.encode(payload, jwt_secret, algorithm="HS256")
```

---

## A2A Protocol (Agent-to-Agent)

### 1. Agent Discovery (No Auth Required)

**Endpoint:** `GET /.well-known/agent.json`

Discover what this agent can do.

```bash
curl http://localhost:8004/.well-known/agent.json
```

**Response (200 OK):**
```json
{
  "name": "FYP Orchestrator",
  "description": "Multi-agent marketing automation platform",
  "a2aVersion": "0.1",
  "a2aEndpointUrl": "http://localhost:8004/a2a",
  "authentication": {
    "schemes": ["bearer"],
    "description": "JWT Bearer token required"
  },
  "capabilities": [
    {
      "method": "tasks.send",
      "description": "Submit task and wait for completion"
    },
    {
      "method": "tasks.sendSubscribe",
      "description": "Submit task with real-time SSE updates"
    },
    {
      "method": "tasks.cancel",
      "description": "Cancel a running task"
    },
    {
      "method": "campaigns.propose",
      "description": "Propose marketing campaign"
    },
    {
      "method": "campaigns.accept",
      "description": "Accept proposed campaign"
    }
  ]
}
```

### 2. Submit Task (Request-Response)

**Endpoint:** `POST /a2a` with `method: "tasks.send"`

Submit a task and wait for completion (polling).

**Request Example:**
```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "method": "tasks.send",
  "params": {
    "task": {
      "messages": [
        {
          "role": "user",
          "parts": [
            {
              "type": "text",
              "text": "Generate a blog post about AI in marketing"
            }
          ]
        }
      ],
      "metadata": {
        "intent": "blog_generation",
        "brand_name": "TechCorp",
        "duration_days": 7,
        "audience": "Tech professionals"
      }
    }
  }
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:8004/a2a \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "req-001",
    "method": "tasks.send",
    "params": {
      "task": {
        "messages": [{
          "role": "user",
          "parts": [{"type": "text", "text": "Generate blog post about AI marketing"}]
        }],
        "metadata": {
          "intent": "blog_generation",
          "brand_name": "TechCorp"
        }
      }
    }
  }'
```

**Response (200 OK):**
```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "result": {
    "taskId": "task-blog-ai-20260407-a8c3f9e1",
    "status": {
      "state": "submitted",
      "message": "Task queued for processing"
    }
  }
}
```

### 3. Poll Task Status

**Endpoint:** `GET /a2a/tasks/{task_id}`

Poll the status of a submitted task.

**cURL Example:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8004/a2a/tasks/task-blog-ai-20260407-a8c3f9e1
```

**Response - Running (200 OK):**
```json
{
  "id": "task-blog-ai-20260407-a8c3f9e1",
  "status": {
    "state": "working",
    "message": "Generating blog content (step 3/5)...",
    "progress_percent": 60
  },
  "metadata": {
    "estimated_remaining_seconds": 45
  }
}
```

**Response - Completed (200 OK):**
```json
{
  "id": "task-blog-ai-20260407-a8c3f9e1",
  "status": {
    "state": "completed",
    "message": "Task completed successfully",
    "progress_percent": 100
  },
  "messages": [
    {
      "role": "user",
      "parts": [
        {
          "type": "text",
          "text": "Generate a blog post about AI in marketing"
        }
      ]
    },
    {
      "role": "agent",
      "parts": [
        {
          "type": "text",
          "text": "Blog post generated successfully..."
        },
        {
          "type": "file",
          "file": {
            "name": "blog_post.html",
            "mimeType": "text/html",
            "bytes": "base64_encoded_content..."
          }
        }
      ]
    }
  ],
  "artifacts": [
    {
      "name": "blog_post.html",
      "parts": [
        {
          "type": "file",
          "file": {
            "name": "blog_post.html",
            "mimeType": "text/html",
            "bytes": "base64_encoded_content..."
          }
        }
      ]
    }
  ]
}
```

### 4. Subscribe to Task (Real-Time SSE)

**Endpoint:** `POST /a2a/tasks/{task_id}/subscribe`

Open a real-time Server-Sent Events (SSE) connection to receive live task updates.

**cURL Example:**
```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  http://localhost:8004/a2a/tasks/task-blog-ai-20260407-a8c3f9e1/subscribe
```

**Response - SSE Stream (200 OK):**
```
event: status
data: {"type":"status","taskId":"task-blog-ai-20260407-a8c3f9e1","status":{"state":"working","message":"Loading brand context..."}}

event: status
data: {"type":"status","taskId":"task-blog-ai-20260407-a8c3f9e1","status":{"state":"working","message":"Extracting keywords..."}}

event: artifact
data: {"type":"artifact","taskId":"task-blog-ai-20260407-a8c3f9e1","artifact":{"name":"keywords.json","parts":[{"type":"text","text":"[\"AI\",\"Marketing\",\"Automation\"]"}]}}

event: status
data: {"type":"status","taskId":"task-blog-ai-20260407-a8c3f9e1","status":{"state":"working","message":"Generating blog content..."}}

event: artifact
data: {"type":"artifact","taskId":"task-blog-ai-20260407-a8c3f9e1","artifact":{"name":"blog_post.html","parts":[{"type":"file","file":{"name":"blog_post.html"}}]}}

event: status
data: {"type":"status","taskId":"task-blog-ai-20260407-a8c3f9e1","status":{"state":"completed","message":"Task completed successfully"}}
```

**Python Example (SSE Client):**
```python
import requests
import json

headers = {"Authorization": f"Bearer {token}"}
task_id = "task-blog-ai-20260407-a8c3f9e1"

with requests.post(
    f"http://localhost:8004/a2a/tasks/{task_id}/subscribe",
    headers=headers,
    stream=True
) as response:
    for line in response.iter_lines():
        if line:
            if line.startswith(b'event:'):
                event = line.decode().split(': ', 1)[1]
            elif line.startswith(b'data:'):
                data = json.loads(line.decode().split(': ', 1)[1])
                print(f"Event: {event}")
                print(f"Data: {data}")
```

### 5. Campaign Proposal

**Endpoint:** `POST /a2a` with `method: "campaigns.propose"`

Propose a marketing campaign strategy.

**Request Example:**
```json
{
  "jsonrpc": "2.0",
  "id": "req-002",
  "method": "campaigns.propose",
  "params": {
    "campaign": {
      "theme": "Sustainable Products Q2 2026",
      "tier": "balanced",
      "duration_days": 28,
      "budget": 5000,
      "target_audience": "Eco-conscious consumers",
      "platforms": ["twitter", "instagram", "tiktok"]
    }
  }
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:8004/a2a \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "req-002",
    "method": "campaigns.propose",
    "params": {
      "campaign": {
        "theme": "Sustainable Products Q2 2026",
        "tier": "balanced",
        "duration_days": 28,
        "budget": 5000
      }
    }
  }'
```

**Response (200 OK):**
```json
{
  "jsonrpc": "2.0",
  "id": "req-002",
  "result": {
    "taskId": "task-campaign-20260407-b7d3f8e2",
    "status": {
      "state": "submitted",
      "message": "Campaign proposal queued"
    },
    "campaign": {
      "id": "campaign-001",
      "tier": "balanced",
      "estimated_engagement": 8500,
      "estimated_roi": 2.3,
      "posting_schedule": [
        {
          "date": "2026-04-07",
          "posts": [
            {"platform": "twitter", "hour": 9},
            {"platform": "instagram", "hour": 12}
          ]
        }
      ]
    }
  }
}
```

### 6. Cancel Task

**Endpoint:** `POST /a2a/tasks/{task_id}/cancel`

Cancel a running or queued task.

**cURL Example:**
```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "User requested cancellation"}' \
  http://localhost:8004/a2a/tasks/task-blog-ai-20260407-a8c3f9e1/cancel
```

**Response (200 OK):**
```json
{
  "id": "task-blog-ai-20260407-a8c3f9e1",
  "status": {
    "state": "canceled",
    "message": "Task cancelled by user"
  }
}
```

---

## MCP Protocol (Model Context Protocol)

### 1. Initialize Connection

**Endpoint:** `POST /mcp/initialize`

Initiate MCP handshake to discover capabilities.

**Request Example:**
```json
{
  "protocolVersion": "2024-11-05",
  "clientInfo": {
    "name": "claude-desktop",
    "version": "1.0.0"
  }
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:8004/mcp/initialize \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "protocolVersion": "2024-11-05",
    "clientInfo": {"name": "claude-desktop", "version": "1.0.0"}
  }'
```

**Response (200 OK):**
```json
{
  "protocolVersion": "2024-11-05",
  "serverInfo": {
    "name": "FYP MCP Server",
    "version": "1.0.0"
  },
  "capabilities": [
    "tools",
    "resources",
    "prompts"
  ]
}
```

### 2. List Available Tools

**Endpoint:** `POST /mcp/tools/list`

Get all callable tools available to the LLM.

**Request Example:**
```json
{
  "jsonrpc": "2.0",
  "id": "mcp-001",
  "method": "tools/list"
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:8004/mcp/tools/list \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": "mcp-001", "method": "tools/list"}'
```

**Response (200 OK):**
```json
{
  "tools": [
    {
      "name": "seo_analyze",
      "description": "Perform comprehensive SEO analysis on a URL",
      "inputSchema": {
        "type": "object",
        "properties": {
          "url": {
            "type": "string",
            "description": "Website URL to analyze"
          },
          "analyze_competitors": {
            "type": "boolean",
            "description": "Whether to include competitor analysis"
          }
        },
        "required": ["url"]
      }
    },
    {
      "name": "content_generate_blog",
      "description": "Generate a blog post",
      "inputSchema": {
        "type": "object",
        "properties": {
          "topic": {"type": "string"},
          "brand": {"type": "string"},
          "tone": {"type": "string", "enum": ["professional", "casual", "technical"]},
          "length": {"type": "integer"}
        },
        "required": ["topic", "brand"]
      }
    },
    {
      "name": "keywords_extract",
      "description": "Extract keywords from text or URL",
      "inputSchema": {
        "type": "object",
        "properties": {
          "source": {"type": "string"},
          "language": {"type": "string", "default": "en"}
        },
        "required": ["source"]
      }
    },
    {
      "name": "webcrawler_extract",
      "description": "Crawl and extract data from a website",
      "inputSchema": {
        "type": "object",
        "properties": {
          "url": {"type": "string"},
          "depth": {"type": "integer", "default": 2}
        },
        "required": ["url"]
      }
    },
    {
      "name": "gap_analyzer_run",
      "description": "Perform competitive gap analysis",
      "inputSchema": {
        "type": "object",
        "properties": {
          "brand": {"type": "string"},
          "competitors": {"type": "array", "items": {"type": "string"}}
        },
        "required": ["brand", "competitors"]
      }
    },
    {
      "name": "query_knowledge_graph",
      "description": "Query the Neo4j knowledge graph",
      "inputSchema": {
        "type": "object",
        "properties": {
          "query": {"type": "string"},
          "limit": {"type": "integer", "default": 10}
        },
        "required": ["query"]
      }
    },
    {
      "name": "get_optimal_workflow",
      "description": "Get MABO-optimized workflow parameters",
      "inputSchema": {
        "type": "object",
        "properties": {
          "agent": {"type": "string"},
          "objective": {"type": "string"}
        },
        "required": ["agent", "objective"]
      }
    }
  ]
}
```

### 3. Call Tool

**Endpoint:** `POST /mcp/tools/call`

Invoke a specific tool with arguments.

**Request Example (SEO Analysis):**
```json
{
  "jsonrpc": "2.0",
  "id": "mcp-002",
  "method": "tools/call",
  "params": {
    "name": "seo_analyze",
    "arguments": {
      "url": "https://example.com",
      "analyze_competitors": true
    }
  }
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:8004/mcp/tools/call \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "mcp-002",
    "method": "tools/call",
    "params": {
      "name": "seo_analyze",
      "arguments": {"url": "https://example.com"}
    }
  }'
```

**Response (200 OK):**
```json
{
  "jsonrpc": "2.0",
  "id": "mcp-002",
  "result": {
    "url": "https://example.com",
    "score": 78,
    "metrics": {
      "performance": 85,
      "accessibility": 92,
      "seo": 75,
      "best_practices": 70
    },
    "issues": [
      {
        "type": "missing_meta_description",
        "severity": "high",
        "message": "Meta description tag is missing"
      }
    ],
    "recommendations": [
      "Add meta descriptions to all pages",
      "Improve Core Web Vitals"
    ]
  }
}
```

**Request Example (Generate Blog):**
```json
{
  "jsonrpc": "2.0",
  "id": "mcp-003",
  "method": "tools/call",
  "params": {
    "name": "content_generate_blog",
    "arguments": {
      "topic": "AI in Marketing",
      "brand": "TechCorp",
      "tone": "professional",
      "length": 1500
    }
  }
}
```

**Response (200 OK):**
```json
{
  "jsonrpc": "2.0",
  "id": "mcp-003",
  "result": {
    "title": "How AI is Transforming Modern Marketing Strategies",
    "content": "<html>...",
    "word_count": 1485,
    "estimated_read_time": 6,
    "seo_score": 85,
    "keywords": ["AI marketing", "automation", "personalization"],
    "preview_url": "https://localhost:8004/previews/blog-2026-04-07.html"
  }
}
```

### 4. List Resources

**Endpoint:** `POST /mcp/resources/list`

Discover available data resources.

**Request Example:**
```json
{
  "jsonrpc": "2.0",
  "id": "mcp-004",
  "method": "resources/list"
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:8004/mcp/resources/list \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"jsonrpc": "2.0", "id": "mcp-004", "method": "resources/list"}'
```

**Response (200 OK):**
```json
{
  "resources": [
    {
      "uri": "brand://*/profile",
      "name": "Brand Profile",
      "description": "Access brand characterization and context",
      "mimeType": "application/json"
    },
    {
      "uri": "content://*/generated",
      "name": "Generated Content",
      "description": "Access previously generated content",
      "mimeType": "application/json"
    },
    {
      "uri": "campaign://*/schedule",
      "name": "Campaign Schedule",
      "description": "Access campaign schedules and metrics",
      "mimeType": "application/json"
    },
    {
      "uri": "metrics://overview",
      "name": "Platform Metrics",
      "description": "Aggregated engagement metrics",
      "mimeType": "application/json"
    },
    {
      "uri": "knowledge://graph",
      "name": "Knowledge Graph",
      "description": "Neo4j semantic relationship graph",
      "mimeType": "text/plain"
    }
  ]
}
```

### 5. Read Resource

**Endpoint:** `POST /mcp/resources/read`

Access live data from a resource using URI.

**Request Example (Brand Profile):**
```json
{
  "jsonrpc": "2.0",
  "id": "mcp-005",
  "method": "resources/read",
  "params": {
    "uri": "brand://42"
  }
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:8004/mcp/resources/read \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "jsonrpc": "2.0",
    "id": "mcp-005",
    "method": "resources/read",
    "params": {"uri": "brand://42"}
  }'
```

**Response (200 OK):**
```json
{
  "jsonrpc": "2.0",
  "id": "mcp-005",
  "result": {
    "uri": "brand://42",
    "brand_id": 42,
    "name": "TechCorp",
    "tagline": "Innovation in Every Solution",
    "voice": {
      "tone": "professional",
      "personality_traits": ["innovative", "trustworthy", "forward-thinking"]
    },
    "values": ["Innovation", "Integrity", "Customer Focus"],
    "target_audience": {
      "primary": "Tech professionals",
      "secondary": "Decision makers in enterprise"
    },
    "visual_identity": {
      "primary_color": "#003366",
      "secondary_color": "#00A0D2"
    }
  }
}
```

**Request Example (Metrics Overview):**
```json
{
  "jsonrpc": "2.0",
  "id": "mcp-006",
  "method": "resources/read",
  "params": {
    "uri": "metrics://overview"
  }
}
```

**Response (200 OK):**
```json
{
  "jsonrpc": "2.0",
  "id": "mcp-006",
  "result": {
    "period": "2026-04-01 to 2026-04-07",
    "total_content_generated": 24,
    "total_engagement": 12450,
    "average_engagement_rate": 0.082,
    "campaigns_active": 3,
    "content_by_type": {
      "blog": 6,
      "social": 12,
      "email": 6
    },
    "top_performing_content": [
      {"id": 1, "engagement": 2150, "type": "blog"},
      {"id": 2, "engagement": 1890, "type": "social"}
    ],
    "roi": 3.45
  }
}
```

### 6. List Prompts

**Endpoint:** `POST /mcp/prompts/list`

Discover available workflow prompt templates.

**Request Example:**
```json
{
  "jsonrpc": "2.0",
  "id": "mcp-007",
  "method": "prompts/list"
}
```

**Response (200 OK):**
```json
{
  "prompts": [
    {
      "name": "blog_generation_workflow",
      "description": "End-to-end blog generation workflow",
      "arguments": ["topic", "brand", "audience"]
    },
    {
      "name": "social_campaign_workflow",
      "description": "Multi-platform social media campaign",
      "arguments": ["theme", "platforms", "duration_days"]
    },
    {
      "name": "competitor_analysis_workflow",
      "description": "Comprehensive competitive intelligence",
      "arguments": ["brand", "competitors"]
    },
    {
      "name": "content_optimization_workflow",
      "description": "SEO and engagement optimization",
      "arguments": ["content_id", "target_keywords"]
    }
  ]
}
```

### 7. Get Prompt Template

**Endpoint:** `POST /mcp/prompts/get`

Retrieve a specific workflow prompt with substitution variables.

**Request Example:**
```json
{
  "jsonrpc": "2.0",
  "id": "mcp-008",
  "method": "prompts/get",
  "params": {
    "name": "blog_generation_workflow",
    "arguments": {
      "topic": "AI",
      "brand": "TechCorp",
      "audience": "Tech professionals"
    }
  }
}
```

**Response (200 OK):**
```json
{
  "jsonrpc": "2.0",
  "id": "mcp-008",
  "result": {
    "name": "blog_generation_workflow",
    "template": "Generate a professional blog post about {topic} for {brand} targeting {audience}...",
    "rendered": "Generate a professional blog post about AI for TechCorp targeting Tech professionals...",
    "steps": [
      {"step": 1, "action": "Extract keywords"},
      {"step": 2, "action": "Analyze competitors"},
      {"step": 3, "action": "Generate content"},
      {"step": 4, "action": "Optimize for SEO"},
      {"step": 5, "action": "Generate preview"}
    ]
  }
}
```

---

## Implementation Examples

### Python Client (A2A)

```python
import json
import requests
from time import sleep

class A2AClient:
    def __init__(self, base_url="http://localhost:8004", token=None):
        self.base_url = base_url
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    
    def submit_task(self, task_description, metadata=None):
        """Submit a task and poll for completion"""
        payload = {
            "jsonrpc": "2.0",
            "id": "req-001",
            "method": "tasks.send",
            "params": {
                "task": {
                    "messages": [{
                        "role": "user",
                        "parts": [{
                            "type": "text",
                            "text": task_description
                        }]
                    }],
                    "metadata": metadata or {}
                }
            }
        }
        
        response = requests.post(
            f"{self.base_url}/a2a",
            headers=self.headers,
            json=payload
        )
        response.raise_for_status()
        result = response.json()
        return result
    
    def poll_task(self, task_id, max_retries=60, delay=5):
        """Poll task status until completion"""
        for attempt in range(max_retries):
            response = requests.get(
                f"{self.base_url}/a2a/tasks/{task_id}",
                headers=self.headers
            )
            response.raise_for_status()
            task = response.json()
            
            state = task["status"]["state"]
            print(f"[{attempt+1}] {state.upper()}: {task['status'].get('message')}")
            
            if state in ["completed", "failed", "canceled"]:
                return task
            
            sleep(delay)
        
        raise TimeoutError(f"Task {task_id} did not complete within {max_retries * delay}s")

# Usage
client = A2AClient(token="<your_jwt_token>")
result = client.submit_task(
    "Generate a blog post about AI marketing",
    metadata={"brand": "TechCorp", "tone": "professional"}
)
task_id = result["result"]["taskId"]
final_task = client.poll_task(task_id)
print(json.dumps(final_task, indent=2))
```

### Python Client (A2A SSE)

```python
import requests
import json

class A2ASSEClient:
    def __init__(self, base_url="http://localhost:8004", token=None):
        self.base_url = base_url
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    
    def subscribe_task(self, task_id, callback=None):
        """Subscribe to task with real-time updates"""
        with requests.post(
            f"{self.base_url}/a2a/tasks/{task_id}/subscribe",
            headers=self.headers,
            stream=True
        ) as response:
            response.raise_for_status()
            
            for line in response.iter_lines():
                if not line:
                    continue
                
                if line.startswith(b'event:'):
                    event_type = line.decode().split(': ', 1)[1]
                
                elif line.startswith(b'data:'):
                    data_str = line.decode().split(': ', 1)[1]
                    data = json.loads(data_str)
                    
                    if callback:
                        callback(event_type, data)
                    else:
                        print(f"[{event_type}] {data}")

# Usage
client = A2ASSEClient(token="<your_jwt_token>")

def handle_event(event, data):
    if event == "status":
        print(f"Status: {data['status']['message']}")
    elif event == "artifact":
        print(f"Generated: {data['artifact']['name']}")

client.subscribe_task("task-blog-ai-20260407-a8c3f9e1", callback=handle_event)
```

### Python Client (MCP)

```python
import requests
import json

class MCPClient:
    def __init__(self, base_url="http://localhost:8004", token=None):
        self.base_url = base_url
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    
    def list_tools(self):
        """Get all available tools"""
        payload = {
            "jsonrpc": "2.0",
            "id": "mcp-001",
            "method": "tools/list"
        }
        response = requests.post(
            f"{self.base_url}/mcp/tools/list",
            headers=self.headers,
            json=payload
        )
        response.raise_for_status()
        return response.json()["tools"]
    
    def call_tool(self, tool_name, arguments):
        """Call a tool with arguments"""
        payload = {
            "jsonrpc": "2.0",
            "id": "mcp-tool",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        response = requests.post(
            f"{self.base_url}/mcp/tools/call",
            headers=self.headers,
            json=payload
        )
        response.raise_for_status()
        return response.json()
    
    def read_resource(self, uri):
        """Read a resource by URI"""
        payload = {
            "jsonrpc": "2.0",
            "id": "mcp-resource",
            "method": "resources/read",
            "params": {"uri": uri}
        }
        response = requests.post(
            f"{self.base_url}/mcp/resources/read",
            headers=self.headers,
            json=payload
        )
        response.raise_for_status()
        return response.json()["result"]

# Usage
client = MCPClient(token="<your_jwt_token>")

# List tools
tools = client.list_tools()
print(f"Available tools: {[t['name'] for t in tools]}")

# Call tool
result = client.call_tool("seo_analyze", {"url": "https://example.com"})
print(f"SEO Score: {result['score']}")

# Read resource
brand = client.read_resource("brand://42")
print(f"Brand: {brand['name']}")
```

### JavaScript Client (A2A)

```javascript
class A2AClient {
  constructor(baseUrl = "http://localhost:8004", token = null) {
    this.baseUrl = baseUrl;
    this.token = token;
    this.headers = {
      "Authorization": `Bearer ${token}`,
      "Content-Type": "application/json"
    };
  }

  async submitTask(taskDescription, metadata = {}) {
    const payload = {
      jsonrpc: "2.0",
      id: "req-001",
      method: "tasks.send",
      params: {
        task: {
          messages: [{
            role: "user",
            parts: [{
              type: "text",
              text: taskDescription
            }]
          }],
          metadata
        }
      }
    };

    const response = await fetch(`${this.baseUrl}/a2a`, {
      method: "POST",
      headers: this.headers,
      body: JSON.stringify(payload)
    });

    return await response.json();
  }

  async pollTask(taskId, maxRetries = 60, delay = 5000) {
    for (let attempt = 0; attempt < maxRetries; attempt++) {
      const response = await fetch(
        `${this.baseUrl}/a2a/tasks/${taskId}`,
        { headers: this.headers }
      );
      const task = await response.json();

      console.log(`[${attempt + 1}] ${task.status.state}: ${task.status.message}`);

      if (["completed", "failed", "canceled"].includes(task.status.state)) {
        return task;
      }

      await new Promise(resolve => setTimeout(resolve, delay));
    }

    throw new Error(`Task ${taskId} did not complete within ${maxRetries * (delay / 1000)}s`);
  }

  async subscribeTask(taskId, onEvent) {
    const response = await fetch(
      `${this.baseUrl}/a2a/tasks/${taskId}/subscribe`,
      {
        method: "POST",
        headers: this.headers
      }
    );

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();

      for (const line of lines) {
        if (line.startsWith("event:")) {
          onEvent.event = line.split(": ")[1];
        } else if (line.startsWith("data:")) {
          const data = JSON.parse(line.split(": ")[1]);
          onEvent(onEvent.event, data);
        }
      }
    }
  }
}

// Usage
const client = new A2AClient("http://localhost:8004", "<your_jwt_token>");

// Submit task
const result = await client.submitTask(
  "Generate a blog post about AI marketing",
  { brand: "TechCorp", tone: "professional" }
);
const taskId = result.result.taskId;

// Poll for completion
const finalTask = await client.pollTask(taskId);
console.log(finalTask);
```

---

## Error Handling

### JSON-RPC Error Codes

| Code | Message | Meaning |
|------|---------|---------|
| -32700 | Parse error | Invalid JSON |
| -32600 | Invalid Request | Malformed request |
| -32601 | Method not found | Unknown method |
| -32602 | Invalid params | Wrong/missing parameters |
| -32603 | Internal error | Server error |

### Example Error Response

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "error": {
    "code": -32602,
    "message": "Invalid params",
    "data": {
      "details": "Field 'brand_name' is required",
      "field": "brand_name"
    }
  }
}
```

### Error Handling in Python

```python
try:
    result = client.submit_task("Generate blog post", {"brand": "Unknown"})
except requests.exceptions.HTTPError as e:
    error = e.response.json()
    if "error" in error:
        print(f"Error Code: {error['error']['code']}")
        print(f"Message: {error['error']['message']}")
        print(f"Details: {error['error'].get('data', {})}")
```

---

## Best Practices

### 1. **Always Validate Agent Discovery First**
```python
agent_card = requests.get("http://localhost:8004/.well-known/agent.json").json()
assert "tasks.send" in [c["method"] for c in agent_card["capabilities"]]
```

### 2. **Use SSE for Long-Running Tasks**
For tasks expected to take >30 seconds, use SSE subscription instead of polling:
```python
client.subscribe_task(task_id, callback=handle_event)  # Real-time updates
# vs.
client.poll_task(task_id)  # Polling every 5 seconds
```

### 3. **Implement Exponential Backoff for Polling**
```python
delay = 1
while not done:
    sleep(delay)
    # Poll task...
    delay = min(delay * 1.5, 30)  # Cap at 30s
```

### 4. **Always Include Metadata**
```json
"metadata": {
  "intent": "blog_generation",
  "brand_name": "TechCorp",
  "user_id": "user-123",
  "correlation_id": "req-xyz"
}
```

### 5. **Handle Task Timeouts Gracefully**
```python
try:
    task = client.poll_task(task_id, max_retries=120, delay=5)
except TimeoutError:
    # Cancel the task
    client.cancel_task(task_id)
    # Fall back to cached content or retry
```

### 6. **Cache MCP Tool Schemas**
```python
# Get tools once and cache
tools = client.list_tools()
with open("tools_cache.json", "w") as f:
    json.dump(tools, f)

# Load from cache in subsequent calls
with open("tools_cache.json", "r") as f:
    tools = json.load(f)
```

### 7. **Validate Input Parameters**
```python
def submit_campaign(campaign):
    required = ["theme", "tier", "duration_days", "budget"]
    missing = [f for f in required if f not in campaign]
    if missing:
        raise ValueError(f"Missing required fields: {missing}")
    # Proceed...
```

### 8. **Implement Circuit Breaker**
```python
class CircuitBreaker:
    def __init__(self, failure_threshold=5):
        self.failure_count = 0
        self.threshold = failure_threshold
        self.is_open = False
    
    def call(self, func, *args, **kwargs):
        if self.is_open:
            raise Exception("Circuit breaker is open")
        try:
            result = func(*args, **kwargs)
            self.failure_count = 0
            return result
        except Exception as e:
            self.failure_count += 1
            if self.failure_count >= self.threshold:
                self.is_open = True
            raise
```

---

## Rate Limiting

- **Max concurrent tasks per agent**: 10
- **Max polling attempts**: 60 (5 minutes)
- **SSE max connections per task**: 5
- **Request rate limit**: 100 req/min per token

---

## Webhooks (Future)

Coming in v1.1:
- Task completion webhooks
- Campaign milestone webhooks
- Metrics update webhooks

---

## Support & Debugging

### Enable Verbose Logging
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Check System Status
```bash
curl http://localhost:8004/health
curl -H "Authorization: Bearer $TOKEN" http://localhost:8004/status
```

### Monitor Live Traces
- Open LangSmith UI: https://smith.langchain.com
- Filter by session/trace ID from task ID
- View agent execution flow and token usage

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-04-07 | Initial release: A2A + MCP |
| 0.1.0 (beta) | 2026-03-20 | Alpha testing |

---

Last Updated: **2026-04-07**  
Maintained By: FYP Marketing Platform Team
