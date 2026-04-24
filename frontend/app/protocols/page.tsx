'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import {
  Network,
  Workflow,
  MessageSquare,
  Database,
  Zap,
  ArrowRight,
  CheckCircle2,
  Clock,
  AlertCircle,
  Play,
  Code,
  FileJson,
  Activity
} from 'lucide-react';

interface ProtocolMessage {
  id: string;
  timestamp: string;
  type: 'a2a' | 'mcp';
  direction: 'request' | 'response';
  from: string;
  to: string;
  method: string;
  payload: any;
  status: 'pending' | 'success' | 'error';
}

interface Agent {
  id: string;
  name: string;
  status: 'active' | 'idle' | 'error';
  capabilities: string[];
}

export default function ProtocolsPage() {
  const [selectedProtocol, setSelectedProtocol] = useState<'a2a' | 'mcp'>('a2a');
  const [messages, setMessages] = useState<ProtocolMessage[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [isLive, setIsLive] = useState(false);
  const [selectedMessage, setSelectedMessage] = useState<ProtocolMessage | null>(null);

  // Fetch agents and messages
  useEffect(() => {
    fetchAgents();
    if (isLive) {
      const interval = setInterval(fetchMessages, 2000);
      return () => clearInterval(interval);
    }
  }, [isLive, selectedProtocol]);

  const fetchAgents = async () => {
    try {
      const response = await fetch('http://127.0.0.1:8004/');
      await response.json();

      // Mock agents for demo - in production, fetch from API
      setAgents([
        { id: 'orchestrator', name: 'Orchestrator', status: 'active', capabilities: ['routing', 'coordination'] },
        { id: 'content', name: 'Content Agent', status: 'active', capabilities: ['blog_writing', 'social_posts'] },
        { id: 'brand', name: 'Brand Agent', status: 'active', capabilities: ['brand_management'] },
        { id: 'image', name: 'Image Agent', status: 'idle', capabilities: ['image_generation'] },
      ]);
    } catch (error) {
      console.error('Failed to fetch agents:', error);
    }
  };

  const fetchMessages = async () => {
    // In production, this would fetch real protocol messages
    // For now, we'll simulate some messages
    const mockMessages: ProtocolMessage[] = [
      {
        id: '1',
        timestamp: new Date().toISOString(),
        type: selectedProtocol,
        direction: 'request',
        from: 'client',
        to: 'orchestrator',
        method: selectedProtocol === 'a2a' ? 'agent.execute' : 'tools/call',
        payload: { task: 'Generate blog post' },
        status: 'success'
      }
    ];
    setMessages(mockMessages);
  };

  const testA2AProtocol = async () => {
    try {
      // Get auth token from localStorage (check both possible keys)
      const token = localStorage.getItem('authToken') || localStorage.getItem('auth_token');

      if (!token) {
        alert('Please login first to test A2A protocol. Go to /login page.');
        return;
      }

      const taskId = `test_${Date.now()}`;

      const response = await fetch('http://127.0.0.1:8004/a2a', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          jsonrpc: '2.0',
          id: Date.now(),
          method: 'tasks.send',
          params: {
            taskId: taskId,
            messages: [
              {
                role: 'user',
                parts: [
                  {
                    type: 'text',
                    text: 'Generate a creative Instagram post about motorcycles for my brand'
                  }
                ]
              }
            ],
            metadata: {
              // Leave brand empty to auto-select user's first brand from database
              test: true,
              source: 'protocol_dashboard'
            }
          }
        })
      });

      const data = await response.json();
      console.log('A2A Response:', data);

      // Add message to timeline
      const newMessage: ProtocolMessage = {
        id: String(Date.now()),
        timestamp: new Date().toISOString(),
        type: 'a2a',
        direction: 'response',
        from: 'orchestrator',
        to: 'client',
        method: 'agent.execute',
        payload: data,
        status: response.ok ? 'success' : 'error'
      };

      setMessages(prev => [newMessage, ...prev]);

      if (!response.ok) {
        alert(`A2A Test Failed: ${data.error?.message || 'Authentication required. Please login first.'}`);
      }
    } catch (error) {
      console.error('A2A Test failed:', error);
      alert('A2A Test failed. Check console for details.');
    }
  };

  const testMCPProtocol = async () => {
    try {
      const token = localStorage.getItem('authToken') || localStorage.getItem('auth_token');

      // First, list available tools
      // MCP uses JSON-RPC style requests
      const listResponse = await fetch('http://127.0.0.1:8004/mcp/tools/list', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
          // No auth required for tools/list
        },
        body: JSON.stringify({
          id: Date.now(),
          method: 'tools/list',
          params: {}
        })
      });

      const toolsData = await listResponse.json();
      console.log('MCP Tools:', toolsData);

      // Add message for tools/list
      const listMessage: ProtocolMessage = {
        id: String(Date.now()),
        timestamp: new Date().toISOString(),
        type: 'mcp',
        direction: 'response',
        from: 'mcp_server',
        to: 'client',
        method: 'tools/list',
        payload: toolsData,
        status: listResponse.ok ? 'success' : 'error'
      };

      setMessages(prev => [listMessage, ...prev]);

      // Test a tool call
      if (listResponse.ok && toolsData.tools && toolsData.tools.length > 0) {
        setTimeout(async () => {
          const callResponse = await fetch('http://127.0.0.1:8004/mcp/tools/call', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': token ? `Bearer ${token}` : ''
            },
            body: JSON.stringify({
              id: Date.now() + 1,
              method: 'tools/call',
              params: {
                name: 'get_brand_profiles',
                arguments: { user_id: 1 }
              }
            })
          });

          const callData = await callResponse.json();
          console.log('MCP Tool Call:', callData);

          const callMessage: ProtocolMessage = {
            id: String(Date.now() + 1),
            timestamp: new Date().toISOString(),
            type: 'mcp',
            direction: 'response',
            from: 'mcp_server',
            to: 'client',
            method: 'tools/call',
            payload: callData,
            status: callResponse.ok ? 'success' : 'error'
          };

          setMessages(prev => [callMessage, ...prev]);
        }, 1000);
      }

      if (!listResponse.ok) {
        alert(`MCP Test Failed: ${toolsData.error?.message || 'Authentication required. Please login first.'}`);
      }
    } catch (error) {
      console.error('MCP Test failed:', error);
      alert('MCP Test failed. Check console for details.');
    }
  };

  return (
    <div className="min-h-screen p-8" style={{ background: 'var(--background)' }}>
      {/* Header */}
      <div className="max-w-7xl mx-auto mb-8">
        <h1 className="text-4xl font-bold mb-2" style={{ color: 'var(--text-primary)' }}>
          Protocol Visualization
        </h1>
        <p className="text-lg" style={{ color: 'var(--text-secondary)' }}>
          Real-time monitoring of A2A and MCP protocol communications
        </p>
        <div className="mt-3">
          <Link href="/a2a-demo" className="text-cyan-400 hover:text-cyan-300 underline">
            Open External User-Agent Demo
          </Link>
        </div>
      </div>

      {/* Protocol Selector */}
      <div className="max-w-7xl mx-auto mb-6 flex gap-4">
        <button
          onClick={() => setSelectedProtocol('a2a')}
          className={`flex items-center gap-2 px-6 py-3 rounded-lg font-semibold transition-all ${
            selectedProtocol === 'a2a'
              ? 'bg-gradient-to-r from-blue-500 to-blue-600 text-white shadow-lg'
              : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
          }`}
        >
          <Network className="w-5 h-5" />
          A2A Protocol
        </button>
        
        <button
          onClick={() => setSelectedProtocol('mcp')}
          className={`flex items-center gap-2 px-6 py-3 rounded-lg font-semibold transition-all ${
            selectedProtocol === 'mcp'
              ? 'bg-gradient-to-r from-purple-500 to-purple-600 text-white shadow-lg'
              : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
          }`}
        >
          <Database className="w-5 h-5" />
          MCP Protocol
        </button>

        <button
          onClick={() => setIsLive(!isLive)}
          className={`flex items-center gap-2 px-6 py-3 rounded-lg font-semibold transition-all ml-auto ${
            isLive
              ? 'bg-green-500 text-white'
              : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
          }`}
        >
          {isLive ? <Activity className="w-5 h-5 animate-pulse" /> : <Play className="w-5 h-5" />}
          {isLive ? 'Live' : 'Start Live'}
        </button>
      </div>

      <div className="max-w-7xl mx-auto grid grid-cols-12 gap-6">
        {/* Left Panel - Flow Diagram */}
        <div className="col-span-8 space-y-6">
          {/* Flow Diagram Card */}
          <div className="rounded-xl p-6 shadow-lg" style={{ background: 'var(--surface)' }}>
            <h2 className="text-2xl font-bold mb-4 flex items-center gap-2" style={{ color: 'var(--text-primary)' }}>
              <Workflow className="w-6 h-6" />
              {selectedProtocol === 'a2a' ? 'A2A Communication Flow' : 'MCP Interaction Flow'}
            </h2>

            {selectedProtocol === 'a2a' ? <A2AFlowDiagram /> : <MCPFlowDiagram />}
          </div>

          {/* Message Timeline */}
          <div className="rounded-xl p-6 shadow-lg" style={{ background: 'var(--surface)' }}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-2xl font-bold flex items-center gap-2" style={{ color: 'var(--text-primary)' }}>
                <MessageSquare className="w-6 h-6" />
                Message Timeline
              </h2>
              <button
                onClick={selectedProtocol === 'a2a' ? testA2AProtocol : testMCPProtocol}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-500 text-white hover:bg-blue-600 transition-colors"
              >
                <Play className="w-4 h-4" />
                Test {selectedProtocol.toUpperCase()}
              </button>
            </div>

            <div className="space-y-3">
              {messages.length === 0 ? (
                <div className="text-center py-12" style={{ color: 'var(--text-secondary)' }}>
                  <Clock className="w-12 h-12 mx-auto mb-3 opacity-50" />
                  <p>No messages yet. Click "Test {selectedProtocol.toUpperCase()}" to send a test message.</p>
                </div>
              ) : (
                messages.map((msg) => (
                  <div
                    key={msg.id}
                    onClick={() => setSelectedMessage(msg)}
                    className="p-4 rounded-lg cursor-pointer transition-all hover:scale-[1.02]"
                    style={{
                      background: 'var(--surface-hover)',
                      border: selectedMessage?.id === msg.id ? '2px solid var(--accent)' : '2px solid transparent'
                    }}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-sm px-2 py-1 rounded" style={{ background: 'var(--background)' }}>
                          {msg.method}
                        </span>
                        <ArrowRight className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
                        <span className="font-semibold">{msg.to}</span>
                      </div>
                      {msg.status === 'success' && <CheckCircle2 className="w-5 h-5 text-green-500" />}
                      {msg.status === 'pending' && <Clock className="w-5 h-5 text-yellow-500" />}
                      {msg.status === 'error' && <AlertCircle className="w-5 h-5 text-red-500" />}
                    </div>
                    <div className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                      {new Date(msg.timestamp).toLocaleTimeString()}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Right Panel - Details */}
        <div className="col-span-4 space-y-6">
          {/* Active Agents */}
          <div className="rounded-xl p-6 shadow-lg" style={{ background: 'var(--surface)' }}>
            <h2 className="text-xl font-bold mb-4 flex items-center gap-2" style={{ color: 'var(--text-primary)' }}>
              <Network className="w-5 h-5" />
              Active Agents
            </h2>
            <div className="space-y-3">
              {agents.map((agent) => (
                <div
                  key={agent.id}
                  className="p-3 rounded-lg"
                  style={{ background: 'var(--background)' }}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-semibold" style={{ color: 'var(--text-primary)' }}>
                      {agent.name}
                    </span>
                    <span
                      className={`w-2 h-2 rounded-full ${
                        agent.status === 'active' ? 'bg-green-500' :
                        agent.status === 'idle' ? 'bg-yellow-500' : 'bg-red-500'
                      }`}
                    />
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {agent.capabilities.map((cap) => (
                      <span
                        key={cap}
                        className="text-xs px-2 py-1 rounded"
                        style={{ background: 'var(--surface-hover)', color: 'var(--text-secondary)' }}
                      >
                        {cap}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Message Details */}
          {selectedMessage && (
            <div className="rounded-xl p-6 shadow-lg" style={{ background: 'var(--surface)' }}>
              <h2 className="text-xl font-bold mb-4 flex items-center gap-2" style={{ color: 'var(--text-primary)' }}>
                <Code className="w-5 h-5" />
                Message Details
              </h2>
              <div className="space-y-3">
                <div>
                  <label className="text-sm font-semibold" style={{ color: 'var(--text-secondary)' }}>Method</label>
                  <div className="font-mono text-sm p-2 rounded mt-1" style={{ background: 'var(--background)' }}>
                    {selectedMessage.method}
                  </div>
                </div>
                <div>
                  <label className="text-sm font-semibold" style={{ color: 'var(--text-secondary)' }}>Payload</label>
                  <pre className="font-mono text-xs p-3 rounded mt-1 overflow-auto max-h-64" style={{ background: 'var(--background)' }}>
                    {JSON.stringify(selectedMessage.payload, null, 2)}
                  </pre>
                </div>
              </div>
            </div>
          )}

          {/* Protocol Info */}
          <div className="rounded-xl p-6 shadow-lg" style={{ background: 'var(--surface)' }}>
            <h2 className="text-xl font-bold mb-4 flex items-center gap-2" style={{ color: 'var(--text-primary)' }}>
              <FileJson className="w-5 h-5" />
              {selectedProtocol === 'a2a' ? 'A2A Spec' : 'MCP Spec'}
            </h2>
            {selectedProtocol === 'a2a' ? <A2ASpec /> : <MCPSpec />}
          </div>
        </div>
      </div>
    </div>
  );
}

// A2A Flow Diagram Component
function A2AFlowDiagram() {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-center gap-4">
        <FlowNode label="Client" icon={<MessageSquare className="w-5 h-5" />} />
        <ArrowRight className="w-6 h-6" style={{ color: 'var(--accent)' }} />
        <FlowNode label="Orchestrator" icon={<Workflow className="w-5 h-5" />} highlight />
        <ArrowRight className="w-6 h-6" style={{ color: 'var(--accent)' }} />
        <FlowNode label="Agent" icon={<Zap className="w-5 h-5" />} />
      </div>

      <div className="p-4 rounded-lg" style={{ background: 'var(--background)' }}>
        <h3 className="font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>JSON-RPC 2.0 Request</h3>
        <pre className="text-xs font-mono overflow-auto" style={{ color: 'var(--text-secondary)' }}>
{`{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tasks.send",
  "params": {
    "taskId": "task_123",
    "messages": [
      {
        "role": "user",
        "parts": [{"type": "text", "text": "..."}]
      }
    ]
  }
}`}
        </pre>
      </div>

      <div className="grid grid-cols-3 gap-3 text-sm">
        <InfoCard title="Async Tasks" value="Supported" icon={<Clock />} />
        <InfoCard title="Streaming" value="Enabled" icon={<Activity />} />
        <InfoCard title="Error Handling" value="Built-in" icon={<CheckCircle2 />} />
      </div>
    </div>
  );
}

// MCP Flow Diagram Component
function MCPFlowDiagram() {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-center gap-4">
        <FlowNode label="Client" icon={<MessageSquare className="w-5 h-5" />} />
        <ArrowRight className="w-6 h-6" style={{ color: 'var(--accent)' }} />
        <FlowNode label="MCP Server" icon={<Database className="w-5 h-5" />} highlight />
        <ArrowRight className="w-6 h-6" style={{ color: 'var(--accent)' }} />
        <FlowNode label="Resources" icon={<FileJson className="w-5 h-5" />} />
      </div>

      <div className="p-4 rounded-lg" style={{ background: 'var(--background)' }}>
        <h3 className="font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>MCP Tool Call</h3>
        <pre className="text-xs font-mono overflow-auto" style={{ color: 'var(--text-secondary)' }}>
{`{
  "method": "tools/call",
  "params": {
    "name": "get_brand_profile",
    "arguments": {
      "brand_id": 1
    }
  }
}`}
        </pre>
      </div>

      <div className="grid grid-cols-3 gap-3 text-sm">
        <InfoCard title="Tools" value="15+" icon={<Zap />} />
        <InfoCard title="Resources" value="Dynamic" icon={<Database />} />
        <InfoCard title="Prompts" value="Custom" icon={<MessageSquare />} />
      </div>
    </div>
  );
}

// Flow Node Component
interface FlowNodeProps {
  label: string;
  icon: React.ReactNode;
  highlight?: boolean;
}

function FlowNode({ label, icon, highlight }: FlowNodeProps) {
  return (
    <div
      className={`px-6 py-4 rounded-lg flex flex-col items-center gap-2 transition-all ${
        highlight ? 'shadow-lg' : ''
      }`}
      style={{
        background: highlight
          ? 'linear-gradient(135deg, var(--accent) 0%, var(--accent-dark) 100%)'
          : 'var(--surface-hover)',
        border: highlight ? '2px solid var(--accent)' : '2px solid var(--border)'
      }}
    >
      <div className={highlight ? 'text-white' : ''} style={{ color: highlight ? undefined : 'var(--accent)' }}>
        {icon}
      </div>
      <span className={`font-semibold text-sm ${highlight ? 'text-white' : ''}`} style={{ color: highlight ? undefined : 'var(--text-primary)' }}>
        {label}
      </span>
    </div>
  );
}

// Info Card Component
interface InfoCardProps {
  title: string;
  value: string;
  icon: React.ReactNode;
}

function InfoCard({ title, value, icon }: InfoCardProps) {
  return (
    <div className="p-3 rounded-lg" style={{ background: 'var(--background)' }}>
      <div className="flex items-center gap-2 mb-1" style={{ color: 'var(--text-secondary)' }}>
        <span className="w-4 h-4">{icon}</span>
        <span className="text-xs">{title}</span>
      </div>
      <div className="font-bold" style={{ color: 'var(--text-primary)' }}>
        {value}
      </div>
    </div>
  );
}

// A2A Specification Component
function A2ASpec() {
  return (
    <div className="space-y-3 text-sm" style={{ color: 'var(--text-secondary)' }}>
      <div>
        <h3 className="font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>Protocol</h3>
        <p>JSON-RPC 2.0 over HTTP</p>
      </div>
      <div>
        <h3 className="font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>Endpoints</h3>
        <ul className="space-y-1 font-mono text-xs">
          <li>POST /a2a</li>
          <li>GET /.well-known/agent.json</li>
          <li>GET /a2a/tasks/:id</li>
        </ul>
      </div>
      <div>
        <h3 className="font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>Methods</h3>
        <ul className="space-y-1">
          <li>• tasks.send</li>
          <li>• tasks.sendSubscribe</li>
          <li>• tasks.cancel</li>
          <li>• tasks.pushNotification.set</li>
          <li>• campaigns.propose</li>
          <li>• campaigns.accept</li>
        </ul>
      </div>
    </div>
  );
}

// MCP Specification Component
function MCPSpec() {
  return (
    <div className="space-y-3 text-sm" style={{ color: 'var(--text-secondary)' }}>
      <div>
        <h3 className="font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>Protocol</h3>
        <p>Model Context Protocol</p>
      </div>
      <div>
        <h3 className="font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>Endpoints</h3>
        <ul className="space-y-1 font-mono text-xs">
          <li>POST /mcp/initialize</li>
          <li>GET /mcp/tools/list</li>
          <li>POST /mcp/tools/call</li>
          <li>GET /mcp/resources/list</li>
        </ul>
      </div>
      <div>
        <h3 className="font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>Features</h3>
        <ul className="space-y-1">
          <li>• Dynamic tool discovery</li>
          <li>• Resource management</li>
          <li>• Prompt templates</li>
        </ul>
      </div>
    </div>
  );
}

