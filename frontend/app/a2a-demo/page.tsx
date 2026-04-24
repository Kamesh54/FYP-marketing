"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

const USER_AGENT_BASE = "http://127.0.0.1:8091";
const ORCHESTRATOR_BASE = "http://127.0.0.1:8004";

type StepState = "pending" | "completed" | "proposed" | "accepted" | "running" | "listening" | "failed";

type WorkflowRecord = {
  workflow_id: string;
  created_at: number;
  event: {
    product_id: string;
    product_name: string;
    description: string;
    category: string;
    tier: string;
    duration_days: number;
    request_kind?: "campaign" | "post" | "blog";
    platform?: string | null;
  };
  summary: string;
  generated_prompt?: string;
  generated_result?: any;
  dispatch_status?: string;
  error?: string;
  steps: {
    observer: StepState;
    content_creator: StepState;
    negotiation: StepState;
    execution: StepState;
    feedback: StepState;
  };
  orchestrator_task_id?: string | null;
  orchestrator_state?: string | null;
  campaign_result?: any;
  task_snapshot?: any;
};

function extractArtifact(workflow: WorkflowRecord | null, artifactName: string): any | null {
  const artifacts = workflow?.task_snapshot?.artifacts;
  if (!Array.isArray(artifacts)) return null;

  const artifact = artifacts.find((a: any) => a?.name === artifactName);
  const text = artifact?.parts?.[0]?.text;
  if (!text || typeof text !== "string") return null;

  try {
    return JSON.parse(text);
  } catch {
    return { raw: text };
  }
}

export default function A2ADemoPage() {
  const [productName, setProductName] = useState("RoadPro Carbon Helmet");
  const [description, setDescription] = useState("A lightweight cycling helmet with MIPS safety, reflective trim, and premium ventilation channels.");
  const [category, setCategory] = useState("cycling");
  const [tier, setTier] = useState("balanced");
  const [durationDays, setDurationDays] = useState(7);
  const [requestKind, setRequestKind] = useState<"campaign" | "post" | "blog">("campaign");
  const [platform, setPlatform] = useState("instagram");

  const [workflow, setWorkflow] = useState<WorkflowRecord | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [metrics, setMetrics] = useState<{ tracer?: any; mabo?: any }>({});

  const authToken = useMemo(() => {
    const token = typeof window !== "undefined" ? (localStorage.getItem("authToken") || localStorage.getItem("auth_token")) : "";
    return token || "";
  }, []);

  const proposalArtifact = useMemo(() => extractArtifact(workflow, "proposal"), [workflow]);
  const acceptanceArtifact = useMemo(() => extractArtifact(workflow, "response"), [workflow]);

  useEffect(() => {
    if (!workflow?.workflow_id) return;

    const interval = setInterval(async () => {
      try {
        const response = await fetch(`${USER_AGENT_BASE}/workflows/${workflow.workflow_id}`);
        if (!response.ok) return;
        const data = await response.json();
        setWorkflow(data);
      } catch {
        // Ignore transient polling errors.
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [workflow?.workflow_id]);

  useEffect(() => {
    if (!workflow?.campaign_result) return;

    const loadMetrics = async () => {
      try {
        const [tracerRes, maboRes] = await Promise.allSettled([
          fetch(`${ORCHESTRATOR_BASE}/tracer/status`, {
            headers: authToken ? { Authorization: `Bearer ${authToken}` } : undefined,
          }),
          fetch(`${ORCHESTRATOR_BASE}/mabo/stats`, {
            headers: authToken ? { Authorization: `Bearer ${authToken}` } : undefined,
          }),
        ]);

        const nextMetrics: { tracer?: any; mabo?: any } = {};
        if (tracerRes.status === "fulfilled" && tracerRes.value.ok) {
          nextMetrics.tracer = await tracerRes.value.json();
        }
        if (maboRes.status === "fulfilled" && maboRes.value.ok) {
          nextMetrics.mabo = await maboRes.value.json();
        }
        setMetrics(nextMetrics);
      } catch {
        // Keep demo resilient even if metrics APIs fail.
      }
    };

    loadMetrics();
  }, [workflow?.campaign_result, authToken]);

  const triggerProductAdded = async () => {
    setLoading("observer");
    setError(null);
    try {
      const response = await fetch(`${USER_AGENT_BASE}/events/product-added`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          product_id: `prd_${Date.now()}`,
          product_name: productName,
          description,
          category,
          tier,
          duration_days: durationDays,
          request_kind: requestKind,
          platform: requestKind === "post" ? platform : null,
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Observer failed");
      setWorkflow(data);
    } catch (e: any) {
      setError(e.message || "Failed to trigger Product_Added event");
    } finally {
      setLoading(null);
    }
  };

  const sendProposal = async () => {
    if (!workflow?.workflow_id) return;
    setLoading("proposal");
    setError(null);
    try {
      const response = await fetch(`${USER_AGENT_BASE}/workflows/${workflow.workflow_id}/propose`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Proposal failed");

      const refreshed = await fetch(`${USER_AGENT_BASE}/workflows/${workflow.workflow_id}`);
      setWorkflow(await refreshed.json());
    } catch (e: any) {
      setError(e.message || "Failed to send proposal");
    } finally {
      setLoading(null);
    }
  };

  const acceptAndExecute = async () => {
    if (!workflow?.workflow_id) return;
    setLoading("execute");
    setError(null);
    try {
      const response = await fetch(`${USER_AGENT_BASE}/workflows/${workflow.workflow_id}/accept`, {
        method: "POST",
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Execution failed");

      const refreshed = await fetch(`${USER_AGENT_BASE}/workflows/${workflow.workflow_id}`);
      setWorkflow(await refreshed.json());
    } catch (e: any) {
      setError(e.message || "Failed to execute campaign");
    } finally {
      setLoading(null);
    }
  };

  const stepClass = (state?: StepState) => {
    if (!state || state === "pending") return "bg-slate-700 text-slate-200";
    if (state === "failed") return "bg-red-700 text-red-100";
    if (state === "running" || state === "listening" || state === "proposed") return "bg-blue-700 text-blue-100";
    return "bg-emerald-700 text-emerald-100";
  };

  const lifecycleEntries = useMemo(() => {
    if (!workflow) return [] as Array<[string, StepState]>;
    const entries = Object.entries(workflow.steps) as Array<[string, StepState]>;
    if (workflow.event?.request_kind === "campaign") return entries;

    return entries.map(([name, state]) => {
      if (name === "negotiation") return ["dispatch", state] as [string, StepState];
      return [name, state] as [string, StepState];
    });
  }, [workflow]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-8">
      <div className="max-w-6xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">A2A External User-Agent Demo</h1>
            <p className="text-slate-300 mt-1">Observer -&gt; Summary -&gt; Proposal -&gt; Orchestrator Execution -&gt; Feedback Metrics</p>
          </div>
          <Link href="/protocols" className="text-cyan-300 hover:text-cyan-200 underline">Back to Protocols</Link>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-4">
            <h2 className="font-semibold text-xl">1) Trigger Product_Added</h2>
            <input className="w-full rounded bg-slate-800 p-2" value={productName} onChange={(e) => setProductName(e.target.value)} placeholder="Product name" />
            <textarea className="w-full rounded bg-slate-800 p-2 min-h-24" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Description" />
            <div className="grid grid-cols-3 gap-3">
              <input className="rounded bg-slate-800 p-2" value={category} onChange={(e) => setCategory(e.target.value)} placeholder="Category" />
              <select className="rounded bg-slate-800 p-2" value={tier} onChange={(e) => setTier(e.target.value)}>
                <option value="budget">budget</option>
                <option value="balanced">balanced</option>
                <option value="premium">premium</option>
              </select>
              <input className="rounded bg-slate-800 p-2" type="number" min={1} max={30} value={durationDays} onChange={(e) => setDurationDays(Number(e.target.value))} />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <select className="rounded bg-slate-800 p-2" value={requestKind} onChange={(e) => setRequestKind(e.target.value as "campaign" | "post" | "blog")}>
                <option value="campaign">campaign</option>
                <option value="post">post</option>
                <option value="blog">blog</option>
              </select>
              <select className="rounded bg-slate-800 p-2" value={platform} onChange={(e) => setPlatform(e.target.value)} disabled={requestKind !== "post"}>
                <option value="instagram">instagram</option>
                <option value="twitter">twitter</option>
              </select>
            </div>

            <div className="flex gap-2">
              <button className="px-4 py-2 rounded bg-cyan-700 hover:bg-cyan-600 disabled:opacity-50" disabled={loading !== null} onClick={triggerProductAdded}>
                {loading === "observer" ? "Observing..." : "Trigger Observer"}
              </button>
              <button className="px-4 py-2 rounded bg-blue-700 hover:bg-blue-600 disabled:opacity-50" disabled={!workflow || loading !== null || requestKind !== "campaign"} onClick={sendProposal}>
                {loading === "proposal" ? "Proposing..." : "Send Proposal"}
              </button>
              <button className="px-4 py-2 rounded bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50" disabled={!workflow?.orchestrator_task_id || loading !== null || requestKind !== "campaign"} onClick={acceptAndExecute}>
                {loading === "execute" ? "Executing..." : "Accept + Execute"}
              </button>
            </div>

            <p className="text-xs text-slate-400">
              Trigger Observer now auto-sends prompt to orchestrator. Manual Proposal/Accept is optional for campaign mode only.
            </p>

            {error && <p className="text-red-300 text-sm">{error}</p>}
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-4">
            <h2 className="font-semibold text-xl">2) Lifecycle</h2>
            {!workflow ? (
              <p className="text-slate-400">No workflow yet. Trigger Product_Added to start.</p>
            ) : (
              <>
                <p className="text-sm text-slate-300">Workflow ID: <span className="font-mono">{workflow.workflow_id}</span></p>
                <p className="text-sm text-slate-300">Orchestrator Task: <span className="font-mono">{workflow.orchestrator_task_id || "(pending)"}</span></p>
                <p className="text-sm text-slate-300">Dispatch: <span className="font-mono">{workflow.dispatch_status || "-"}</span></p>
                <div className="grid grid-cols-1 gap-2">
                  {lifecycleEntries.map(([name, state]) => (
                    <div key={name} className="flex items-center justify-between rounded bg-slate-800 px-3 py-2">
                      <span className="capitalize">{name.replace("_", " ")}</span>
                      <span className={`text-xs px-2 py-1 rounded ${stepClass(state)}`}>{state}</span>
                    </div>
                  ))}
                </div>
                <div className="text-sm text-slate-300">Orchestrator state: {workflow.orchestrator_state || "-"}</div>
                {workflow.error && <div className="text-sm text-red-300">Error: {workflow.error}</div>}
              </>
            )}
          </div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-3">
          <h2 className="font-semibold text-xl">3) Execution Result + Metrics Hook</h2>
          {workflow?.generated_prompt && (
            <div className="rounded bg-slate-800 p-3">
              <p className="text-sm font-semibold mb-1">Prompt Sent To Orchestrator</p>
              <pre className="text-xs overflow-auto">{workflow.generated_prompt}</pre>
            </div>
          )}

          {workflow?.generated_result && (
            <div className="rounded bg-slate-800 p-3">
              <p className="text-sm font-semibold mb-1">Generated Output (Post/Blog/Campaign)</p>
              <pre className="text-xs overflow-auto">{JSON.stringify(workflow.generated_result, null, 2)}</pre>
            </div>
          )}

          {proposalArtifact && (
            <div className="rounded bg-slate-800 p-3">
              <p className="text-sm font-semibold mb-1">Proposal From Orchestrator</p>
              <pre className="text-xs overflow-auto">{JSON.stringify(proposalArtifact, null, 2)}</pre>
            </div>
          )}

          {acceptanceArtifact && (
            <div className="rounded bg-slate-800 p-3">
              <p className="text-sm font-semibold mb-1">Acceptance Response</p>
              <pre className="text-xs overflow-auto">{JSON.stringify(acceptanceArtifact, null, 2)}</pre>
            </div>
          )}

          {!workflow?.campaign_result ? (
            <p className="text-slate-400">Campaign result appears after orchestration completes.</p>
          ) : (
            <>
              <pre className="text-xs bg-slate-950 rounded p-3 overflow-auto">{JSON.stringify(workflow.campaign_result, null, 2)}</pre>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="rounded bg-slate-800 p-3">
                  <p className="text-sm font-semibold mb-1">Tracer Status</p>
                  <pre className="text-xs overflow-auto">{JSON.stringify(metrics.tracer || {}, null, 2)}</pre>
                  {metrics.tracer && metrics.tracer.enabled === false && (
                    <p className="text-amber-300 text-xs mt-2">
                      Tracer is currently disabled, so campaign trace logs are not being recorded.
                    </p>
                  )}
                </div>
                <div className="rounded bg-slate-800 p-3">
                  <p className="text-sm font-semibold mb-1">MABO Stats</p>
                  <pre className="text-xs overflow-auto">{JSON.stringify(metrics.mabo || {}, null, 2)}</pre>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
