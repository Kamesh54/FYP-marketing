"""
A2A (Agent-to-Agent) Protocol Models
Pydantic models for Google A2A JSON-RPC interoperability.
"""
import enum
import os
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────────────────────

class TaskStatusEnum(str, enum.Enum):
    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input_required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


# ── Part / Message / Artifact ─────────────────────────────────────────────────

class FilePart(BaseModel):
    name: str = ""
    mimeType: str = "application/octet-stream"
    bytes: str = ""  # base64-encoded


class A2APart(BaseModel):
    type: str = "text"  # "text" | "file"
    text: Optional[str] = None
    file: Optional[FilePart] = None


class A2AMessage(BaseModel):
    role: str = "user"  # "user" | "agent"
    parts: List[A2APart] = []


class A2AArtifact(BaseModel):
    name: str = ""
    parts: List[A2APart] = []


# ── Task ──────────────────────────────────────────────────────────────────────

class A2ATaskStatus(BaseModel):
    state: TaskStatusEnum = TaskStatusEnum.SUBMITTED
    message: Optional[str] = None


class A2ATask(BaseModel):
    id: str
    status: A2ATaskStatus = A2ATaskStatus()
    messages: List[A2AMessage] = []
    artifacts: List[A2AArtifact] = []
    metadata: Dict[str, Any] = {}


# ── JSON-RPC ──────────────────────────────────────────────────────────────────

class A2AJsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: Any = None
    method: str
    params: Dict[str, Any] = {}


class A2AJsonRpcError(BaseModel):
    code: int
    message: str
    data: Optional[Any] = None


class A2AJsonRpcResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: Any = None
    result: Optional[Any] = None
    error: Optional[A2AJsonRpcError] = None


# ── SSE Events ────────────────────────────────────────────────────────────────

class TaskStatusUpdateEvent(BaseModel):
    type: str = "status"
    taskId: str
    status: A2ATaskStatus


class TaskArtifactUpdateEvent(BaseModel):
    type: str = "artifact"
    taskId: str
    artifact: A2AArtifact


# ── Agent Card ────────────────────────────────────────────────────────────────

class AgentCardAuthentication(BaseModel):
    schemes: List[str] = ["bearer"]
    description: str = "JWT Bearer token (same as /chat endpoint)"


class AgentCardCapability(BaseModel):
    method: str
    description: str = ""


class AgentCard(BaseModel):
    name: str = "FYP Orchestrator"
    description: str = "Multi-agent marketing platform with SEO, content generation, social media, and campaign planning capabilities."
    a2aVersion: str = "0.1"
    a2aEndpointUrl: str = ""
    authentication: AgentCardAuthentication = AgentCardAuthentication()
    capabilities: List[AgentCardCapability] = [
        AgentCardCapability(method="tasks.send", description="Submit a task and receive the result when complete"),
        AgentCardCapability(method="tasks.sendSubscribe", description="Submit a task and receive SSE updates"),
        AgentCardCapability(method="tasks.cancel", description="Cancel a running task"),
        AgentCardCapability(method="tasks.pushNotification.set", description="Register a webhook for task updates"),
        AgentCardCapability(method="campaigns.propose", description="Submit a campaign proposal for orchestrator review"),
        AgentCardCapability(method="campaigns.accept", description="Accept a proposed campaign and start execution"),
    ]

    @classmethod
    def build(cls, host: str = "") -> "AgentCard":
        """Build an AgentCard with the correct endpoint URL."""
        if not host:
            host = os.getenv("A2A_HOST", "http://localhost:8080")
        return cls(a2aEndpointUrl=f"{host}/a2a")
