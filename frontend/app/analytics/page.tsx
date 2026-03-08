"use client"

import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { ArrowLeft, BarChart3, Brain, Star, Zap, RefreshCw, ThumbsUp } from "lucide-react"
import Link from "next/link"

const ORCHESTRATOR = "http://127.0.0.1:8004"

interface MaboStats {
  agent_scores?: Record<string, number>
  total_runs?: number
  workflow_stats?: Record<string, { runs: number; avg_score: number }>
}

interface TracerStatus {
  enabled: boolean
  project?: string
  run_count?: number
}

function StatCard({ label, value, sub, icon }: { label: string; value: string | number; sub?: string; icon: React.ReactNode }) {
  return (
    <Card className="bg-gray-900 border-gray-700">
      <CardContent className="p-4 flex items-center gap-3">
        <div className="p-2 bg-gray-800 rounded-lg">{icon}</div>
        <div>
          <p className="text-2xl font-bold">{value}</p>
          <p className="text-sm text-gray-400">{label}</p>
          {sub && <p className="text-xs text-gray-600">{sub}</p>}
        </div>
      </CardContent>
    </Card>
  )
}

function ScoreBar({ label, score, max = 1 }: { label: string; score: number; max?: number }) {
  const pct = Math.round((score / max) * 100)
  const color = pct >= 70 ? "bg-green-500" : pct >= 40 ? "bg-yellow-500" : "bg-red-500"
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-gray-300">{label}</span>
        <span className="text-gray-400">{score.toFixed(3)}</span>
      </div>
      <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

export default function AnalyticsPage() {
  const [maboStats, setMaboStats] = useState<MaboStats | null>(null)
  const [tracerStatus, setTracerStatus] = useState<TracerStatus | null>(null)
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState("")

  // Social feedback form
  const [fbContentId, setFbContentId] = useState("")
  const [fbPlatform, setFbPlatform] = useState("instagram")
  const [fbReward, setFbReward] = useState("0.5")
  const [fbRunId, setFbRunId] = useState("")
  const [fbSending, setFbSending] = useState(false)

  // Prompt evolution form
  const [peAgent, setPeAgent] = useState("content_agent")
  const [peContext, setPeContext] = useState("blog")
  const [peFeedback, setPeFeedback] = useState("")
  const [peScore, setPeScore] = useState("0.65")
  const [peResult, setPeResult] = useState("")
  const [peSending, setPeSending] = useState(false)

  useEffect(() => { refresh() }, [])

  async function refresh() {
    setLoading(true)
    try {
      const [r1, r2] = await Promise.allSettled([
        fetch(`${ORCHESTRATOR}/mabo/stats`).then((r) => r.json()),
        fetch(`${ORCHESTRATOR}/tracer/status`).then((r) => r.json()),
      ])
      if (r1.status === "fulfilled") setMaboStats(r1.value)
      if (r2.status === "fulfilled") setTracerStatus(r2.value)
    } catch (_) {}
    setLoading(false)
  }

  async function sendFeedback() {
    if (!fbContentId) return
    setFbSending(true)
    setMsg("")
    try {
      const r = await fetch(`${ORCHESTRATOR}/feedback/social`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          content_id: fbContentId,
          platform: fbPlatform,
          reward: parseFloat(fbReward),
          langsmith_run_id: fbRunId || null,
        }),
      })
      if (r.ok) setMsg("Feedback recorded!")
      else setMsg("Failed: " + (await r.text()))
    } catch (e: any) {
      setMsg("Error: " + e.message)
    }
    setFbSending(false)
  }

  async function evolvePrompt() {
    if (!peFeedback) return
    setPeSending(true)
    setPeResult("")
    try {
      const r = await fetch(`${ORCHESTRATOR}/prompt/evolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          agent_name: peAgent,
          context_type: peContext,
          feedback: peFeedback,
          current_score: parseFloat(peScore),
        }),
      })
      const data = await r.json()
      setPeResult(data.new_prompt || JSON.stringify(data, null, 2))
    } catch (e: any) {
      setPeResult("Error: " + e.message)
    }
    setPeSending(false)
  }

  const agentScores = maboStats?.agent_scores || {}
  const workflowStats = maboStats?.workflow_stats || {}

  return (
    <div className="min-h-screen bg-gray-950 text-white p-6 overflow-y-auto">
      {/* Header */}
      <div className="flex items-center gap-4 mb-8">
        <Link href="/">
          <Button variant="ghost" size="sm"><ArrowLeft className="h-4 w-4 mr-1" />Back</Button>
        </Link>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <BarChart3 className="h-6 w-6 text-blue-400" />
          Analytics &amp; MABO
        </h1>
        <Button variant="ghost" size="sm" onClick={refresh} disabled={loading} className="ml-auto">
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
        </Button>
      </div>

      {msg && (
        <div className={`mb-4 px-4 py-2 rounded text-sm ${msg.includes("!") ? "bg-green-900 text-green-300" : "bg-red-900 text-red-300"}`}>
          {msg}
        </div>
      )}

      {/* Stat cards row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <StatCard label="Total Runs" value={maboStats?.total_runs ?? "–"} icon={<Zap className="h-5 w-5 text-yellow-400" />} />
        <StatCard label="Active Agents" value={Object.keys(agentScores).length} icon={<Brain className="h-5 w-5 text-purple-400" />} />
        <StatCard label="Workflows Tracked" value={Object.keys(workflowStats).length} icon={<BarChart3 className="h-5 w-5 text-blue-400" />} />
        <StatCard
          label="LangSmith Tracing"
          value={tracerStatus?.enabled ? "On" : "Off"}
          sub={tracerStatus?.project ? `Project: ${tracerStatus.project}` : undefined}
          icon={<Star className={`h-5 w-5 ${tracerStatus?.enabled ? "text-green-400" : "text-gray-600"}`} />}
        />
      </div>

      <div className="grid grid-cols-12 gap-6">
        {/* MABO agent scores */}
        <div className="col-span-5">
          <Card className="bg-gray-900 border-gray-700">
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Brain className="h-4 w-4 text-purple-400" />MABO Agent Scores
              </CardTitle>
              <CardDescription>Bandit arm scores for agent selection</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {Object.keys(agentScores).length === 0 ? (
                <p className="text-gray-500 text-sm">No data yet. Run some workflows to see scores.</p>
              ) : (
                Object.entries(agentScores).sort((a, b) => b[1] - a[1]).map(([agent, score]) => (
                  <ScoreBar key={agent} label={agent} score={score} />
                ))
              )}
            </CardContent>
          </Card>

          {/* Workflow stats */}
          {Object.keys(workflowStats).length > 0 && (
            <Card className="bg-gray-900 border-gray-700 mt-4">
              <CardHeader>
                <CardTitle className="text-base">Workflow Performance</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {Object.entries(workflowStats).map(([wf, stat]) => (
                    <div key={wf} className="flex items-center justify-between text-sm py-1 border-b border-gray-800 last:border-0">
                      <span className="text-gray-300 capitalize">{wf.replace(/_/g, " ")}</span>
                      <div className="flex items-center gap-3 text-xs text-gray-400">
                        <span>{stat.runs} runs</span>
                        <Badge variant="secondary">{(stat.avg_score * 100).toFixed(0)}% avg</Badge>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Right column */}
        <div className="col-span-7 space-y-5">
          {/* Social feedback form */}
          <Card className="bg-gray-900 border-gray-700">
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <ThumbsUp className="h-4 w-4 text-green-400" />Record Social Feedback
              </CardTitle>
              <CardDescription>Feed performance signals back into MABO and LangSmith</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label>Content ID</Label>
                  <Input value={fbContentId} onChange={(e) => setFbContentId(e.target.value)} placeholder="content_uuid" className="bg-gray-800 border-gray-600 font-mono text-sm" />
                </div>
                <div className="space-y-1">
                  <Label>Platform</Label>
                  <Select value={fbPlatform} onValueChange={setFbPlatform}>
                    <SelectTrigger className="bg-gray-800 border-gray-600"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {["instagram"].map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-1">
                <Label>Reward Score: <span className="text-purple-400 font-bold">{fbReward}</span></Label>
                <input
                  type="range" min="0" max="1" step="0.05"
                  value={fbReward}
                  onChange={(e) => setFbReward(e.target.value)}
                  className="w-full accent-purple-500"
                />
                <div className="flex justify-between text-xs text-gray-500">
                  <span>0.0 (poor)</span><span>0.5 (ok)</span><span>1.0 (excellent)</span>
                </div>
              </div>
              <div className="space-y-1">
                <Label>LangSmith Run ID <span className="text-gray-500">(optional)</span></Label>
                <Input value={fbRunId} onChange={(e) => setFbRunId(e.target.value)} placeholder="run_xxxxxx" className="bg-gray-800 border-gray-600 font-mono text-sm" />
              </div>
              <Button onClick={sendFeedback} disabled={fbSending || !fbContentId} className="bg-purple-600 hover:bg-purple-700">
                {fbSending ? "Sending…" : "Submit Feedback"}
              </Button>
            </CardContent>
          </Card>

          {/* Prompt evolution */}
          <Card className="bg-gray-900 border-gray-700">
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Zap className="h-4 w-4 text-yellow-400" />Evolve Prompt
              </CardTitle>
              <CardDescription>Trigger meta-prompt mutation to improve a specific agent's prompt</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label>Agent</Label>
                  <Select value={peAgent} onValueChange={setPeAgent}>
                    <SelectTrigger className="bg-gray-800 border-gray-600"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {["content_agent","seo_agent","research_agent","critic_agent"].map((a) => (
                        <SelectItem key={a} value={a}>{a}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label>Context</Label>
                  <Select value={peContext} onValueChange={setPeContext}>
                    <SelectTrigger className="bg-gray-800 border-gray-600"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {["blog","social_post","meta_description","synthesis","default"].map((c) => (
                        <SelectItem key={c} value={c}>{c}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-1">
                <Label>Feedback / Observations</Label>
                <textarea
                  value={peFeedback}
                  onChange={(e) => setPeFeedback(e.target.value)}
                  rows={3}
                  placeholder="e.g. The blog intros are too generic, need stronger hooks…"
                  className="w-full bg-gray-800 border border-gray-600 rounded-md px-3 py-2 text-sm text-white placeholder:text-gray-500 focus:outline-none focus:ring-1 focus:ring-purple-500"
                />
              </div>
              <div className="space-y-1">
                <Label>Current Score: <span className="text-yellow-400">{peScore}</span></Label>
                <input type="range" min="0" max="1" step="0.05" value={peScore} onChange={(e) => setPeScore(e.target.value)} className="w-full accent-yellow-500" />
              </div>
              <Button onClick={evolvePrompt} disabled={peSending || !peFeedback} className="bg-yellow-600 hover:bg-yellow-700 text-black font-medium">
                {peSending ? "Evolving…" : <><Zap className="h-4 w-4 mr-1" />Evolve Prompt</>}
              </Button>
              {peResult && (
                <div className="bg-gray-800 rounded p-3 text-sm text-gray-200 whitespace-pre-wrap font-mono max-h-48 overflow-y-auto border border-gray-700">
                  {peResult}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
