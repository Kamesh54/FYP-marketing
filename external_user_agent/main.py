import asyncio
import json
import os
import time
import uuid
from typing import Any, Dict, Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

ORCHESTRATOR_BASE_URL = os.getenv("ORCHESTRATOR_BASE_URL", "http://127.0.0.1:8004").rstrip("/")
ORCHESTRATOR_EMAIL = os.getenv("ORCHESTRATOR_EMAIL", "")
ORCHESTRATOR_PASSWORD = os.getenv("ORCHESTRATOR_PASSWORD", "")
ORCHESTRATOR_BRAND = os.getenv("ORCHESTRATOR_BRAND", "")
ORCHESTRATOR_DEMO_EMAIL = os.getenv("ORCHESTRATOR_DEMO_EMAIL", "a2a_demo_user@example.com")
ORCHESTRATOR_DEMO_PASSWORD = os.getenv("ORCHESTRATOR_DEMO_PASSWORD", "Aa123456")

app = FastAPI(title="External User Agent", version="0.1.0")

# Allow the local frontend dev server to call this API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_workflows: Dict[str, Dict[str, Any]] = {}
_token_cache: Dict[str, Any] = {"token": None, "expires_at": 0}


class ProductAddedEvent(BaseModel):
    product_id: str
    product_name: str
    description: str
    category: str = "general"
    tier: str = Field(default="balanced", pattern="^(budget|balanced|premium)$")
    duration_days: int = 7
    request_kind: str = Field(default="campaign", pattern="^(campaign|post|blog)$")
    platform: Optional[str] = None


class ProposalRequest(BaseModel):
    budget_guardrail: Optional[float] = None


async def _get_token() -> str:
    now = time.time()
    if _token_cache.get("token") and _token_cache.get("expires_at", 0) > now + 60:
        return _token_cache["token"]

    email = ORCHESTRATOR_EMAIL
    password = ORCHESTRATOR_PASSWORD

    # Demo fallback: if credentials are not configured, bootstrap a local account.
    if not email or not password:
        email = ORCHESTRATOR_DEMO_EMAIL
        password = ORCHESTRATOR_DEMO_PASSWORD

        async with httpx.AsyncClient(timeout=20) as client:
            signup_response = await client.post(
                f"{ORCHESTRATOR_BASE_URL}/auth/signup",
                json={
                    "email": email,
                    "password": password,
                    "full_name": "A2A Demo User",
                },
            )
            # If the account already exists, signup can fail; login below is authoritative.
            if signup_response.status_code not in {200, 400, 409}:
                raise HTTPException(
                    status_code=500,
                    detail=f"Unable to bootstrap demo account: {signup_response.text}",
                )

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{ORCHESTRATOR_BASE_URL}/auth/login",
            json={"email": email, "password": password},
        )
        if response.status_code != 200:
            raise HTTPException(status_code=401, detail=f"Orchestrator login failed: {response.text}")

        data = response.json()
        token = data.get("token")
        if not token:
            raise HTTPException(status_code=401, detail="Orchestrator login returned no token")

        expires_at = now + 6 * 24 * 3600
        _token_cache["token"] = token
        _token_cache["expires_at"] = expires_at
        return token


async def _a2a_rpc(method: str, params: Dict[str, Any]) -> Dict[str, Any]:
    token = await _get_token()
    payload = {
        "jsonrpc": "2.0",
        "id": int(time.time() * 1000),
        "method": method,
        "params": params,
    }
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.post(
            f"{ORCHESTRATOR_BASE_URL}/a2a",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=f"A2A RPC failed: {response.text}")
        data = response.json()
        if data.get("error"):
            raise HTTPException(status_code=400, detail=f"A2A error: {data['error'].get('message')}")
        return data


async def _orchestrator_chat(message: str, platform: Optional[str] = None, intent: Optional[str] = None) -> Dict[str, Any]:
    token = await _get_token()
    payload: Dict[str, Any] = {
        "message": message,
        "active_brand": ORCHESTRATOR_BRAND or None,
    }
    if platform:
        payload["platform"] = platform
    if intent:
        payload["intent"] = intent

    last_error: Optional[str] = None
    for _ in range(1):
        try:
            async with httpx.AsyncClient(timeout=75) as client:
                response = await client.post(
                    f"{ORCHESTRATOR_BASE_URL}/chat",
                    json=payload,
                    headers={"Authorization": f"Bearer {token}"},
                )
                if response.status_code != 200:
                    last_error = f"Chat failed: {response.status_code} {response.text}"
                    continue
                return response.json()
        except Exception as exc:
            last_error = str(exc) or repr(exc)

    raise HTTPException(status_code=502, detail=last_error or "Chat request failed")


async def _get_task(task_id: str) -> Dict[str, Any]:
    token = await _get_token()
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            f"{ORCHESTRATOR_BASE_URL}/a2a/tasks/{task_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=f"Task lookup failed: {response.text}")
        return response.json()


async def _watch_execution(workflow_id: str) -> None:
    workflow = _workflows.get(workflow_id)
    if not workflow or not workflow.get("orchestrator_task_id"):
        return

    task_id = workflow["orchestrator_task_id"]
    for _ in range(90):
        task = await _get_task(task_id)
        state = task.get("status", {}).get("state", "submitted")
        workflow["orchestrator_state"] = state

        if state in {"completed", "failed", "canceled"}:
            workflow["steps"]["execution"] = "completed" if state == "completed" else "failed"
            workflow["steps"]["feedback"] = "completed" if state == "completed" else "failed"
            workflow["completed_at"] = time.time()
            workflow["task_snapshot"] = task

            if state == "completed":
                campaign_info = None
                for artifact in task.get("artifacts", []):
                    if artifact.get("name") == "campaign_execution":
                        parts = artifact.get("parts", [])
                        if parts and parts[0].get("type") == "text":
                            try:
                                campaign_info = json.loads(parts[0].get("text", "{}"))
                            except json.JSONDecodeError:
                                campaign_info = {"raw": parts[0].get("text", "")}
                            break
                workflow["campaign_result"] = campaign_info or {}
            return

        await asyncio.sleep(2)


def _build_summary(event: ProductAddedEvent) -> str:
    return (
        f"Product Added: {event.product_name}. "
        f"Category: {event.category}. "
        f"Description: {event.description[:240]}"
    )


def _build_prompt(event: ProductAddedEvent, summary: str) -> str:
    if event.request_kind == "post":
        channel = (event.platform or "instagram").lower()
        return (
            f"Create a high-converting {channel} post for product {event.product_name}. "
            f"Category: {event.category}. Details: {event.description}. "
            "Return caption-ready content and include image idea guidance."
        )

    if event.request_kind == "blog":
        return (
            f"Generate an SEO blog article in HTML for {event.product_name}. "
            f"Category: {event.category}. Context: {event.description}. "
            "Include clear headings, persuasive CTA, and publish-ready structure."
        )

    return (
        f"Create a {event.tier} campaign plan for {event.product_name} over {event.duration_days} days. "
        f"Category: {event.category}. Context: {summary}."
    )


async def _auto_dispatch(workflow_id: str) -> None:
    workflow = _workflows.get(workflow_id)
    if not workflow:
        return

    event = ProductAddedEvent(**workflow["event"])
    workflow["dispatch_status"] = "running"

    try:
        if event.request_kind == "campaign":
            proposal = {
                "theme": event.product_name,
                "tier": event.tier,
                "duration_days": event.duration_days,
                "summary": workflow["summary"],
                "budget_guardrail": None,
            }
            result = await _a2a_rpc(
                "campaigns.propose",
                {
                    "taskId": f"prop_{uuid.uuid4().hex[:12]}",
                    "proposal": proposal,
                    "metadata": {
                        "source": "external_user_agent",
                        "brand": ORCHESTRATOR_BRAND,
                        "workflow_id": workflow_id,
                    },
                },
            )

            task = result.get("result", {})
            workflow["orchestrator_task_id"] = task.get("id")
            workflow["orchestrator_state"] = task.get("status", {}).get("state")
            workflow["steps"]["negotiation"] = "proposed"

            await _a2a_rpc("campaigns.accept", {"taskId": workflow["orchestrator_task_id"], "async": True})
            workflow["steps"]["negotiation"] = "accepted"
            workflow["steps"]["execution"] = "running"
            workflow["steps"]["feedback"] = "listening"
            workflow["dispatch_status"] = "completed"

            asyncio.create_task(_watch_execution(workflow_id))
            return

        workflow["steps"]["negotiation"] = "completed"
        workflow["steps"]["execution"] = "running"
        workflow["steps"]["feedback"] = "listening"
        forced_intent = "social_post" if event.request_kind == "post" else "blog_generation"
        chat_result = await asyncio.wait_for(
            _orchestrator_chat(
                workflow["generated_prompt"],
                platform=event.platform,
                intent=forced_intent,
            ),
            timeout=90,
        )
        workflow["generated_result"] = chat_result
        workflow["orchestrator_state"] = "completed"
        workflow["steps"]["negotiation"] = "completed"
        workflow["steps"]["execution"] = "completed"
        workflow["steps"]["feedback"] = "completed"
        workflow["dispatch_status"] = "completed"
    except Exception as exc:
        workflow["dispatch_status"] = "failed"
        workflow["orchestrator_state"] = "failed"
        workflow["steps"]["negotiation"] = "completed" if event.request_kind != "campaign" else workflow["steps"]["negotiation"]
        workflow["steps"]["execution"] = "failed"
        workflow["steps"]["feedback"] = "failed"
        if isinstance(exc, asyncio.TimeoutError):
            workflow["error"] = "Orchestrator chat timed out after 90s (likely upstream LLM rate-limit stall)."
        else:
            workflow["error"] = str(exc) or repr(exc)


@app.get("/")
async def root() -> Dict[str, Any]:
    return {
        "service": "external-user-agent",
        "status": "running",
        "capabilities": [
            "observe_product_added",
            "create_summary",
            "a2a_campaign_proposal",
            "execution_feedback_loop",
        ],
    }


@app.post("/events/product-added")
async def product_added(event: ProductAddedEvent) -> Dict[str, Any]:
    workflow_id = f"ua_{uuid.uuid4().hex[:10]}"
    summary = _build_summary(event)
    prompt = _build_prompt(event, summary)

    _workflows[workflow_id] = {
        "workflow_id": workflow_id,
        "created_at": time.time(),
        "event": event.model_dump(),
        "summary": summary,
        "generated_prompt": prompt,
        "generated_result": None,
        "dispatch_status": "queued",
        "steps": {
            "observer": "completed",
            "content_creator": "completed",
            "negotiation": "pending",
            "execution": "pending",
            "feedback": "pending",
        },
        "orchestrator_task_id": None,
        "orchestrator_state": None,
        "campaign_result": None,
        "task_snapshot": None,
    }

    asyncio.create_task(_auto_dispatch(workflow_id))

    return _workflows[workflow_id]


@app.post("/workflows/{workflow_id}/propose")
async def send_proposal(workflow_id: str, req: ProposalRequest) -> Dict[str, Any]:
    workflow = _workflows.get(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    event = workflow["event"]
    proposal = {
        "theme": event["product_name"],
        "tier": event["tier"],
        "duration_days": event["duration_days"],
        "summary": workflow["summary"],
        "budget_guardrail": req.budget_guardrail,
    }

    result = await _a2a_rpc(
        "campaigns.propose",
        {
            "taskId": f"prop_{uuid.uuid4().hex[:12]}",
            "proposal": proposal,
            "metadata": {
                "source": "external_user_agent",
                "brand": ORCHESTRATOR_BRAND,
                "workflow_id": workflow_id,
            },
        },
    )

    task = result.get("result", {})
    workflow["orchestrator_task_id"] = task.get("id")
    workflow["orchestrator_state"] = task.get("status", {}).get("state")
    workflow["steps"]["negotiation"] = "proposed"

    return {
        "workflow_id": workflow_id,
        "proposal_status": "proposed",
        "orchestrator_task_id": workflow["orchestrator_task_id"],
    }


@app.post("/workflows/{workflow_id}/accept")
async def accept_and_execute(workflow_id: str) -> Dict[str, Any]:
    workflow = _workflows.get(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if not workflow.get("orchestrator_task_id"):
        raise HTTPException(status_code=400, detail="Proposal not sent yet")

    task_id = workflow["orchestrator_task_id"]
    await _a2a_rpc("campaigns.accept", {"taskId": task_id, "async": True})

    workflow["steps"]["negotiation"] = "accepted"
    workflow["steps"]["execution"] = "running"
    workflow["steps"]["feedback"] = "listening"

    asyncio.create_task(_watch_execution(workflow_id))

    return {
        "workflow_id": workflow_id,
        "execution": "started",
        "orchestrator_task_id": task_id,
    }


@app.get("/workflows/{workflow_id}")
async def get_workflow(workflow_id: str) -> Dict[str, Any]:
    workflow = _workflows.get(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    if workflow.get("orchestrator_task_id") and workflow.get("steps", {}).get("execution") in {"running", "pending"}:
        task = await _get_task(workflow["orchestrator_task_id"])
        workflow["orchestrator_state"] = task.get("status", {}).get("state")
        workflow["task_snapshot"] = task

    return workflow


@app.get("/workflows")
async def list_workflows() -> Dict[str, Any]:
    return {
        "count": len(_workflows),
        "workflows": sorted(_workflows.values(), key=lambda x: x.get("created_at", 0), reverse=True),
    }
