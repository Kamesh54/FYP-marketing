"use client"

import { useState, useEffect, useCallback } from "react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Zap, RefreshCw, ChevronDown, ChevronUp, ArrowLeft, TrendingUp, TrendingDown, Minus } from "lucide-react"
import Link from "next/link"

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface PromptVersion {
  id: string
  agent_name: string
  context_type: string
  prompt_text: string
  performance_score: number | null
  use_count: number
  created_at: string
  updated_at: string
}

interface PromptExecution {
  execution_id: string
  prompt_id?: string
  agent_name: string
  context_type: string
  brand_info: {
    brand_name?: string
    brand_positioning?: string
    target_audience?: string
    key_products?: string[]
    tone_guidelines?: string
    [key: string]: any
  }
  performance_score?: number
  quality_score?: number
  brand_alignment_score?: number
  overall_score?: number
  feedback?: string
  execution_time?: number
  created_at: string
}

interface AgentKey {
  agent_name: string
  context_type: string
}

interface LogData {
  templates: PromptVersion[]
  total_templates: number
  executions: PromptExecution[]
  total_executions: number
  agents: AgentKey[]
  error?: string
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function scoreColor(s: number | null): string {
  if (s === null) return "rgba(120,120,140,1)"
  if (s >= 0.8) return "#22c55e"
  if (s >= 0.6) return "#f59e0b"
  return "#ef4444"
}

function scoreLabel(s: number | null): string {
  if (s === null) return "pending"
  if (s >= 0.8) return "good"
  if (s >= 0.6) return "fair"
  return "poor"
}

function agentBadgeColor(a: string): string {
  const map: Record<string, string> = {
    content_agent: "rgba(99,102,241,0.25)",
    seo_agent:     "rgba(16,185,129,0.25)",
    research_agent:"rgba(245,158,11,0.25)",
  }
  return map[a] ?? "rgba(100,100,120,0.2)"
}

function contextBadgeColor(c: string): string {
  const map: Record<string, string> = {
    blog:             "rgba(139,92,246,0.25)",
    social_post:      "rgba(236,72,153,0.25)",
    meta_description: "rgba(59,130,246,0.25)",
    synthesis:        "rgba(245,158,11,0.25)",
  }
  return map[c] ?? "rgba(100,100,120,0.2)"
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const s = Math.floor(diff / 1000)
  if (s < 60)  return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

// ─────────────────────────────────────────────────────────────────────────────
// Score trend indicator between consecutive versions of same agent/context
// ─────────────────────────────────────────────────────────────────────────────
function TrendIcon({ prev, curr }: { prev: number | null; curr: number | null }) {
  if (prev === null || curr === null) return <Minus className="w-3 h-3" style={{ color: "rgba(120,120,140,1)" }} />
  const delta = curr - prev
  if (delta >  0.02) return <TrendingUp   className="w-3 h-3" style={{ color: "#22c55e" }} />
  if (delta < -0.02) return <TrendingDown  className="w-3 h-3" style={{ color: "#ef4444" }} />
  return <Minus className="w-3 h-3" style={{ color: "#f59e0b" }} />
}

// ─────────────────────────────────────────────────────────────────────────────
// Score bar
// ─────────────────────────────────────────────────────────────────────────────
function ScoreBar({ score }: { score: number | null }) {
  const pct = score !== null ? Math.round(score * 100) : 0
  return (
    <div className="flex items-center gap-2 min-w-[120px]">
      <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: "rgba(var(--surface), 0.6)" }}>
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${pct}%`, background: scoreColor(score) }}
        />
      </div>
      <span className="text-xs font-mono font-semibold tabular-nums" style={{ color: scoreColor(score), minWidth: 32 }}>
        {score !== null ? `${pct}%` : "–"}
      </span>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Execution row - Shows prompt execution with brand context
// ─────────────────────────────────────────────────────────────────────────────
function ExecutionRow({ exec }: { exec: PromptExecution }) {
  const [expanded, setExpanded] = useState(false)
  const brandInfo = exec.brand_info || {}
  const overallScore = exec.overall_score ?? exec.performance_score ?? null

  return (
    <div
      className="rounded-lg border overflow-hidden cursor-pointer transition-colors"
      onClick={() => setExpanded(!expanded)}
      style={{
        borderColor: "rgba(var(--border), 0.3)",
        background: expanded ? "rgba(var(--surface), 0.5)" : "rgba(var(--surface), 0.2)",
      }}
    >
      {/* Header */}
      <div className="px-4 py-3 flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <div
              className="px-2 py-1 rounded text-xs font-medium"
              style={{
                background: agentBadgeColor(exec.agent_name),
                color: "rgba(var(--text-primary), 0.9)",
              }}
            >
              {exec.agent_name}
            </div>
            <div
              className="px-2 py-1 rounded text-xs font-medium"
              style={{
                background: contextBadgeColor(exec.context_type),
                color: "rgba(var(--text-primary), 0.9)",
              }}
            >
              {exec.context_type}
            </div>
          </div>

          {/* Brand Info */}
          <div className="space-y-1">
            <p className="font-semibold text-sm" style={{ color: "rgba(var(--text-primary), 1)" }}>
              🏢 {brandInfo.brand_name || "Unknown Brand"}
            </p>
            {brandInfo.brand_positioning && (
              <p className="text-xs line-clamp-1" style={{ color: "rgba(var(--text-secondary), 0.8)" }}>
                {brandInfo.brand_positioning}
              </p>
            )}
            {brandInfo.target_audience && (
              <p className="text-xs line-clamp-1" style={{ color: "rgba(var(--text-secondary), 0.7)" }}>
                👥 {brandInfo.target_audience}
              </p>
            )}
            {brandInfo.key_products && brandInfo.key_products.length > 0 && (
              <p className="text-xs line-clamp-1" style={{ color: "rgba(var(--text-secondary), 0.7)" }}>
                📦 {brandInfo.key_products.join(", ")}
              </p>
            )}
          </div>
        </div>

        {/* Score */}
        <div className="flex flex-col items-end gap-2 flex-shrink-0">
          <div className="text-lg font-bold" style={{ color: scoreColor(overallScore) }}>
            {overallScore !== null ? `${(overallScore * 100).toFixed(0)}%` : "—"}
          </div>
          <p className="text-xs" style={{ color: "rgba(var(--text-secondary), 0.5)" }}>
            {relativeTime(exec.created_at)}
          </p>
          {expanded ? (
            <ChevronUp className="w-4 h-4" style={{ color: "rgba(var(--secondary), 1)" }} />
          ) : (
            <ChevronDown className="w-4 h-4" style={{ color: "rgba(var(--text-secondary), 0.4)" }} />
          )}
        </div>
      </div>

      {/* Details */}
      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t" style={{ borderColor: "rgba(var(--border), 0.2)" }}>
          <div className="pt-3 grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
            {exec.quality_score !== undefined && (
              <div>
                <p style={{ color: "rgba(var(--text-secondary), 0.6)" }}>Quality</p>
                <p className="font-semibold" style={{ color: scoreColor(exec.quality_score) }}>
                  {(exec.quality_score * 100).toFixed(0)}%
                </p>
              </div>
            )}
            {exec.brand_alignment_score !== undefined && (
              <div>
                <p style={{ color: "rgba(var(--text-secondary), 0.6)" }}>Brand Align</p>
                <p className="font-semibold" style={{ color: scoreColor(exec.brand_alignment_score) }}>
                  {(exec.brand_alignment_score * 100).toFixed(0)}%
                </p>
              </div>
            )}
            {exec.execution_time !== undefined && (
              <div>
                <p style={{ color: "rgba(var(--text-secondary), 0.6)" }}>Duration</p>
                <p className="font-semibold text-blue-500">{exec.execution_time.toFixed(1)}s</p>
              </div>
            )}
            {exec.overall_score !== undefined && (
              <div>
                <p style={{ color: "rgba(var(--text-secondary), 0.6)" }}>Overall</p>
                <p className="font-semibold" style={{ color: scoreColor(exec.overall_score) }}>
                  {(exec.overall_score * 100).toFixed(0)}%
                </p>
              </div>
            )}
          </div>

          {exec.feedback && (
            <div style={{ borderTop: "1px solid rgba(var(--border), 0.2)", paddingTop: "12px" }}>
              <p className="text-xs font-semibold mb-1" style={{ color: "rgba(var(--text-secondary), 0.6)" }}>
                Feedback
              </p>
              <p className="text-xs" style={{ color: "rgba(var(--text-primary), 0.8)" }}>
                {exec.feedback}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Single version row
// ─────────────────────────────────────────────────────────────────────────────
function VersionRow({
  v,
  prevScore,
  index,
}: {
  v: PromptVersion
  prevScore: number | null
  index: number
}) {
  const [expanded, setExpanded] = useState(false)
  const preview = v.prompt_text.length > 160 ? v.prompt_text.slice(0, 160) + "…" : v.prompt_text

  return (
    <div
      className="rounded-xl border transition-all duration-200"
      style={{
        background: "rgba(var(--surface), 0.35)",
        borderColor: "rgba(var(--border), 0.3)",
      }}
    >
      {/* Header row */}
      <div
        className="flex flex-wrap items-center gap-3 px-4 py-3 cursor-pointer select-none"
        onClick={() => setExpanded(e => !e)}
      >
        {/* Version index pill */}
        <span
          className="text-xs font-mono font-bold rounded px-1.5 py-0.5"
          style={{ background: "rgba(var(--surface), 0.6)", color: "rgba(var(--text-secondary), 0.8)", minWidth: 28, textAlign: "center" }}
        >
          #{index + 1}
        </span>

        {/* Agent + context badges */}
        <span
          className="text-xs font-medium rounded-full px-2 py-0.5"
          style={{ background: agentBadgeColor(v.agent_name), color: "rgba(var(--text-primary), 0.9)" }}
        >
          {v.agent_name}
        </span>
        <span
          className="text-xs font-medium rounded-full px-2 py-0.5"
          style={{ background: contextBadgeColor(v.context_type), color: "rgba(var(--text-primary), 0.9)" }}
        >
          {v.context_type}
        </span>

        {/* Score */}
        <div className="flex items-center gap-1.5 ml-auto">
          <TrendIcon prev={prevScore} curr={v.performance_score} />
          <ScoreBar score={v.performance_score} />
          <span
            className="text-xs rounded px-1.5 py-0.5"
            style={{ background: "rgba(var(--surface), 0.5)", color: scoreColor(v.performance_score) }}
          >
            {scoreLabel(v.performance_score)}
          </span>
        </div>

        {/* Use count */}
        <span className="text-xs" style={{ color: "rgba(var(--text-secondary), 0.7)" }}>
          ×{v.use_count} used
        </span>

        {/* Timestamp */}
        <span className="text-xs" style={{ color: "rgba(var(--text-secondary), 0.5)" }}>
          {relativeTime(v.created_at)}
        </span>

        {/* Expand toggle */}
        {expanded
          ? <ChevronUp  className="w-3.5 h-3.5" style={{ color: "rgba(var(--text-secondary), 0.5)" }} />
          : <ChevronDown className="w-3.5 h-3.5" style={{ color: "rgba(var(--text-secondary), 0.5)" }} />
        }
      </div>

      {/* Collapsed preview */}
      {!expanded && (
        <p
          className="px-4 pb-3 text-xs font-mono leading-relaxed"
          style={{ color: "rgba(var(--text-secondary), 0.65)" }}
        >
          {preview}
        </p>
      )}

      {/* Expanded full prompt */}
      {expanded && (
        <div className="px-4 pb-4 space-y-2 border-t" style={{ borderColor: "rgba(var(--border), 0.2)" }}>
          <p className="pt-3 text-xs" style={{ color: "rgba(var(--text-secondary), 0.6)" }}>
            ID: <span className="font-mono">{v.id}</span>
            {" · "}Updated: {relativeTime(v.updated_at)}
          </p>
          <pre
            className="whitespace-pre-wrap text-xs font-mono p-3 rounded-lg leading-relaxed overflow-auto max-h-96"
            style={{
              background: "rgba(var(--bg), 0.6)",
              color: "rgba(var(--text-primary), 0.85)",
              border: "1px solid rgba(var(--border), 0.2)",
            }}
          >
            {v.prompt_text}
          </pre>
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Main page
// ─────────────────────────────────────────────────────────────────────────────

export default function PromptLogPage() {
  const [data,        setData]        = useState<LogData | null>(null)
  const [loading,     setLoading]     = useState(true)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)
  const [filter,      setFilter]      = useState<{ agent_name: string; context_type: string } | null>(null)
  const [tab,         setTab]         = useState<"templates" | "executions">("templates")

  const fetchData = useCallback(async () => {
    try {
      const params = new URLSearchParams({ limit: "200" })
      if (filter) {
        params.set("agent_name",   filter.agent_name)
        params.set("context_type", filter.context_type)
      }
      const res  = await fetch(`http://localhost:8004/prompt-log?${params}`)
      const json = await res.json() as LogData
      setData(json)
      setLastRefresh(new Date())
    } catch {
      // keep stale data shown, just stop spinner
    } finally {
      setLoading(false)
    }
  }, [filter])

  // Initial + filter-change fetch
  useEffect(() => {
    setLoading(true)
    fetchData()
  }, [fetchData])

  // Auto-refresh every 6 s
  useEffect(() => {
    if (!autoRefresh) return
    const id = setInterval(fetchData, 6000)
    return () => clearInterval(id)
  }, [autoRefresh, fetchData])

  // Group versions by agent+context to compute trend
  const filteredVersions = data?.templates ?? []

  // Build a map: "agent/context" → sorted versions (oldest first) for trend
  const trendMap: Record<string, PromptVersion[]> = {}
  for (const v of [...filteredVersions].reverse()) {
    const key = `${v.agent_name}/${v.context_type}`
    if (!trendMap[key]) trendMap[key] = []
    trendMap[key].push(v)
  }

  // Filter executions by agent/context if needed
  const filteredExecutions = data?.executions?.filter(e => {
    if (!filter) return true
    return e.agent_name === filter.agent_name && e.context_type === filter.context_type
  }) ?? []

  // Summary stats
  const scored = filteredVersions.filter(v => v.performance_score !== null)
  const avgScore = scored.length
    ? scored.reduce((a, v) => a + (v.performance_score ?? 0), 0) / scored.length
    : null
  const bestScore = scored.length
    ? Math.max(...scored.map(v => v.performance_score ?? 0))
    : null

  // Execution stats
  const scoredExecutions = filteredExecutions.filter(e => e.overall_score !== undefined)
  const avgExecutionScore = scoredExecutions.length
    ? scoredExecutions.reduce((a, e) => a + (e.overall_score ?? 0), 0) / scoredExecutions.length
    : null
  const bestExecutionScore = scoredExecutions.length
    ? Math.max(...scoredExecutions.map(e => e.overall_score ?? 0))
    : null

  const displayStats = tab === "templates"
    ? {
        total: data?.total_templates || 0,
        scored: scored.length,
        avgScore,
        bestScore,
      }
    : {
        total: data?.total_executions || 0,
        scored: scoredExecutions.length,
        avgScore: avgExecutionScore,
        bestScore: bestExecutionScore,
      }

  return (
    <div
      className="min-h-screen overflow-y-auto"
      style={{ background: "rgba(var(--bg), 1)", color: "rgba(var(--text-primary), 1)" }}
    >
      {/* Header */}
      <div
        className="sticky top-0 z-10 flex items-center gap-3 px-6 py-4 border-b"
        style={{
          background: "rgba(var(--surface), 0.85)",
          backdropFilter: "blur(12px)",
          borderColor: "rgba(var(--border), 0.3)",
        }}
      >
        <Link href="/">
          <Button variant="ghost" size="sm" style={{ color: "rgba(var(--text-secondary), 1)" }}>
            <ArrowLeft className="w-4 h-4 mr-1" />Back
          </Button>
        </Link>
        <Zap className="w-5 h-5" style={{ color: "rgba(var(--secondary), 1)" }} />
        <h1 className="text-lg font-semibold">Prompt Evolution Log</h1>

        <div className="ml-auto flex items-center gap-3">
          {/* Live indicator */}
          <div className="flex items-center gap-1.5">
            <div
              className="w-2 h-2 rounded-full"
              style={{
                background: autoRefresh ? "#22c55e" : "rgba(120,120,140,0.5)",
                boxShadow: autoRefresh ? "0 0 6px #22c55e" : "none",
                animation: autoRefresh ? "pulse 2s infinite" : "none",
              }}
            />
            <span className="text-xs" style={{ color: "rgba(var(--text-secondary), 0.7)" }}>
              {autoRefresh ? "live" : "paused"}
            </span>
          </div>
          {lastRefresh && (
            <span className="text-xs" style={{ color: "rgba(var(--text-secondary), 0.4)" }}>
              {relativeTime(lastRefresh.toISOString())}
            </span>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setAutoRefresh(r => !r)}
            style={{ color: "rgba(var(--text-secondary), 0.8)" }}
          >
            {autoRefresh ? "Pause" : "Resume"}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => { setLoading(true); fetchData() }}
            style={{ color: "rgba(var(--text-secondary), 0.8)" }}
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </Button>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-6 space-y-6">

        {/* Summary cards */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: tab === "templates" ? "Total Templates" : "Total Executions",  value: displayStats.total || "–" },
            { label: "Scored",          value: displayStats.scored || "–" },
            { label: "Avg Score",       value: displayStats.avgScore !== null ? `${Math.round(displayStats.avgScore * 100)}%` : "–" },
            { label: "Best Score",      value: displayStats.bestScore !== null ? `${Math.round(displayStats.bestScore * 100)}%` : "–" },
          ].map(stat => (
            <Card
              key={stat.label}
              className="p-4 text-center rounded-xl border"
              style={{ background: "rgba(var(--surface), 0.4)", borderColor: "rgba(var(--border), 0.3)" }}
            >
              <p className="text-2xl font-bold" style={{ color: "rgba(var(--text-primary), 1)" }}>{stat.value}</p>
              <p className="text-xs mt-1" style={{ color: "rgba(var(--text-secondary), 0.65)" }}>{stat.label}</p>
            </Card>
          ))}
        </div>

        {/* Tab switcher */}
        <div className="flex border-b" style={{ borderColor: "rgba(var(--border), 0.3)" }}>
          <button
            onClick={() => setTab("templates")}
            className="px-4 py-3 text-sm font-medium transition-colors border-b-2 -mb-px"
            style={{
              borderColor: tab === "templates" ? "rgba(var(--secondary), 1)" : "transparent",
              color: tab === "templates" ? "rgba(var(--secondary), 1)" : "rgba(var(--text-secondary), 0.6)",
            }}
          >
            Templates ({data?.total_templates || 0})
          </button>
          <button
            onClick={() => setTab("executions")}
            className="px-4 py-3 text-sm font-medium transition-colors border-b-2 -mb-px"
            style={{
              borderColor: tab === "executions" ? "rgba(var(--secondary), 1)" : "transparent",
              color: tab === "executions" ? "rgba(var(--secondary), 1)" : "rgba(var(--text-secondary), 0.6)",
            }}
          >
            Executions ({data?.total_executions || 0})
          </button>
        </div>

        {/* Filter tabs */}
        {(data?.agents?.length ?? 0) > 0 && (
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => setFilter(null)}
              className="text-xs rounded-full px-3 py-1 border transition-all"
              style={{
                background: filter === null ? "rgba(var(--secondary), 0.25)" : "rgba(var(--surface), 0.4)",
                borderColor: filter === null ? "rgba(var(--secondary), 0.5)" : "rgba(var(--border), 0.3)",
                color: "rgba(var(--text-primary), 0.9)",
              }}
            >
              All
            </button>
            {data!.agents.map(a => {
              const active = filter?.agent_name === a.agent_name && filter?.context_type === a.context_type
              return (
                <button
                  key={`${a.agent_name}/${a.context_type}`}
                  onClick={() => setFilter(active ? null : a)}
                  className="text-xs rounded-full px-3 py-1 border transition-all"
                  style={{
                    background: active ? "rgba(var(--secondary), 0.25)" : "rgba(var(--surface), 0.4)",
                    borderColor: active ? "rgba(var(--secondary), 0.5)" : "rgba(var(--border), 0.3)",
                    color: "rgba(var(--text-primary), 0.9)",
                  }}
                >
                  {a.agent_name} / {a.context_type}
                </button>
              )
            })}
          </div>
        )}

        {/* Version/Execution list */}
        {loading && !data && (
          <div className="flex justify-center py-16">
            <RefreshCw className="w-8 h-8 animate-spin" style={{ color: "rgba(var(--text-secondary), 0.4)" }} />
          </div>
        )}

        {!loading && tab === "templates" && filteredVersions.length === 0 && (
          <div className="text-center py-16 space-y-3">
            <Zap className="w-10 h-10 mx-auto" style={{ color: "rgba(var(--text-secondary), 0.3)" }} />
            <p style={{ color: "rgba(var(--text-secondary), 0.5)" }}>
              No prompt templates yet. Generate some content to see the optimizer in action.
            </p>
          </div>
        )}

        {!loading && tab === "executions" && filteredExecutions.length === 0 && (
          <div className="text-center py-16 space-y-3">
            <Zap className="w-10 h-10 mx-auto" style={{ color: "rgba(var(--text-secondary), 0.3)" }} />
            <p style={{ color: "rgba(var(--text-secondary), 0.5)" }}>
              No execution records yet. Generate content with brand context to see executions.
            </p>
          </div>
        )}

        {tab === "templates" && filteredVersions.length > 0 && (
          <div className="space-y-3">
            {filteredVersions.map((v, i) => {
              const key = `${v.agent_name}/${v.context_type}`
              // Find previous version score (the one directly after in the reversed sorted list)
              const group = trendMap[key] ?? []
              const posInGroup = group.findIndex(g => g.id === v.id)
              const prev = posInGroup > 0 ? group[posInGroup - 1].performance_score : null
              return <VersionRow key={v.id} v={v} prevScore={prev} index={i} />
            })}
          </div>
        )}

        {tab === "executions" && filteredExecutions.length > 0 && (
          <div className="space-y-3">
            {filteredExecutions.map((exec) => (
              <ExecutionRow key={exec.execution_id} exec={exec} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
