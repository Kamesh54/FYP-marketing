"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Textarea } from "@/components/ui/textarea"
import { ArrowLeft, CheckCircle, XCircle, Edit2, RefreshCw, Bell } from "lucide-react"
import Link from "next/link"

const ORCHESTRATOR = "http://127.0.0.1:8004"
const POLL_INTERVAL = 3000 // ms

interface CriticScore {
  intent_score: number
  brand_score: number
  quality_score: number
  critique: string
  suggestions: string[]
}

interface HitlEvent {
  id: number
  content_id: string
  content_text: string
  content_type: string
  platform?: string
  critic_data?: CriticScore
  composite_score?: number
  created_at: string
}

function ScoreBar({ label, value, color }: { label: string; value: number; color: string }) {
  const pct = Math.round(value * 100)
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-gray-400">{label}</span>
        <span className="font-medium">{pct}%</span>
      </div>
      <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color} transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

export default function ContentApprovalPage() {
  const [events, setEvents] = useState<HitlEvent[]>([])
  const [editId, setEditId] = useState<string | null>(null)
  const [editText, setEditText] = useState("")
  const [msg, setMsg] = useState("")
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState<string>("")
  const pollerRef = useRef<NodeJS.Timeout | null>(null)

  useEffect(() => {
    const sid = localStorage.getItem("session_id") || "default"
    setSessionId(sid)
  }, [])

  const fetchPending = useCallback(async () => {
    if (!sessionId) return
    try {
      const r = await fetch(`${ORCHESTRATOR}/hitl/pending/${sessionId}`)
      if (r.ok) {
        const data = await r.json()
        setEvents(data.events || [])
      }
    } catch (_) {}
  }, [sessionId])

  useEffect(() => {
    if (!sessionId) return
    fetchPending()
    pollerRef.current = setInterval(fetchPending, POLL_INTERVAL)
    return () => { if (pollerRef.current) clearInterval(pollerRef.current) }
  }, [sessionId, fetchPending])

  async function respond(eventId: number, decision: "approved" | "rejected", editedText?: string) {
    setLoading(true)
    setMsg("")
    try {
      const body: Record<string, unknown> = {
        decision,
        reviewer_id: localStorage.getItem("user_id") || "user",
      }
      if (editedText) body.edited_content = editedText
      const r = await fetch(`${ORCHESTRATOR}/hitl/respond/${eventId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })
      if (r.ok) {
        setMsg(decision === "approved" ? "Content approved!" : "Content rejected.")
        setEditId(null)
        setEditText("")
        fetchPending()
      } else {
        setMsg("Failed: " + (await r.text()))
      }
    } catch (e: any) {
      setMsg("Error: " + e.message)
    }
    setLoading(false)
  }

  const compositeLabel = (score?: number) => {
    if (!score) return "–"
    if (score >= 0.85) return "Excellent"
    if (score >= 0.70) return "Good"
    if (score >= 0.50) return "Needs Review"
    return "Poor"
  }

  const compositeColor = (score?: number) => {
    if (!score) return "bg-gray-500"
    if (score >= 0.70) return "bg-green-500"
    if (score >= 0.50) return "bg-yellow-500"
    return "bg-red-500"
  }

  return (
    <div className="min-h-screen bg-gray-950 text-white p-6 overflow-y-auto">
      {/* Header */}
      <div className="flex items-center gap-4 mb-8">
        <Link href="/">
          <Button variant="ghost" size="sm"><ArrowLeft className="h-4 w-4 mr-1" />Back</Button>
        </Link>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Bell className="h-6 w-6 text-yellow-400" />
          Content Approval
          {events.length > 0 && (
            <Badge className="bg-yellow-500 text-black ml-2">{events.length}</Badge>
          )}
        </h1>
        <Button
          variant="ghost"
          size="sm"
          onClick={fetchPending}
          className="ml-auto"
          aria-label="Refresh"
        >
          <RefreshCw className="h-4 w-4" />
        </Button>
      </div>

      {msg && (
        <div className={`mb-4 px-4 py-2 rounded text-sm ${msg.includes("approved") ? "bg-green-900 text-green-300" : "bg-red-900 text-red-300"}`}>
          {msg}
        </div>
      )}

      {events.length === 0 ? (
        <Card className="bg-gray-900 border-gray-700 text-center py-16">
          <CardContent>
            <CheckCircle className="h-12 w-12 text-green-500 mx-auto mb-3 opacity-50" />
            <p className="text-gray-400">No pending content awaiting approval.</p>
            <p className="text-gray-600 text-sm mt-1">Polling every {POLL_INTERVAL / 1000}s…</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-6">
          {events.map((ev) => (
            <Card key={ev.id} className="bg-gray-900 border-gray-700">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                  <div>
                    <CardTitle className="text-base">Content ID: <span className="text-purple-300 font-mono">{ev.content_id}</span></CardTitle>
                    <CardDescription className="mt-1">
                      {ev.content_type && <Badge variant="outline" className="mr-2 text-xs">{ev.content_type}</Badge>}
                      {ev.platform && <Badge variant="secondary" className="mr-2 text-xs">{ev.platform}</Badge>}
                      <span className="text-xs text-gray-500">{new Date(ev.created_at).toLocaleString()}</span>
                    </CardDescription>
                  </div>
                  {ev.composite_score !== undefined && (
                    <div className="flex items-center gap-2">
                      <Badge className={`${compositeColor(ev.composite_score)} text-white`}>
                        {compositeLabel(ev.composite_score)} ({Math.round((ev.composite_score ?? 0) * 100)}%)
                      </Badge>
                    </div>
                  )}
                </div>
              </CardHeader>

              <CardContent className="space-y-4">
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  {/* Content text */}
                  <div className="space-y-2">
                    <p className="text-xs uppercase tracking-wider text-gray-500">Content</p>
                    {editId === String(ev.id) ? (
                      <Textarea
                        value={editText}
                        onChange={(e) => setEditText(e.target.value)}
                        rows={8}
                        className="bg-gray-800 border-gray-600 text-sm"
                      />
                    ) : (
                      <pre className="text-sm text-gray-200 bg-gray-800 p-3 rounded whitespace-pre-wrap leading-relaxed max-h-48 overflow-y-auto">
                        {ev.content_text}
                      </pre>
                    )}
                  </div>

                  {/* Critic scores */}
                  {ev.critic_data && (
                    <div className="space-y-3">
                      <p className="text-xs uppercase tracking-wider text-gray-500">Critic Analysis</p>
                      <div className="space-y-2">
                        <ScoreBar label="Intent Match" value={ev.critic_data.intent_score} color="bg-blue-500" />
                        <ScoreBar label="Brand Alignment" value={ev.critic_data.brand_score} color="bg-purple-500" />
                        <ScoreBar label="Quality" value={ev.critic_data.quality_score} color="bg-green-500" />
                      </div>
                      <div className="bg-gray-800 rounded p-3 space-y-2">
                        <p className="text-xs text-gray-500 uppercase tracking-wider">Critique</p>
                        <p className="text-sm text-gray-300">{ev.critic_data.critique}</p>
                        {ev.critic_data.suggestions?.length > 0 && (
                          <ul className="text-xs text-gray-400 list-disc list-inside space-y-0.5">
                            {ev.critic_data.suggestions.map((s, i) => <li key={i}>{s}</li>)}
                          </ul>
                        )}
                      </div>
                    </div>
                  )}
                </div>

                {/* Action buttons */}
                <div className="flex flex-wrap gap-2 pt-2 border-t border-gray-700">
                  {editId === String(ev.id) ? (
                    <>
                      <Button
                        onClick={() => respond(ev.id, "approved", editText)}
                        disabled={loading}
                        className="bg-green-600 hover:bg-green-700"
                      >
                        <CheckCircle className="h-4 w-4 mr-1" />Submit Edit
                      </Button>
                      <Button variant="ghost" onClick={() => { setEditId(null); setEditText("") }} disabled={loading}>
                        Cancel
                      </Button>
                    </>
                  ) : (
                    <>
                      <Button
                        onClick={() => respond(ev.id, "approved")}
                        disabled={loading}
                        className="bg-green-600 hover:bg-green-700"
                      >
                        <CheckCircle className="h-4 w-4 mr-1" />Approve
                      </Button>
                      <Button
                        onClick={() => respond(ev.id, "rejected")}
                        disabled={loading}
                        variant="destructive"
                      >
                        <XCircle className="h-4 w-4 mr-1" />Reject
                      </Button>
                      <Button
                        variant="outline"
                        disabled={loading}
                        className="border-gray-600"
                        onClick={() => {
                          setEditId(String(ev.id))
                          setEditText(ev.content_text)
                        }}
                      >
                        <Edit2 className="h-4 w-4 mr-1" />Edit &amp; Approve
                      </Button>
                    </>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
