# Live Agent Visualizer - Quick Start Guide

## What Was Built

A **real-time agent execution visualizer** similar to **n8n** and **LangSmith** that shows:
- 📊 Live workflow execution with node-level tracing
- 🔄 Real-time updates via WebSocket
- 📈 Timeline visualization of execution flow
- 🔍 Input/output inspection for each node
- ⚡ Status indicators (running/success/error)
- 📜 Trace history

## How to Use

### 1. Start the Backend (if not already running)
```bash
python3 orchestrator.py
```

The orchestrator will start on `http://localhost:8004` with WebSocket support.

### 2. Open the Visualizer
Navigate to: **http://localhost:3000/visualizer**

You should see:
- **Left Panel**: List of recent execution traces
- **Right Panel**: Detailed execution timeline (select a trace to view)
- **Connection Status**: Green dot = connected, Red dot = disconnected

### 3. Trigger an Execution

**Option A: From Chat UI**
1. Open `http://localhost:3000/` in another tab
2. Send any message (e.g., "What can you do?")
3. Watch the visualizer update in real-time!

**Option B: From Protocol Dashboard**
1. Open `http://localhost:3000/protocols`
2. Click "Test A2A"
3. Watch the execution flow

**Option C: Direct API Call**
```bash
curl -X POST http://localhost:8004/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test_token_user1" \
  -d '{"message": "Tell me about your capabilities", "user_id": 1}'
```

### 4. What You'll See

The visualizer will show:

**Trace Metadata:**
- Trace ID (e.g., `chat_sess_abc123_1775040000`)
- User ID and Session ID
- User message
- Intent classification
- Workflow type (langgraph/a2a)
- Start time and duration

**Node Events:**
- 🔵 **Blue** = Node started
- 🟢 **Green** = Node completed successfully
- 🔴 **Red** = Node encountered error
- 🟡 **Yellow** = Progress update (optional)

**Example Timeline:**
```
14:42:38  🔵 router started
14:42:38  🟢 router completed (intent: general_chat, confidence: 0.95)
14:42:39  🔵 chat started
14:42:39  🟢 chat completed (response: 450 chars)
```

**Event Details:**
Click any event to see:
- Full input/output data (JSON)
- Timestamp
- Duration
- Node-specific metadata

## Currently Instrumented Nodes

✅ **Router Node** - Intent classification and workflow selection  
✅ **Chat Node** - General conversation handling

**Coming Soon:**
- Blog generation node
- Social post generation node
- SEO analysis node
- Image generation node
- Research node

## WebSocket Events

The visualizer receives real-time events:

### `trace_start`
When a new execution begins:
```json
{
  "type": "trace_start",
  "trace_id": "chat_sess_abc123_1775040000",
  "metadata": {
    "user_id": 1,
    "session_id": "sess_abc123",
    "user_message": "Create a blog post",
    "intent": "blog_generation",
    "workflow": "langgraph",
    "status": "running",
    "start_time": "2026-04-01T15:01:35.000Z"
  }
}
```

### `node_event`
When a node starts/completes/errors:
```json
{
  "type": "node_event",
  "trace_id": "chat_sess_abc123_1775040000",
  "event_type": "complete",
  "node": "router",
  "timestamp": "2026-04-01T15:01:36.000Z",
  "data": {
    "intent": "blog_generation",
    "confidence": 0.95,
    "extracted_params": {"topic": "AI marketing"}
  }
}
```

### `trace_complete`
When the entire workflow finishes:
```json
{
  "type": "trace_complete",
  "trace_id": "chat_sess_abc123_1775040000",
  "metadata": {
    "status": "success",
    "end_time": "2026-04-01T15:01:40.000Z",
    "duration_ms": 5234
  }
}
```

## Troubleshooting

### ❌ WebSocket Not Connecting
- **Check**: Is orchestrator running on port 8004?
- **Fix**: Restart orchestrator: `python3 orchestrator.py`

### ❌ No Traces Appearing
- **Check**: Are you sending messages from the chat UI?
- **Fix**: Make sure you've triggered an execution (send a chat message)

### ❌ Events Not Updating
- **Check**: Is the green connection indicator showing?
- **Fix**: Refresh the page to reconnect WebSocket

### ❌ "NameError: llm_intent is not defined"
- **Status**: ✅ **FIXED** in latest version
- The intent is now set to "unknown" and determined by the router node

## Technical Details

**Backend:**
- `trace_manager.py` - In-memory trace storage and WebSocket broadcasting
- `orchestrator.py` - WebSocket endpoints (`/ws/traces`, `/ws/traces/{trace_id}`)
- `langgraph_nodes.py` - Node instrumentation with `emit_trace()`
- `langgraph_state.py` - Added `trace_id` to state

**Frontend:**
- `frontend/app/visualizer/page.tsx` - React visualization UI
- WebSocket client for real-time updates
- Timeline-based event display

## Next Steps

### Extend Coverage
Add tracing to more nodes by using the `emit_trace()` helper:

```python
async def your_node(state: MarketingState):
    emit_trace(state, "start", "your_node", {"input": ...})
    
    # ... do work ...
    
    emit_trace(state, "complete", "your_node", {"output": ...})
```

### Enhance Visualization
- Add React Flow graph view
- Add performance metrics (execution time, cost)
- Add filtering and search
- Add export to JSON

### Persist Traces
- Store traces in SQLite
- Add historical analysis
- Add replay functionality

## Files to Review

| File | Purpose |
|------|---------|
| `LIVE_VISUALIZER_GUIDE.md` | Comprehensive guide with architecture |
| `VISUALIZER_IMPLEMENTATION_SUMMARY.md` | Implementation details and changes |
| `trace_manager.py` | Core trace management logic |
| `orchestrator.py` | WebSocket endpoints |
| `frontend/app/visualizer/page.tsx` | Visualization UI |

## Summary

You now have a **fully functional live agent execution visualizer** that provides:
- Real-time visibility into agent workflows
- Debugging capabilities with input/output inspection
- Professional n8n/LangSmith-like interface

**Start using it now:**
1. Open `http://localhost:3000/visualizer`
2. Send a chat message
3. Watch the magic happen! ✨

For detailed documentation, see `LIVE_VISUALIZER_GUIDE.md`.

