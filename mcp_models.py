"""
MCP (Model Context Protocol) Data Models
Implements the MCP specification for tool/resource/prompt definitions
"""
from typing import Any, Dict, List, Optional, Literal, Union
from pydantic import BaseModel, Field
from datetime import datetime


# ═══════════════════════════════════════════════════════════════════════════
# MCP Protocol Message Types
# ═══════════════════════════════════════════════════════════════════════════

class MCPRequest(BaseModel):
    """Base MCP JSON-RPC Request"""
    jsonrpc: str = "2.0"
    id: Union[str, int]
    method: str
    params: Optional[Dict[str, Any]] = None


class MCPResponse(BaseModel):
    """Base MCP JSON-RPC Response"""
    jsonrpc: str = "2.0"
    id: Union[str, int]
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None


class MCPNotification(BaseModel):
    """MCP Notification (no response expected)"""
    jsonrpc: str = "2.0"
    method: str
    params: Optional[Dict[str, Any]] = None


# ═══════════════════════════════════════════════════════════════════════════
# MCP Tool Definitions
# ═══════════════════════════════════════════════════════════════════════════

class MCPToolInputSchema(BaseModel):
    """JSON Schema for tool input parameters"""
    type: str = "object"
    properties: Dict[str, Any]
    required: Optional[List[str]] = None
    additionalProperties: Optional[bool] = False


class MCPTool(BaseModel):
    """MCP Tool Definition"""
    name: str
    description: str
    inputSchema: MCPToolInputSchema


class MCPToolCallRequest(BaseModel):
    """Request to call a tool"""
    name: str
    arguments: Dict[str, Any]


class MCPToolCallResult(BaseModel):
    """Result of tool execution"""
    content: List[Dict[str, Any]]  # Array of text/image/resource content
    isError: Optional[bool] = False


# ═══════════════════════════════════════════════════════════════════════════
# MCP Resource Definitions
# ═══════════════════════════════════════════════════════════════════════════

class MCPResource(BaseModel):
    """MCP Resource Definition"""
    uri: str
    name: str
    description: Optional[str] = None
    mimeType: Optional[str] = "application/json"


class MCPResourceContents(BaseModel):
    """Resource contents"""
    uri: str
    mimeType: str
    text: Optional[str] = None
    blob: Optional[str] = None  # Base64 encoded


# ═══════════════════════════════════════════════════════════════════════════
# MCP Prompt Definitions
# ═══════════════════════════════════════════════════════════════════════════

class MCPPromptArgument(BaseModel):
    """Prompt template argument"""
    name: str
    description: Optional[str] = None
    required: Optional[bool] = False


class MCPPrompt(BaseModel):
    """MCP Prompt Template"""
    name: str
    description: Optional[str] = None
    arguments: Optional[List[MCPPromptArgument]] = None


class MCPPromptMessage(BaseModel):
    """Message in a prompt"""
    role: Literal["user", "assistant"]
    content: Dict[str, Any]  # Text or image content


class MCPGetPromptResult(BaseModel):
    """Result of getting a prompt"""
    description: Optional[str] = None
    messages: List[MCPPromptMessage]


# ═══════════════════════════════════════════════════════════════════════════
# MCP Server Capabilities
# ═══════════════════════════════════════════════════════════════════════════

class MCPServerCapabilities(BaseModel):
    """Server capabilities declaration"""
    tools: Optional[Dict[str, Any]] = None
    resources: Optional[Dict[str, Any]] = None
    prompts: Optional[Dict[str, Any]] = None
    logging: Optional[Dict[str, Any]] = None


class MCPClientCapabilities(BaseModel):
    """Client capabilities"""
    roots: Optional[Dict[str, Any]] = None
    sampling: Optional[Dict[str, Any]] = None


class MCPImplementation(BaseModel):
    """Implementation details"""
    name: str
    version: str


class MCPInitializeParams(BaseModel):
    """Initialize request parameters"""
    protocolVersion: str
    capabilities: MCPClientCapabilities
    clientInfo: MCPImplementation


class MCPInitializeResult(BaseModel):
    """Initialize response"""
    protocolVersion: str
    capabilities: MCPServerCapabilities
    serverInfo: MCPImplementation

