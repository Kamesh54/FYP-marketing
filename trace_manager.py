"""
Real-time execution tracing for agent workflows.
Streams execution events via WebSocket for live visualization.
"""
import asyncio
import json
import time
from typing import Dict, Any, List, Optional, Set
from datetime import datetime
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

class TraceEvent:
    """Individual trace event in the workflow execution."""
    def __init__(self, trace_id: str, event_type: str, node: str, data: Dict[str, Any]):
        self.trace_id = trace_id
        self.event_type = event_type  # 'start', 'progress', 'complete', 'error'
        self.node = node
        self.timestamp = datetime.utcnow().isoformat()
        self.data = data
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "event_type": self.event_type,
            "node": self.node,
            "timestamp": self.timestamp,
            "data": self.data
        }

class TraceManager:
    """Manages real-time execution traces and broadcasts to connected clients."""
    
    def __init__(self):
        self.active_traces: Dict[str, List[TraceEvent]] = {}
        self.trace_metadata: Dict[str, Dict[str, Any]] = {}
        self.websocket_connections: Dict[str, Set] = defaultdict(set)  # trace_id -> set of websockets
        self.all_connections: Set = set()  # clients listening to all traces
        
    def start_trace(self, trace_id: str, user_id: int, session_id: str,
                    user_message: str, intent: str, workflow: str) -> None:
        """Initialize a new trace session."""
        self.active_traces[trace_id] = []
        self.trace_metadata[trace_id] = {
            "trace_id": trace_id,
            "user_id": user_id,
            "session_id": session_id,
            "user_message": user_message,
            "intent": intent,
            "workflow": workflow,
            "start_time": datetime.utcnow().isoformat(),
            "status": "running"
        }
        logger.info(f"Started trace {trace_id} for intent={intent}, workflow={workflow}")

        # Broadcast trace start to all listeners (thread-safe)
        self._schedule_broadcast(trace_id, {
            "type": "trace_start",
            "trace_id": trace_id,
            "metadata": self.trace_metadata[trace_id]
        })
    
    def add_event(self, trace_id: str, event_type: str, node: str,
                  data: Dict[str, Any]) -> None:
        """Add an event to an active trace."""
        if trace_id not in self.active_traces:
            logger.warning(f"Trace {trace_id} not found, creating new trace")
            self.start_trace(trace_id, 0, "unknown", "unknown", "unknown", "unknown")

        event = TraceEvent(trace_id, event_type, node, data)
        self.active_traces[trace_id].append(event)

        # Broadcast event to connected clients (thread-safe)
        self._schedule_broadcast(trace_id, {
            "type": "node_event",
            "trace_id": trace_id,
            **event.to_dict()
        })
    
    def complete_trace(self, trace_id: str, success: bool = True,
                       error: Optional[str] = None) -> None:
        """Mark a trace as complete."""
        if trace_id in self.trace_metadata:
            self.trace_metadata[trace_id]["status"] = "success" if success else "error"
            self.trace_metadata[trace_id]["end_time"] = datetime.utcnow().isoformat()
            if error:
                self.trace_metadata[trace_id]["error"] = error

            # Calculate duration
            start = datetime.fromisoformat(self.trace_metadata[trace_id]["start_time"])
            end = datetime.fromisoformat(self.trace_metadata[trace_id]["end_time"])
            self.trace_metadata[trace_id]["duration_ms"] = int((end - start).total_seconds() * 1000)

            logger.info(f"Completed trace {trace_id}: {self.trace_metadata[trace_id]['status']}")

            # Broadcast completion (thread-safe)
            self._schedule_broadcast(trace_id, {
                "type": "trace_complete",
                "trace_id": trace_id,
                "metadata": self.trace_metadata[trace_id]
            })
    
    async def _broadcast_event(self, trace_id: str, event: Dict[str, Any]) -> None:
        """Broadcast event to all connected WebSocket clients."""
        # Send to clients listening to this specific trace
        disconnected = set()
        for ws in self.websocket_connections.get(trace_id, set()):
            try:
                await ws.send_json(event)
            except Exception as e:
                logger.warning(f"Failed to send to websocket: {e}")
                disconnected.add(ws)
        
        # Send to clients listening to all traces
        for ws in self.all_connections:
            try:
                await ws.send_json(event)
            except Exception as e:
                logger.warning(f"Failed to send to websocket: {e}")
                disconnected.add(ws)
        
        # Clean up disconnected clients
        for ws in disconnected:
            self._remove_connection(ws)
    
    def add_connection(self, websocket, trace_id: Optional[str] = None) -> None:
        """Register a WebSocket connection for trace updates."""
        if trace_id:
            self.websocket_connections[trace_id].add(websocket)
            logger.info(f"WebSocket connected to trace {trace_id}")
        else:
            self.all_connections.add(websocket)
            logger.info("WebSocket connected to all traces")
    
    def _remove_connection(self, websocket) -> None:
        """Remove a WebSocket connection."""
        self.all_connections.discard(websocket)
        for connections in self.websocket_connections.values():
            connections.discard(websocket)

    def _schedule_broadcast(self, trace_id: str, message: Dict[str, Any]) -> None:
        """Schedule a broadcast event (safe to call from sync code)."""
        try:
            # Try to get the running event loop
            loop = asyncio.get_running_loop()
            # Schedule the coroutine in the running loop
            asyncio.create_task(self._broadcast_event(trace_id, message))
        except RuntimeError:
            # No event loop running, skip broadcast (will be polled via HTTP)
            pass

    def get_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """Schedule a broadcast event (safe to call from sync code)."""
        try:
            # Try to get the running event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Schedule the coroutine in the running loop
                asyncio.create_task(self._broadcast_event(trace_id, message))
            else:
                # No running loop, skip broadcast (will be polled via HTTP)
                pass
        except RuntimeError:
            # No event loop at all, skip broadcast
            pass

    def get_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve complete trace data."""
        if trace_id not in self.active_traces:
            return None
        
        return {
            "metadata": self.trace_metadata.get(trace_id, {}),
            "events": [e.to_dict() for e in self.active_traces[trace_id]]
        }
    
    def get_recent_traces(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent trace metadata."""
        traces = sorted(
            self.trace_metadata.values(),
            key=lambda x: x.get("start_time", ""),
            reverse=True
        )
        return traces[:limit]

# Global singleton instance
_trace_manager = TraceManager()

def get_trace_manager() -> TraceManager:
    """Get the global trace manager instance."""
    return _trace_manager

