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

interface AgentKey {
  agent_name: string
  context_type: string
}

interface LogData {
  versions: PromptVersion[]
  total: number
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
  const filteredVersions = data?.versions ?? []

  // Build a map: "agent/context" → sorted versions (oldest first) for trend
  const trendMap: Record<string, PromptVersion[]> = {}
  for (const v of [...filteredVersions].reverse()) {
    const key = `${v.agent_name}/${v.context_type}`
    if (!trendMap[key]) trendMap[key] = []
    trendMap[key].push(v)
  }

  // Summary stats
  const scored = filteredVersions.filter(v => v.performance_score !== null)
  const avgScore = scored.length
    ? scored.reduce((a, v) => a + (v.performance_score ?? 0), 0) / scored.length
    : null
  const bestScore = scored.length
    ? Math.max(...scored.map(v => v.performance_score ?? 0))
    : null

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
            { label: "Total Versions",  value: data?.total ?? "–" },
            { label: "Scored",          value: scored.length || "–" },
            { label: "Avg Score",       value: avgScore !== null ? `${Math.round(avgScore * 100)}%` : "–" },
            { label: "Best Score",      value: bestScore !== null ? `${Math.round(bestScore * 100)}%` : "–" },
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

        {/* Version list */}
        {loading && !data && (
          <div className="flex justify-center py-16">
            <RefreshCw className="w-8 h-8 animate-spin" style={{ color: "rgba(var(--text-secondary), 0.4)" }} />
          </div>
        )}

        {!loading && filteredVersions.length === 0 && (
          <div className="text-center py-16 space-y-3">
            <Zap className="w-10 h-10 mx-auto" style={{ color: "rgba(var(--text-secondary), 0.3)" }} />
            <p style={{ color: "rgba(var(--text-secondary), 0.5)" }}>
              No prompt versions yet. Generate some content to see the optimizer in action.
            </p>
          </div>
        )}

        {filteredVersions.length > 0 && (
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
      </div>
    </div>
  )
}
