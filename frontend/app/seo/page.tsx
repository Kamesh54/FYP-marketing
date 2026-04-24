"use client"

import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Search, Loader2, ExternalLink, CheckCircle, XCircle, AlertTriangle, ArrowLeft } from "lucide-react"
import Link from "next/link"

interface Recommendation {
  area: string
  issue: string
  priority: "High" | "Medium" | "Low"
  suggestion: string
}

interface AuditResult {
  status: "completed" | "error"
  url: string
  final_url?: string
  report_path?: string
  scores?: Record<string, number>
  recommendations?: (Recommendation | string)[]
  error?: string
  audited_at?: string
}

const COUNT_FIELDS = new Set([
  "recommendations",
  "high_priority",
  "medium_priority",
  "low_priority",
  "issues",
  "opportunities",
])

function normalizeScore(value: number) {
  if (!Number.isFinite(value)) return 0
  const normalized = value <= 1 ? value * 100 : value
  return Math.max(0, Math.min(100, Math.round(normalized)))
}

const SCORE_LABELS: Record<string, string> = {
  onpage:      "On-Page SEO",
  links:       "Links",
  performance: "Performance",
  usability:   "Usability",
  social:      "Social",
  local:       "Local SEO",
  technical:   "Technical",
}

function ScoreBar({ label, score }: { label: string; score: number }) {
  const pct = normalizeScore(score)
  const color =
    pct >= 75 ? "#22c55e" :
    pct >= 50 ? "#f59e0b" :
                "#ef4444"

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-sm">
        <span style={{ color: "rgba(var(--text-secondary), 1)" }}>{label}</span>
        <span className="font-semibold" style={{ color }}>{pct}/100</span>
      </div>
      <div className="h-2 rounded-full overflow-hidden" style={{ background: "rgba(var(--surface), 0.6)" }}>
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
    </div>
  )
}

function overallGrade(scores: Record<string, number>) {
  // Only use the 'overall' score, not the count metrics
  const overall = scores.overall
  if (overall === undefined || overall === null) return null
  return normalizeScore(overall)
}

export default function SEOAuditPage() {
  const [url, setUrl]           = useState("")
  const [loading, setLoading]   = useState(false)
  const [result, setResult]     = useState<AuditResult | null>(null)
  const [error, setError]       = useState("")

  // Load last audit result pushed from the chat (stored in localStorage) OR extract URL from query/message
  useEffect(() => {
    if (typeof window === "undefined") return
    
    // Check for stored result first
    const stored = localStorage.getItem("lastSeoAudit")
    if (stored) {
      try {
        const parsed = JSON.parse(stored) as AuditResult
        setResult(parsed)
        if (parsed.url || parsed.final_url) setUrl(parsed.url || parsed.final_url || "")
        return
      } catch {}
    }

    // Extract URL from query params (seo?url=...)
    const params = new URLSearchParams(window.location.search)
    const queryUrl = params.get("url")
    if (queryUrl) {
      setUrl(queryUrl)
      return
    }

    // Extract URL from hash fragment (seo#https://example.com)
    const hashUrl = window.location.hash.replace("#", "")
    if (hashUrl && (hashUrl.startsWith("http://") || hashUrl.startsWith("https://"))) {
      setUrl(hashUrl)
      return
    }
  }, [])

  function clearResult() {
    setResult(null)
    setUrl("")
    setError("")
    localStorage.removeItem("lastSeoAudit")
  }

  async function runAudit() {
    if (!url.trim()) return
    setLoading(true)
    setResult(null)
    setError("")
    try {
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 300000) // 5-minute timeout for detailed analysis
      
      // Use detailed analysis endpoint for comprehensive report
      const res = await fetch("http://localhost:8004/seo/analyze/detailed", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url.trim() }),
        signal: controller.signal,
      })
      clearTimeout(timeout)
      if (!res.ok) throw new Error(`SEO analysis returned ${res.status}`)
      const data: AuditResult = await res.json()
      if (data.status === "error") throw new Error(data.error || "Audit failed")
      setResult(data)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Audit failed. Is the orchestrator running on port 8004?")
    } finally {
      setLoading(false)
    }
  }

  function reportUrl(reportPath: string) {
    // reports are saved as report_{host}.html in the workspace root
    const filename = reportPath.split(/[\\/]/).pop() || reportPath
    return `http://localhost:8080/${filename}`
  }

  const overall = result?.scores ? overallGrade(result.scores) : null

  return (
    <div
      className="min-h-screen p-6 font-sans overflow-y-auto"
      style={{ background: "rgba(var(--background), 1)", color: "rgba(var(--text-primary), 1)" }}
    >
      {/* Header */}
      <div className="max-w-3xl mx-auto">
        <div className="flex items-center gap-3 mb-8">
          <Link href="/">
            <Button variant="ghost" size="sm" style={{ color: "rgba(var(--text-secondary), 1)" }}>
              <ArrowLeft className="w-4 h-4 mr-1" />Back
            </Button>
          </Link>
          <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: "rgba(var(--primary), 0.15)" }}>
            <Search className="w-5 h-5" style={{ color: "rgba(var(--primary), 1)" }} />
          </div>
          <div>
            <h1 className="text-2xl font-bold">SEO Audit</h1>
            <p className="text-sm" style={{ color: "rgba(var(--text-secondary), 1)" }}>
              Analyse any URL for on-page, technical, performance &amp; social signals
            </p>
          </div>
        </div>

        {/* Input */}
        <Card
          className="p-5 mb-6 rounded-2xl border"
          style={{ background: "rgba(var(--surface), 0.5)", borderColor: "rgba(var(--border), 0.4)" }}
        >
          <div className="flex gap-3">
            <input
              type="url"
              placeholder="https://example.com"
              value={url}
              onChange={e => setUrl(e.target.value)}
              onKeyDown={e => e.key === "Enter" && !loading && runAudit()}
              className="flex-1 bg-transparent outline-none text-sm px-3 py-2 rounded-lg border"
              style={{
                borderColor: "rgba(var(--border), 0.5)",
                color: "rgba(var(--text-primary), 1)",
              }}
            />
            <Button
              onClick={runAudit}
              disabled={loading || !url.trim()}
              className="rounded-xl px-5"
              style={{ background: "rgba(var(--primary), 1)", color: "#fff" }}
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
              <span className="ml-2">{loading ? "Auditing..." : "Run Audit"}</span>
            </Button>
          </div>
        </Card>

        {/* Error */}
        {error && (
          <Card
            className="p-4 mb-6 rounded-2xl border flex items-start gap-3"
            style={{ background: "rgba(239,68,68,0.1)", borderColor: "rgba(239,68,68,0.3)" }}
          >
            <XCircle className="w-5 h-5 mt-0.5 shrink-0" style={{ color: "#ef4444" }} />
            <p className="text-sm" style={{ color: "#ef4444" }}>{error}</p>
          </Card>
        )}

        {/* Loading skeleton */}
        {loading && (
          <Card
            className="p-6 rounded-2xl border space-y-4"
            style={{ background: "rgba(var(--surface), 0.3)", borderColor: "rgba(var(--border), 0.3)" }}
          >
            <div className="flex items-center gap-2" style={{ color: "rgba(var(--text-secondary), 1)" }}>
              <Loader2 className="w-4 h-4 animate-spin" />
              <span className="text-sm">Running comprehensive SEO audit - this may take 20-30 seconds...</span>
            </div>
            {[...Array(7)].map((_, i) => (
              <div key={i} className="space-y-1 animate-pulse">
                <div className="h-3 w-32 rounded" style={{ background: "rgba(var(--surface), 0.8)" }} />
                <div className="h-2 rounded-full" style={{ background: "rgba(var(--surface), 0.8)" }} />
              </div>
            ))}
          </Card>
        )}

        {/* Results */}
        {result && !loading && (
          <div className="space-y-5">
            {/* From-chat banner */}
            {result.audited_at && (
              <div
                className="flex items-center justify-between px-4 py-2 rounded-xl text-sm"
                style={{ background: "rgba(var(--primary), 0.1)", border: "1px solid rgba(var(--primary), 0.25)" }}
              >
                <span style={{ color: "rgba(var(--primary), 1)" }}>
                  Results loaded from chat - {new Date(result.audited_at).toLocaleString()}
                </span>
                <button
                  onClick={clearResult}
                  className="text-xs underline opacity-70 hover:opacity-100"
                  style={{ color: "rgba(var(--text-secondary), 1)" }}
                >
                  Clear
                </button>
              </div>
            )}
            {/* Overall score */}
            <Card
              className="p-5 rounded-2xl border"
              style={{ background: "rgba(var(--surface), 0.5)", borderColor: "rgba(var(--border), 0.4)" }}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold">Overall Score</span>
                {overall !== null && (
                  <span
                    className="text-3xl font-bold"
                    style={{
                      color: overall >= 75 ? "#22c55e" : overall >= 50 ? "#f59e0b" : "#ef4444",
                    }}
                  >
                    {overall}<span className="text-lg font-normal">/100</span>
                  </span>
                )}
              </div>
              <p className="text-xs mb-4" style={{ color: "rgba(var(--text-secondary), 1)" }}>
                Audited: <a href={result.final_url || result.url} target="_blank" rel="noopener noreferrer" className="underline">{result.final_url || result.url}</a>
              </p>
              {/* Score bars - only actual scores, exclude counts */}
              <div className="space-y-3">
                {Object.entries(result.scores || {}).map(([key, val]) => {
                  // Skip count fields
                  if (COUNT_FIELDS.has(key)) {
                    return null
                  }
                  if (typeof val !== 'number' || val < 0 || val > 100) return null
                  return <ScoreBar key={key} label={SCORE_LABELS[key] || key} score={val} />
                })}
              </div>
              {/* Issue counts summary */}
              {(result.scores?.high_priority || result.scores?.medium_priority || result.scores?.low_priority) && (
                <div style={{ marginTop: '16px', paddingTop: '16px', borderTop: '1px solid rgba(var(--border), 0.4)' }}>
                  <p style={{ fontSize: '12px', color: "rgba(var(--text-secondary), 1)", marginBottom: '8px' }}>Issues by Priority:</p>
                  <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                    {result.scores?.high_priority ? (
                      <span style={{ fontSize: '13px', color: '#ef4444' }}>High: <strong>{result.scores.high_priority}</strong></span>
                    ) : null}
                    {result.scores?.medium_priority ? (
                      <span style={{ fontSize: '13px', color: '#f59e0b' }}>Medium: <strong>{result.scores.medium_priority}</strong></span>
                    ) : null}
                    {result.scores?.low_priority ? (
                      <span style={{ fontSize: '13px', color: '#22c55e' }}>Low: <strong>{result.scores.low_priority}</strong></span>
                    ) : null}
                  </div>
                </div>
              )}
            </Card>

            {/* Recommendations */}
            {result.recommendations && result.recommendations.length > 0 && (
              <Card
                className="p-5 rounded-2xl border"
                style={{ background: "rgba(var(--surface), 0.5)", borderColor: "rgba(var(--border), 0.4)" }}
              >
                <h2 className="font-semibold mb-3 flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4" style={{ color: "#f59e0b" }} />
                  Top Recommendations
                </h2>
                <ul className="space-y-3">
                  {result.recommendations.slice(0, 5).map((rec, i) => {
                    const isObj = typeof rec === "object" && rec !== null
                    const issue      = isObj ? (rec as Recommendation).issue      : rec as string
                    const suggestion = isObj ? (rec as Recommendation).suggestion : ""
                    const area       = isObj ? (rec as Recommendation).area       : ""
                    const priority   = isObj ? (rec as Recommendation).priority   : ""
                    const badgeColor =
                      priority === "High"   ? "#ef4444" :
                      priority === "Medium" ? "#f59e0b" :
                                             "#22c55e"
                    return (
                      <li key={i} className="flex items-start gap-2 text-sm">
                        <CheckCircle className="w-4 h-4 mt-0.5 shrink-0" style={{ color: "rgba(var(--primary), 1)" }} />
                        <div className="space-y-0.5">
                          <div className="flex items-center gap-2 flex-wrap">
                            {area && (
                              <span className="text-xs px-1.5 py-0.5 rounded font-medium" style={{ background: "rgba(var(--surface), 0.8)", color: "rgba(var(--text-secondary), 1)" }}>{area}</span>
                            )}
                            {priority && (
                              <span className="text-xs px-1.5 py-0.5 rounded font-semibold" style={{ background: `${badgeColor}22`, color: badgeColor }}>{priority}</span>
                            )}
                          </div>
                          <p style={{ color: "rgba(var(--text-primary), 1)" }}>{issue}</p>
                          {suggestion && (
                            <p className="text-xs" style={{ color: "rgba(var(--text-secondary), 1)" }}>{suggestion}</p>
                          )}
                        </div>
                      </li>
                    )
                  })}
                </ul>
              </Card>
            )}

            {/* Full report link */}
            {result.report_path && (
              <a
                href={reportUrl(result.report_path)}
                target="_blank"
                rel="noopener noreferrer"
                className="block"
              >
                <Button
                  className="w-full rounded-xl py-3"
                  style={{ background: "rgba(var(--primary), 0.15)", color: "rgba(var(--primary), 1)", border: "1px solid rgba(var(--primary), 0.3)" }}
                >
                  <ExternalLink className="w-4 h-4 mr-2" />
                  Open Full HTML Report
                </Button>
              </a>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
