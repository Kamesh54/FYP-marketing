# MCP & A2A Protocol Integration Guide

## Overview

Your FYP Marketing Platform now supports two industry-standard agent communication protocols:

- **MCP (Model Context Protocol)**: Exposes agents as tools for LLM integration
- **A2A (Agent-to-Agent Protocol)**: Enables inter-agent task coordination

Both protocols are **enabled by default** as of v5.0.

---

## 🔧 MCP (Model Context Protocol)

### What is MCP?

MCP is Anthropic's protocol for connecting LLMs to external tools and resources. It allows Claude, GPT-4, and other LLMs to use your marketing agents as function tools.

### MCP Endpoints

All MCP endpoints are available at `http://localhost:8004/mcp/*`:

```
POST /mcp/initialize          # Initialize MCP connection
POST /mcp/tools/list          # List available tools
POST /mcp/tools/call          # Execute a tool
POST /mcp/resources/list      # List available resources
POST /mcp/resources/read      # Read a resource
POST /mcp/prompts/list        # List prompt templates
POST /mcp/prompts/get         # Get a prompt template
```

### Available MCP Tools

| Tool Name | Description | Required Parameters |
|-----------|-------------|---------------------|
| `webcrawler_extract` | Extract website content | `url` |
| `seo_analyze` | SEO analysis | `url` |
| `keywords_extract` | Keyword extraction | `text` or `url` |
| `gap_analyzer_run` | Competitor gap analysis | `domain`, `keywords` |
| `content_generate_blog` | Generate blog post | `topic` |
| `content_generate_social` | Generate social post | `topic`, `platform` |
| `image_generate` | AI image generation | `prompt` |
| `brand_extract` | Extract brand identity | `url` |
| `research_deep` | Deep research | `topic` |
| `reddit_research` | Reddit insights | `keywords` |
| `campaign_plan` | Campaign planning | `goal` |

### MCP Resources

Access database entities via URIs:

- `brand://{brand_id}` - Brand profile data
- `content://{content_id}` - Generated content
- `campaign://{campaign_id}` - Campaign data
- `metrics://overview` - Performance metrics
- `knowledge://graph` - Knowledge graph access

### MCP Prompt Templates

Pre-built workflows:

1. **blog_generation_workflow** - Complete blog generation
2. **social_campaign_workflow** - Multi-platform campaign
3. **competitor_analysis_workflow** - Competitor research
4. **content_optimization_workflow** - SEO optimization

### Example: Using MCP with Claude Desktop

**1. Initialize Connection**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05",
    "clientInfo": {
      "name": "claude-desktop",
      "version": "1.0.0"
    },
    "capabilities": {}
  }
}
```

**2. List Tools**
```bash
curl -X POST http://localhost:8004/mcp/tools/list \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/list"
  }'
```

**3. Call a Tool**
```bash
curl -X POST http://localhost:8004/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "seo_analyze",
      "arguments": {
        "url": "https://example.com"
      }
    }
  }'
```

### MCP Configuration in Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "fyp-marketing": {
      "url": "http://localhost:8004/mcp",
      "type": "http",
      "headers": {
        "Authorization": "Bearer YOUR_JWT_TOKEN"
      }
    }
  }
}
```

---

## 🤖 A2A (Agent-to-Agent Protocol)

### What is A2A?

A2A is Google's JSON-RPC protocol for agent-to-agent communication. It enables task delegation, status tracking, and result streaming between agents.

### A2A Endpoints

```
GET  /.well-known/agent.json   # AgentCard discovery
POST /a2a                       # JSON-RPC endpoint
POST /a2a/tasks/{task_id}/subscribe  # SSE updates
POST /a2a/tasks/{task_id}/cancel     # Cancel task
```

### AgentCard

Discover agent capabilities:

```bash
curl http://localhost:8004/.well-known/agent.json
```

Response:
```json
{
  "name": "FYP Orchestrator",
  "description": "Multi-agent marketing platform",
  "a2aVersion": "0.1",
  "a2aEndpointUrl": "http://localhost:8004/a2a",
  "capabilities": [
    {
      "method": "tasks.send",
      "description": "Submit a task and receive result"
    },
    {
      "method": "tasks.sendSubscribe",
      "description": "Submit task with SSE updates"
    }
  ]
}
```

### Example: Submit Task via A2A

```bash
curl -X POST http://localhost:8004/a2a \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "jsonrpc": "2.0",
    "id": "req-123",
    "method": "tasks.send",
    "params": {
      "task": {
        "messages": [
          {
            "role": "user",
            "parts": [
              {
                "content": "Generate a blog post about AI marketing"
              }
            ]
          }
        ]
      }
    }
  }'
```

### A2A with SSE Streaming

```bash
curl -N http://localhost:8004/a2a/tasks/{task_id}/subscribe
```

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env and add your API keys
```

### 3. Start the Orchestrator

```bash
python orchestrator.py
```

### 4. Verify Protocols

```bash
# Check MCP
curl http://localhost:8004/ | jq .protocols

# Check A2A AgentCard
curl http://localhost:8004/.well-known/agent.json | jq .
```

---

## 📊 Protocol Comparison

| Feature | MCP | A2A |
|---------|-----|-----|
| **Purpose** | LLM ↔ Agent | Agent ↔ Agent |
| **Primary Use** | Tool calling | Task delegation |
| **Streaming** | No | Yes (SSE) |
| **Discovery** | Tool listing | AgentCard |
| **Auth** | Optional | JWT required |
| **Best For** | Claude, GPT-4 | Multi-agent systems |

---

## 🔐 Authentication

### MCP
- Optional for tool listing
- JWT recommended for tool execution
- Pass via `Authorization` header

### A2A
- JWT required for all endpoints
- Obtain via `/auth/login`
- Rate limited: 100 req/min

---

## 🛠️ Development

### Disable Protocols

In `.env`:
```bash
ENABLE_MCP=false
ENABLE_A2A=false
```

### Add Custom MCP Tool

Edit `mcp_server.py`:

```python
MCPTool(
    name="your_tool_name",
    description="What it does",
    inputSchema=MCPToolInputSchema(
        properties={
            "param": {"type": "string", "description": "Parameter description"}
        },
        required=["param"]
    )
)
```

Then add handler in `_call_tool()` method.

---

## 📚 Additional Resources

- [MCP Specification](https://spec.modelcontextprotocol.io/)
- [A2A Protocol](https://github.com/google/a2a)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [FYP Platform README](README.md)

---

## ❓ Troubleshooting

### MCP tool calls failing?
- Check ENABLE_MCP=true in .env
- Verify agents are running (start.bat)
- Check logs for specific errors

### A2A 429 errors?
- Rate limit: 100 requests/minute per IP
- Implement client-side throttling

### Resources not found?
- Ensure database is initialized
- Check brand/content IDs exist
- Verify authentication token

---

**Version**: 1.0.0  
**Last Updated**: 2026-04-01  
**Platform**: FYP Marketing v5.0

