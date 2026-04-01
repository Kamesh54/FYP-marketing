# Protocol Visualization Dashboard Guide

## Overview

The Protocol Visualization Dashboard (`/protocols` page) provides a real-time, interactive view of:
- **A2A Protocol** (Agent-to-Agent communication)
- **MCP Protocol** (Model Context Protocol)

This allows developers and users to understand how agents communicate and interact with each other in the system.

---

## 🚀 Features

### 1. **Dual Protocol Support**
- **A2A (Agent-to-Agent)**: JSON-RPC 2.0 based inter-agent communication
- **MCP (Model Context Protocol)**: Tool, resource, and prompt management

### 2. **Real-Time Monitoring**
- Live message timeline with request/response tracking
- Agent status monitoring (active/idle/error)
- Message payload inspection
- Success/error status indicators

### 3. **Interactive Flow Diagrams**
- Visual representation of message flows
- Color-coded nodes showing active components
- Request/response direction arrows

### 4. **Testing Tools**
- One-click protocol testing buttons
- Automatic message capture
- Detailed payload inspection

---

## 📊 How to Use

### Step 1: Login First
The protocol endpoints require authentication. Make sure you're logged in:
1. Go to `/login` or `/signup`
2. Login with your credentials
3. The JWT token is automatically stored in localStorage

### Step 2: Access the Dashboard
Navigate to: `http://localhost:3000/protocols`

### Step 3: Select a Protocol
Click either:
- **A2A Protocol** button (blue)
- **MCP Protocol** button (purple)

### Step 4: Test Communication
Click the **"Test A2A"** or **"Test MCP"** button to send a test request.

### Step 5: View Results
- Messages appear in the timeline
- Click any message to see detailed payload
- Check agent status in the right panel

---

## 🔧 Technical Details

### A2A Protocol

**Endpoint**: `POST http://127.0.0.1:8004/a2a`

**Request Format** (JSON-RPC 2.0):
```json
{
  "jsonrpc": "2.0",
  "id": 1234567890,
  "method": "agent.execute",
  "params": {
    "task": "Generate marketing content",
    "context": {
      "user_id": 1,
      "brand_id": 1
    }
  }
}
```

**Headers Required**:
```
Content-Type: application/json
Authorization: Bearer <your_jwt_token>
```

**Supported Methods**:
- `tasks.send` - Send a task to an agent
- `tasks.sendSubscribe` - Send task with streaming updates
- `tasks.cancel` - Cancel a running task
- `tasks.pushNotification.set` - Configure push notifications

### MCP Protocol

**Endpoints**:
- `POST /mcp/initialize` - Initialize MCP session
- `POST /mcp/tools/list` - List available tools
- `POST /mcp/tools/call` - Call a specific tool
- `GET /mcp/resources/list` - List resources
- `POST /mcp/resources/read` - Read a resource
- `GET /mcp/prompts/list` - List prompt templates

**Example Tool Call**:
```json
{
  "name": "get_brand_profiles",
  "arguments": {
    "user_id": 1
  }
}
```

**Available MCP Tools**:
- `get_brand_profiles` - Fetch brand profiles
- `update_brand_profile` - Update brand information
- `generate_content` - Generate marketing content
- `get_campaign_metrics` - Retrieve performance metrics
- And 10+ more...

---

## 🎨 UI Components

### Left Panel (8/12 width)
1. **Flow Diagram Card**
   - Visual representation of communication flow
   - Shows: Client → Orchestrator → Agent
   - Animated arrows for active flows

2. **Message Timeline Card**
   - Chronological list of all protocol messages
   - Click to expand and view details
   - Status indicators (✓ success, ⏰ pending, ❌ error)

### Right Panel (4/12 width)
1. **Active Agents Card**
   - Lists all registered agents
   - Shows status (green=active, yellow=idle, red=error)
   - Lists agent capabilities

2. **Message Details Card** (appears when message selected)
   - Method name
   - Full JSON payload
   - Timestamp

3. **Protocol Spec Card**
   - Quick reference for protocol details
   - Available endpoints
   - Supported methods

---

## 🔐 Authentication

The dashboard uses the same authentication as the rest of the application:

1. **Token Storage**: JWT token stored in `localStorage.getItem('auth_token')`
2. **Header Format**: `Authorization: Bearer <token>`
3. **Token Source**: Obtained from `/auth/login` endpoint

If you get **401 Unauthorized** errors:
- Ensure you're logged in
- Check browser console for token presence
- Try logging out and back in
- Clear localStorage if needed

---

## 🐛 Troubleshooting

### "401 Unauthorized" Error
- **Cause**: Missing or invalid JWT token
- **Fix**: Login via `/login` page first

### "No messages yet"
- **Cause**: Haven't tested protocols yet
- **Fix**: Click "Test A2A" or "Test MCP" button

### Agents showing as "error"
- **Cause**: Agent service might be down
- **Fix**: Check if orchestrator and agents are running:
  ```bash
  # Check orchestrator
  curl http://127.0.0.1:8004/
  
  # Check brand agent
  curl http://127.0.0.1:8006/
  ```

### Messages not updating in real-time
- **Cause**: "Live" mode not enabled
- **Fix**: Click "Start Live" button in top-right

---

## 📝 Development Notes

### Adding New Protocol Messages
To capture custom protocol messages in the timeline, dispatch them from your code:

```typescript
const newMessage: ProtocolMessage = {
  id: String(Date.now()),
  timestamp: new Date().toISOString(),
  type: 'a2a', // or 'mcp'
  direction: 'request', // or 'response'
  from: 'client',
  to: 'orchestrator',
  method: 'custom.method',
  payload: { /* your data */ },
  status: 'success' // or 'pending' or 'error'
};
```

### Customizing Flow Diagrams
Edit the `A2AFlowDiagram` or `MCPFlowDiagram` components in `frontend/app/protocols/page.tsx`.

---

## 🌐 Live Demo

Visit: `http://localhost:3000/protocols` (after starting the frontend)


