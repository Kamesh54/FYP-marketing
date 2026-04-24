"use client"

import { useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { ArrowLeft, BarChart3, RefreshCcw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"

const API_BASE = "http://127.0.0.1:8004"

type Decision = "approved" | "rejected" | "edited" | null

type CriticLog = {
  id: number
  content_id: string
  session_id?: string | null
  intent_score: number
  brand_score: number
  quality_score: number
  overall_score: number
  critique_text: string
  passed: number | boolean
  user_decision?: Decision
  created_at: string
  content_type?: string | null
  brand_name?: string | null
  content_preview?: string
}

type FilterMode = "all" | "pass" | "fail" | "pending"

function scoreColor(v: number) {
  if (v >= 0.7) return "text-green-400"
  if (v >= 0.5) return "text-amber-400"
  return "text-red-400"
}

function pct(v: number) {
  return Math.max(0, Math.min(100, Math.round(v * 100)))
}

function fmtDate(s?: string) {
  if (!s) return "-"
  const d = new Date(s)
  return Number.isNaN(d.getTime()) ? s : d.toLocaleString()
}

export default function CriticPage() {
  const [logs, setLogs] = useState<CriticLog[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  const [filter, setFilter] = useState<FilterMode>("all")
  const [query, setQuery] = useState("")
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [updating, setUpdating] = useState<string>("")

  async function loadLogs() {
    setLoading(true)
    setError("")
    try {
      const res = await fetch(`${API_BASE}/critic/logs?limit=200`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = (await res.json()) as CriticLog[]
      setLogs(data)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load critic logs")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadLogs()
  }, [])

  const stats = useMemo(() => {
    const total = logs.length
    const passed = logs.filter((l) => Boolean(l.passed)).length
    const failed = total - passed
    const avg = (k: "intent_score" | "brand_score" | "quality_score") => {
      if (!total) return 0
      return logs.reduce((sum, l) => sum + (Number(l[k]) || 0), 0) / total
    }
    return {
      total,
      passed,
      failed,
      passRate: total ? Math.round((passed / total) * 100) : 0,
      avgIntent: avg("intent_score"),
      avgBrand: avg("brand_score"),
      avgQuality: avg("quality_score"),
    }
  }, [logs])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return logs.filter((l) => {
      if (filter === "pass" && !l.passed) return false
      if (filter === "fail" && l.passed) return false
      if (filter === "pending" && l.user_decision) return false
      if (!q) return true
      const hay = `${l.brand_name || ""} ${l.content_type || ""} ${l.content_preview || ""}`.toLowerCase()
      return hay.includes(q)
    })
  }, [logs, filter, query])

  async function recordDecision(contentId: string, decision: "approved" | "rejected") {
    setUpdating(contentId + decision)
    try {
      const res = await fetch(`${API_BASE}/critic/decision/${contentId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      await loadLogs()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to record decision")
    } finally {
      setUpdating("")
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 text-white p-6 overflow-y-auto">
      <div className="max-w-7xl mx-auto">
        <div className="flex items-center gap-4 mb-6">
          <Link href="/">
            <Button variant="ghost" size="sm"><ArrowLeft className="h-4 w-4 mr-1" />Back</Button>
          </Link>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <BarChart3 className="h-6 w-6 text-indigo-400" /> Critic Dashboard
          </h1>
          <div className="ml-auto">
            <Button variant="outline" size="sm" onClick={loadLogs} disabled={loading}>
              <RefreshCcw className="h-4 w-4 mr-1" />Refresh
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3 mb-6">
          <Card className="bg-gray-900 border-gray-700"><CardContent className="p-4"><p className="text-xs text-gray-400">Total</p><p className="text-2xl font-bold text-indigo-400">{stats.total}</p></CardContent></Card>
          <Card className="bg-gray-900 border-gray-700"><CardContent className="p-4"><p className="text-xs text-gray-400">Passed</p><p className="text-2xl font-bold text-green-400">{stats.passed}</p></CardContent></Card>
          <Card className="bg-gray-900 border-gray-700"><CardContent className="p-4"><p className="text-xs text-gray-400">Failed</p><p className="text-2xl font-bold text-red-400">{stats.failed}</p></CardContent></Card>
          <Card className="bg-gray-900 border-gray-700"><CardContent className="p-4"><p className="text-xs text-gray-400">Pass Rate</p><p className="text-2xl font-bold">{stats.passRate}%</p></CardContent></Card>
          <Card className="bg-gray-900 border-gray-700"><CardContent className="p-4"><p className="text-xs text-gray-400">Avg Intent</p><p className="text-2xl font-bold">{stats.avgIntent.toFixed(2)}</p></CardContent></Card>
          <Card className="bg-gray-900 border-gray-700"><CardContent className="p-4"><p className="text-xs text-gray-400">Avg Brand</p><p className="text-2xl font-bold">{stats.avgBrand.toFixed(2)}</p></CardContent></Card>
          <Card className="bg-gray-900 border-gray-700"><CardContent className="p-4"><p className="text-xs text-gray-400">Avg Quality</p><p className="text-2xl font-bold">{stats.avgQuality.toFixed(2)}</p></CardContent></Card>
        </div>

        <div className="flex flex-wrap gap-2 items-center mb-4">
          {(["all", "pass", "fail", "pending"] as FilterMode[]).map((f) => (
            <Button
              key={f}
              size="sm"
              variant={filter === f ? "default" : "outline"}
              onClick={() => setFilter(f)}
            >
              {f === "pass" ? "Passed" : f === "fail" ? "Failed" : f === "pending" ? "Awaiting Decision" : "All"}
            </Button>
          ))}
          <input
            className="ml-auto bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm w-72"
            placeholder="Search brand or content..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>

        {error && <div className="mb-4 text-sm text-red-400">{error}</div>}
        {loading && <div className="text-sm text-gray-400">Loading critic logs...</div>}

        {!loading && filtered.length === 0 && (
          <Card className="bg-gray-900 border-gray-700"><CardContent className="p-8 text-center text-gray-500">No results for current filter.</CardContent></Card>
        )}

        <div className="space-y-3">
          {filtered.map((l, i) => {
            const isOpen = expandedId === l.id
            return (
              <Card key={l.id} className="bg-gray-900 border-gray-700">
                <CardContent className="p-4">
                  <div className="grid grid-cols-1 lg:grid-cols-12 gap-3 items-center">
                    <div className="lg:col-span-1 text-xs text-gray-500">#{i + 1}</div>
                    <div className="lg:col-span-2 font-semibold">{l.brand_name || "-"}</div>
                    <div className="lg:col-span-1"><Badge variant="outline">{l.content_type || "-"}</Badge></div>
                    <div className="lg:col-span-3 text-sm text-gray-300 truncate">{l.content_preview || "-"}</div>
                    <div className="lg:col-span-2 text-xs text-gray-300">
                      <div>Intent: <span className={scoreColor(l.intent_score)}>{l.intent_score.toFixed(2)}</span></div>
                      <div>Brand: <span className={scoreColor(l.brand_score)}>{l.brand_score.toFixed(2)}</span></div>
                      <div>Quality: <span className={scoreColor(l.quality_score)}>{l.quality_score.toFixed(2)}</span></div>
                    </div>
                    <div className={`lg:col-span-1 font-bold ${scoreColor(l.overall_score)}`}>{l.overall_score.toFixed(3)}</div>
                    <div className="lg:col-span-2 flex gap-2 flex-wrap justify-start lg:justify-end">
                      <Badge className={l.passed ? "bg-green-700" : "bg-red-700"}>{l.passed ? "PASS" : "FAIL"}</Badge>
                      <Badge variant="outline">{l.user_decision || "pending"}</Badge>
                      <Button variant="ghost" size="sm" onClick={() => setExpandedId(isOpen ? null : l.id)}>
                        {isOpen ? "Hide" : "Details"}
                      </Button>
                    </div>
                  </div>

                  {isOpen && (
                    <div className="mt-4 border-t border-gray-800 pt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <p className="text-xs text-gray-500 mb-1">Critique</p>
                        <p className="text-sm text-gray-300 whitespace-pre-wrap">{l.critique_text || "-"}</p>
                        <p className="text-xs text-gray-500 mt-3">Date: {fmtDate(l.created_at)}</p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-500 mb-2">Decision Actions</p>
                        <div className="flex gap-2">
                          <Button
                            size="sm"
                            className="bg-green-700 hover:bg-green-600"
                            disabled={updating === l.content_id + "approved"}
                            onClick={() => recordDecision(l.content_id, "approved")}
                          >Approve</Button>
                          <Button
                            size="sm"
                            className="bg-red-700 hover:bg-red-600"
                            disabled={updating === l.content_id + "rejected"}
                            onClick={() => recordDecision(l.content_id, "rejected")}
                          >Reject</Button>
                        </div>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            )
          })}
        </div>
      </div>
    </div>
  )
}
