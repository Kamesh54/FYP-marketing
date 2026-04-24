"use client";

import React, { useState, useEffect, useRef } from "react";
import { Activity, Clock, CheckCircle, XCircle, PlayCircle, Zap } from "lucide-react";

interface TraceEvent {
  trace_id: string;
  event_type: "start" | "progress" | "complete" | "error";
  node: string;
  timestamp: string;
  data: any;
}

interface TraceMetadata {
  trace_id: string;
  user_id: number;
  session_id: string;
  user_message: string;
  intent: string;
  workflow: string;
  start_time: string;
  end_time?: string;
  status: "running" | "success" | "error";
  duration_ms?: number;
  error?: string;
}

interface Trace {
  metadata: TraceMetadata;
  events: TraceEvent[];
}

export default function VisualizerPage() {
  const [traces, setTraces] = useState<TraceMetadata[]>([]);
  const [selectedTrace, setSelectedTrace] = useState<Trace | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    // Connect to WebSocket for real-time updates
    const ws = new WebSocket("ws://localhost:8004/ws/traces");
    
    ws.onopen = () => {
      console.log("WebSocket connected");
      setIsConnected(true);
    };

    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      console.log("WebSocket message:", message);

      if (message.type === "initial_traces") {
        setTraces(message.traces);
      } else if (message.type === "trace_start") {
        setTraces((prev) => [message.metadata, ...prev]);
      } else if (message.type === "trace_complete") {
        setTraces((prev) =>
          prev.map((t) =>
            t.trace_id === message.trace_id ? message.metadata : t
          )
        );
        // Update selected trace if it's the one that completed
        if (selectedTrace?.metadata.trace_id === message.trace_id) {
          setSelectedTrace((prev) => prev ? {
            ...prev,
            metadata: message.metadata
          } : null);
        }
      } else if (message.type === "node_event") {
        // Update selected trace with new event
        if (selectedTrace?.metadata.trace_id === message.trace_id) {
          setSelectedTrace((prev) => prev ? {
            ...prev,
            events: [...prev.events, message]
          } : null);
        }
      } else if (message.type === "trace_details") {
        setSelectedTrace({
          metadata: message.metadata,
          events: message.events
        });
      }
    };

    ws.onerror = (error) => {
      console.error("WebSocket error:", error);
      setIsConnected(false);
    };

    ws.onclose = () => {
      console.log("WebSocket disconnected");
      setIsConnected(false);
    };

    wsRef.current = ws;

    return () => {
      ws.close();
    };
  }, [selectedTrace]);

  const loadTraceDetails = (traceId: string) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(`get_trace:${traceId}`);
    } else {
      // Fallback to HTTP
      fetch(`http://localhost:8004/traces/${traceId}`)
        .then((res) => res.json())
        .then((data) => setSelectedTrace(data))
        .catch((err) => console.error("Failed to load trace:", err));
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "running":
        return <Activity className="w-4 h-4 text-blue-500 animate-pulse" />;
      case "success":
        return <CheckCircle className="w-4 h-4 text-green-500" />;
      case "error":
        return <XCircle className="w-4 h-4 text-red-500" />;
      default:
        return <Clock className="w-4 h-4 text-gray-500" />;
    }
  };

  const getNodeStatusColor = (eventType: string) => {
    switch (eventType) {
      case "start":
        return "bg-blue-500";
      case "progress":
        return "bg-yellow-500";
      case "complete":
        return "bg-green-500";
      case "error":
        return "bg-red-500";
      default:
        return "bg-gray-500";
    }
  };

  const agentSummary = React.useMemo(() => {
    if (!selectedTrace) return [] as Array<{ node: string; starts: number; completes: number; errors: number }>;

    const summary = new Map<string, { node: string; starts: number; completes: number; errors: number }>();
    for (const event of selectedTrace.events) {
      const node = event.node || "unknown";
      if (!summary.has(node)) {
        summary.set(node, { node, starts: 0, completes: 0, errors: 0 });
      }
      const item = summary.get(node)!;
      if (event.event_type === "start") item.starts += 1;
      if (event.event_type === "complete") item.completes += 1;
      if (event.event_type === "error") item.errors += 1;
    }

    return Array.from(summary.values());
  }, [selectedTrace]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 text-white p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold mb-2 flex items-center gap-3">
            <Zap className="w-10 h-10 text-yellow-400" />
            Agent Execution Visualizer
          </h1>
          <p className="text-gray-300">
            Real-time monitoring of agent workflows • LangGraph & A2A Protocol
          </p>
          <div className="mt-2 flex items-center gap-2">
            <div className={`w-3 h-3 rounded-full ${isConnected ? "bg-green-500" : "bg-red-500"}`}></div>
            <span className="text-sm">{isConnected ? "Connected" : "Disconnected"}</span>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-6">
          {/* Trace List */}
          <div className="col-span-1 bg-white/10 backdrop-blur-lg rounded-xl p-6 border border-white/20">
            <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
              <Activity className="w-5 h-5" />
              Recent Traces
            </h2>
            <div className="space-y-3 max-h-[calc(100vh-240px)] overflow-y-auto">
              {traces.length === 0 ? (
                <p className="text-gray-400 text-sm">No traces yet. Start a conversation to see execution traces.</p>
              ) : (
                traces.map((trace) => (
                  <div
                    key={trace.trace_id}
                    onClick={() => loadTraceDetails(trace.trace_id)}
                    className={`p-4 rounded-lg cursor-pointer transition-all border-2 ${
                      selectedTrace?.metadata.trace_id === trace.trace_id
                        ? "bg-purple-600/30 border-purple-400"
                        : "bg-white/5 border-transparent hover:bg-white/10"
                    }`}
                  >
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex items-center gap-2">
                        {getStatusIcon(trace.status)}
                        <span className="font-semibold text-sm">{trace.intent}</span>
                      </div>
                      {trace.duration_ms && (
                        <span className="text-xs text-gray-400">{trace.duration_ms}ms</span>
                      )}
                    </div>
                    <p className="text-xs text-gray-300 line-clamp-2 mb-2">{trace.user_message}</p>
                    <div className="flex items-center justify-between text-xs text-gray-400">
                      <span>{trace.workflow}</span>
                      <span>{new Date(trace.start_time).toLocaleTimeString()}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Flow Visualization */}
          <div className="col-span-2 bg-white/10 backdrop-blur-lg rounded-xl p-6 border border-white/20">
            <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
              <PlayCircle className="w-5 h-5" />
              Execution Flow
            </h2>

            {!selectedTrace ? (
              <div className="flex items-center justify-center h-96 text-gray-400">
                <p>Select a trace to view execution details</p>
              </div>
            ) : (
              <div className="space-y-6">
                {/* Metadata */}
                <div className="bg-black/20 rounded-lg p-4 border border-white/10">
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <span className="text-gray-400">Trace ID:</span>
                      <span className="ml-2 font-mono text-xs">{selectedTrace.metadata.trace_id}</span>
                    </div>
                    <div>
                      <span className="text-gray-400">Status:</span>
                      <span className="ml-2 flex items-center gap-1">
                        {getStatusIcon(selectedTrace.metadata.status)}
                        {selectedTrace.metadata.status}
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-400">Intent:</span>
                      <span className="ml-2 font-semibold">{selectedTrace.metadata.intent}</span>
                    </div>
                    <div>
                      <span className="text-gray-400">Workflow:</span>
                      <span className="ml-2">{selectedTrace.metadata.workflow}</span>
                    </div>
                    {selectedTrace.metadata.duration_ms && (
                      <div>
                        <span className="text-gray-400">Duration:</span>
                        <span className="ml-2 font-semibold">{selectedTrace.metadata.duration_ms}ms</span>
                      </div>
                    )}
                  </div>
                  <div className="mt-3 pt-3 border-t border-white/10">
                    <span className="text-gray-400 text-sm">Message:</span>
                    <p className="mt-1 text-sm">{selectedTrace.metadata.user_message}</p>
                  </div>
                  {selectedTrace.metadata.error && (
                    <div className="mt-3 pt-3 border-t border-red-500/30 bg-red-900/20 p-3 rounded">
                      <span className="text-red-400 text-sm font-semibold">Error:</span>
                      <p className="mt-1 text-sm text-red-300">{selectedTrace.metadata.error}</p>
                    </div>
                  )}
                </div>

                {/* Event Timeline */}
                <div className="bg-black/20 rounded-lg p-4 border border-white/10">
                  <h3 className="font-semibold mb-3 text-sm text-gray-300">Agents Ran</h3>
                  {agentSummary.length === 0 ? (
                    <p className="text-gray-400 text-sm">No agent/node events yet for this trace.</p>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      {agentSummary.map((agent) => (
                        <div key={agent.node} className="px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-xs">
                          <div className="font-semibold text-gray-100">{agent.node}</div>
                          <div className="text-gray-400 mt-1">
                            start: {agent.starts} | complete: {agent.completes} | error: {agent.errors}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="max-h-[calc(100vh-480px)] overflow-y-auto">
                  <h3 className="font-semibold mb-3 text-sm text-gray-300">Execution Timeline</h3>
                  {selectedTrace.events.length === 0 ? (
                    <p className="text-gray-400 text-sm">No events recorded yet...</p>
                  ) : (
                    <div className="space-y-3">
                      {selectedTrace.events.map((event, index) => (
                        <div key={index} className="flex gap-4">
                          {/* Timeline connector */}
                          <div className="flex flex-col items-center">
                            <div className={`w-3 h-3 rounded-full ${getNodeStatusColor(event.event_type)}`}></div>
                            {index < selectedTrace.events.length - 1 && (
                              <div className="w-0.5 h-full bg-gray-600 my-1"></div>
                            )}
                          </div>

                          {/* Event details */}
                          <div className="flex-1 bg-black/30 rounded-lg p-4 border border-white/10">
                            <div className="flex items-start justify-between mb-2">
                              <div>
                                <span className="font-semibold text-sm">{event.node} • {event.event_type}</span>
                                <span className={`ml-2 text-xs px-2 py-0.5 rounded ${
                                  event.event_type === "complete" ? "bg-green-500/20 text-green-300" :
                                  event.event_type === "error" ? "bg-red-500/20 text-red-300" :
                                  event.event_type === "start" ? "bg-blue-500/20 text-blue-300" :
                                  "bg-yellow-500/20 text-yellow-300"
                                }`}>
                                  {event.event_type}
                                </span>
                              </div>
                              <span className="text-xs text-gray-400">
                                {new Date(event.timestamp).toLocaleTimeString()}
                              </span>
                            </div>

                            {/* Event data */}
                            {Object.keys(event.data).length > 0 && (
                              <details className="mt-2">
                                <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-300">
                                  View Details
                                </summary>
                                <pre className="mt-2 text-xs bg-black/40 p-3 rounded overflow-x-auto">
                                  {JSON.stringify(event.data, null, 2)}
                                </pre>
                              </details>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

