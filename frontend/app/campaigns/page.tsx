"use client"

import { useState, useEffect, useRef } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { ArrowLeft, Calendar, Send, Trash2, Plus, Clock, RotateCw, History, Image as ImageIcon, ExternalLink } from "lucide-react"
import Link from "next/link"

const ORCHESTRATOR = "http://127.0.0.1:8004"
const CAMPAIGN_API = ORCHESTRATOR

interface Schedule {
  id: number
  name: string
  platform: string
  display_platform?: string
  content_template?: string
  content_text?: string
  trigger_type: "once" | "recurring"
  run_at?: string
  cron_expr?: string
  status: string
  created_at: string
  last_run?: string
  next_run?: string
  run_count?: number
  brand_name?: string
  ai_generate?: boolean
  run_history?: Array<{ job_id: string; status: string; post_url: string; ran_at: string }>
}

interface Brand {
  brand_name: string
  logo_url?: string
  industry?: string
}

interface PostJob {
  job_id: string
  status: string
  platform?: string
  post_url?: string
  error?: string
  generated_content?: string      // AI-written post text
  generated_image_url?: string    // AI-generated image preview URL
}

interface PostRecord {
  job_id: string
  user_id: number
  platform: string
  content_snippet: string
  topic?: string
  image_url?: string
  post_url: string
  status: string
  posted_at: string
  ai_generated?: boolean
}

interface CampaignHistoryRecord {
  id: string
  name: string
  status: string
  start_date?: string
  end_date?: string
  budget_tier?: string
  strategy?: string
  created_at: string
  agenda_total?: number
  agenda_completed?: number
  agenda_pending?: number
  agenda_failed?: number
}

interface GeneratedImage {
  filename: string
  url: string
  size_bytes: number
  created_at: string
}

const PLATFORMS = ["instagram"]

const PLATFORM_COLORS: Record<string, string> = {
  linkedin: "bg-blue-600",
  x: "bg-gray-700",
  instagram: "bg-pink-600",
  reddit: "bg-orange-600",
}

export default function CampaignsPage() {
  const [tab, setTab] = useState<"schedules" | "post-now" | "history" | "media">("schedules")
  const [schedules, setSchedules] = useState<Schedule[]>([])
  const [postHistory, setPostHistory] = useState<PostRecord[]>([])
  const [campaignHistory, setCampaignHistory] = useState<CampaignHistoryRecord[]>([])
  const [images, setImages] = useState<GeneratedImage[]>([])
  const [brands, setBrands] = useState<Brand[]>([])
  const [selectedBrand, setSelectedBrand] = useState<string>("")
  const [userId, setUserId] = useState<string>("1")
  const [msg, setMsg] = useState("")
  const [loading, setLoading] = useState(false)
  const [expandedSchedule, setExpandedSchedule] = useState<number | null>(null)

  // Schedule form state
  const [sName, setSName] = useState("")
  const [sPlatform, setSPlatform] = useState("instagram")
  const [sContent, setSContent] = useState("")
  const [sTrigger, setSTrigger] = useState<"once" | "recurring">("once")
  const [sRunAt, setSRunAt] = useState("")
  const [sCron, setSCron] = useState("")
  const [sRecurringDays, setSRecurringDays] = useState("7")
  const [sAiGenerate, setSAiGenerate] = useState(true)

  // Post Now state
  const [pPlatform, setPPlatform] = useState("instagram")
  const [pContent, setPContent] = useState("")
  const [pAiGenerate, setPAiGenerate] = useState(true)
  const [postResult, setPostResult] = useState<PostJob | null>(null)
  const pollRef = useRef<NodeJS.Timeout | null>(null)

  function getResolvedUserId(): string {
    // Keep compatibility with both key styles used across the app.
    return localStorage.getItem("userId") || localStorage.getItem("user_id") || "1"
  }

  useEffect(() => {
    const uid = getResolvedUserId()
    setUserId(uid)
    const savedBrand = localStorage.getItem("activeBrandName") || ""
    setSelectedBrand(savedBrand)
    fetchSchedules(uid)
    fetchBrands(uid, savedBrand)
  }, [])

  async function fetchBrands(uid = userId, savedBrandName = selectedBrand) {
    try {
      const r = await fetch(`${CAMPAIGN_API}/brands/${uid}`)
      const data = await r.json()
      const fetched: Brand[] = data.brands || []

      // If API has no rows but we already have an active brand in localStorage,
      // keep it visible so campaign forms still carry correct brand context.
      if ((!fetched || fetched.length === 0) && savedBrandName) {
        const fallback = [{ brand_name: savedBrandName }]
        setBrands(fallback)
        setSelectedBrand(savedBrandName)
        return
      }

      setBrands(fetched)

      // Ensure selected brand always points to an available option.
      if (savedBrandName && fetched.some((b) => b.brand_name === savedBrandName)) {
        setSelectedBrand(savedBrandName)
      } else if (fetched.length > 0) {
        setSelectedBrand(fetched[0].brand_name)
        localStorage.setItem("activeBrandName", fetched[0].brand_name)
      }
    } catch (_) {}
  }

  useEffect(() => {
    if (tab === "history") fetchHistory()
    if (tab === "history") fetchCampaignHistory()
    if (tab === "media") fetchImages()
  }, [tab])

  async function fetchSchedules(uid = userId) {
    try {
      const r = await fetch(`${CAMPAIGN_API}/schedules/${uid}`)
      const data = await r.json()
      setSchedules(data.schedules || [])
    } catch (_) {}
  }

  async function fetchHistory() {
    try {
      const r = await fetch(`${CAMPAIGN_API}/posts?user_id=${userId}`)
      const data = await r.json()
      setPostHistory(data.posts || [])
    } catch (_) {}
  }

  async function fetchCampaignHistory() {
    try {
      const r = await fetch(`${CAMPAIGN_API}/campaigns/history/${userId}`)
      const data = await r.json()
      setCampaignHistory(data.campaigns || [])
    } catch (_) {}
  }

  async function fetchImages() {
    try {
      const r = await fetch(`${ORCHESTRATOR}/images`)
      const data = await r.json()
      setImages(data.images || [])
    } catch (_) {}
  }

  async function createSchedule() {
    if (!sName || !sPlatform || !sContent) {
      setMsg("Name, platform, and content are required.")
      return
    }
    if (sTrigger === "once" && !sRunAt) { setMsg("Please specify a run time for one-off schedule."); return }
    if (sTrigger === "recurring" && !sCron) { setMsg("Please enter a cron expression for recurring schedule."); return }
    if (sTrigger === "recurring" && sRecurringDays && Number(sRecurringDays) <= 0) {
      setMsg("Recurring days must be greater than 0.")
      return
    }
    setLoading(true); setMsg("")
    try {
      const body: Record<string, unknown> = {
        user_id: parseInt(userId), name: sName, platform: sPlatform,
        content_text: sContent, trigger_type: sTrigger,
        ai_generate: sAiGenerate,
        brand_name: selectedBrand || undefined,
      }
      if (sTrigger === "once") body.run_at = sRunAt
      else {
        body.cron_expr = sCron
        if (sRecurringDays) body.recurring_days = parseInt(sRecurringDays)
      }
      const r = await fetch(`${CAMPAIGN_API}/schedule`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })
      if (r.ok) {
        setMsg("Schedule created!")
        setSName(""); setSContent(""); setSRunAt(""); setSCron(""); setSRecurringDays("7")
        fetchSchedules()
      } else { setMsg("Failed: " + (await r.text())) }
    } catch (e: any) { setMsg("Error: " + e.message) }
    setLoading(false)
  }

  async function cancelSchedule(id: number) {
    if (!confirm("Cancel this schedule?")) return
    try {
      await fetch(`${CAMPAIGN_API}/schedule/${id}?user_id=${userId}`, { method: "DELETE" })
      fetchSchedules()
    } catch (_) {}
  }

  async function postNow() {
    if (!pContent || !pPlatform) return
    setLoading(true); setPostResult(null); setMsg("")
    try {
      const r = await fetch(`${CAMPAIGN_API}/post`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: parseInt(userId), platform: pPlatform, content_text: pContent,
          ai_generate: pAiGenerate,
          brand_name: selectedBrand || undefined,
        }),
      })
      const data = await r.json()
      setPostResult(data)
      // Poll until completed/failed
      if (data.job_id) {
        pollRef.current = setInterval(async () => {
          try {
            const sr = await fetch(`${CAMPAIGN_API}/post/status/${data.job_id}`)
            const sd = await sr.json()
            setPostResult(sd)
            if (sd.status === "completed" || sd.status === "failed") {
              clearInterval(pollRef.current!)
              pollRef.current = null
            }
          } catch (_) { clearInterval(pollRef.current!); pollRef.current = null }
        }, 2000)
      }
    } catch (e: any) { setMsg("Error: " + e.message) }
    setLoading(false)
  }

  const statusColor = (s: string) => {
    if (s === "active" || s === "completed") return "bg-green-600"
    if (s === "cancelled" || s === "failed") return "bg-red-700"
    return "bg-yellow-600"
  }

  return (
    <div className="min-h-screen bg-gray-950 text-white p-6 overflow-y-auto">
      <div className="flex items-center gap-4 mb-4">
        <Link href="/"><Button variant="ghost" size="sm"><ArrowLeft className="h-4 w-4 mr-1" />Back</Button></Link>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Calendar className="h-6 w-6 text-green-400" />Campaign Scheduler
        </h1>
      </div>

      {/* Brand picker */}
      <div className="mb-6 flex items-center gap-3 p-3 bg-gray-900 rounded-lg border border-gray-700">
        <span className="text-sm text-gray-400 shrink-0">Active brand:</span>
        {brands.length === 0 ? (
          <span className="text-sm text-gray-500 italic">No brands found — set one up in Brand Settings first.</span>
        ) : (
          <div className="flex flex-wrap gap-2">
            {brands.map((b) => (
              <button
                key={b.brand_name}
                onClick={() => {
                  setSelectedBrand(b.brand_name)
                  localStorage.setItem("activeBrandName", b.brand_name)
                }}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm border transition-all ${
                  selectedBrand === b.brand_name
                    ? "border-purple-500 bg-purple-900/40 text-purple-200"
                    : "border-gray-600 text-gray-400 hover:border-gray-400"
                }`}
              >
                {b.logo_url && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={b.logo_url} alt="" className="w-4 h-4 rounded-full object-cover" />
                )}
                {b.brand_name}
                {selectedBrand === b.brand_name && <span className="text-purple-400">✓</span>}
              </button>
            ))}
          </div>
        )}
        {selectedBrand && (
          <span className="ml-auto text-xs text-purple-400 shrink-0">Using: <strong>{selectedBrand}</strong></span>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 bg-gray-900 p-1 rounded-lg w-fit flex-wrap">
        {(["schedules", "post-now", "history", "media"] as const).map((t) => {
          const icons: Record<string, React.ReactNode> = {
            "schedules": <Calendar className="h-4 w-4 inline mr-1" />,
            "post-now": <Send className="h-4 w-4 inline mr-1" />,
            "history": <History className="h-4 w-4 inline mr-1" />,
            "media": <ImageIcon className="h-4 w-4 inline mr-1" />,
          }
          const labels: Record<string, string> = { "schedules": "Schedules", "post-now": "Post Now", "history": "Post History", "media": "Media" }
          return (
            <button key={t} onClick={() => setTab(t)}
              className={`px-4 py-2 rounded text-sm font-medium transition-all ${tab === t ? "bg-gray-700 text-white" : "text-gray-400 hover:text-white"}`}
            >{icons[t]}{labels[t]}</button>
          )
        })}
      </div>

      {msg && (
        <div className={`mb-4 px-4 py-2 rounded text-sm ${msg.includes("!") ? "bg-green-900 text-green-300" : "bg-red-900 text-red-300"}`}>{msg}</div>
      )}

      {/* â”€â”€ Schedules tab â”€â”€â”€ */}
      {tab === "schedules" && (
        <div className="grid grid-cols-12 gap-6">
          <div className="col-span-4">
            <Card className="bg-gray-900 border-gray-700">
              <CardHeader><CardTitle className="text-base flex items-center gap-2"><Plus className="h-4 w-4" />New Schedule</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-1">
                  <Label>Schedule Name</Label>
                  <Input value={sName} onChange={(e) => setSName(e.target.value)} placeholder="Weekly LinkedIn post" className="bg-gray-800 border-gray-600" />
                </div>
                <div className="space-y-1">
                  <Label>Platform</Label>
                  <Select value={sPlatform} onValueChange={setSPlatform}>
                    <SelectTrigger className="bg-gray-800 border-gray-600"><SelectValue /></SelectTrigger>
                    <SelectContent>{PLATFORMS.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label>Campaign Topic / Brief</Label>
                  <Textarea value={sContent} onChange={(e) => setSContent(e.target.value)} rows={4}
                    placeholder={sAiGenerate ? "Describe what this campaign is about. AI will write the post and generate an image each time it runs." : "Write the exact post content to be published…"}
                    className="bg-gray-800 border-gray-600 text-sm" />
                </div>
                {/* AI Generate toggle */}
                <div className="flex items-center justify-between p-3 rounded-lg bg-gray-800 border border-gray-600">
                  <div>
                    <p className="text-sm font-medium">AI generate content &amp; image</p>
                    <p className="text-xs text-gray-500">Each run: Groq writes the post, RunwayML makes the image</p>
                  </div>
                  <button
                    onClick={() => setSAiGenerate(!sAiGenerate)}
                    className={`relative w-11 h-6 rounded-full transition-colors ${
                      sAiGenerate ? "bg-purple-600" : "bg-gray-600"
                    }`}
                  >
                    <span className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${
                      sAiGenerate ? "translate-x-5" : "translate-x-0"
                    }`} />
                  </button>
                </div>
                <div className="space-y-1">
                  <Label>Trigger Type</Label>
                  <div className="flex gap-2">
                    {(["once", "recurring"] as const).map((tt) => (
                      <button key={tt} onClick={() => setSTrigger(tt)}
                        className={`flex-1 py-2 rounded text-sm border transition-all ${sTrigger === tt ? "border-purple-500 bg-purple-900/30 text-purple-200" : "border-gray-600 text-gray-400 hover:border-gray-400"}`}
                      >{tt === "once" ? <><Clock className="h-4 w-4 inline mr-1" />One-off</> : <><RotateCw className="h-4 w-4 inline mr-1" />Recurring</>}</button>
                    ))}
                  </div>
                </div>
                {sTrigger === "once" ? (
                  <div className="space-y-1"><Label>Run At</Label><Input type="datetime-local" value={sRunAt} onChange={(e) => setSRunAt(e.target.value)} className="bg-gray-800 border-gray-600" /></div>
                ) : (
                  <div className="space-y-1">
                    <Label>Cron Expression</Label>
                    <Input value={sCron} onChange={(e) => setSCron(e.target.value)} placeholder="0 9 * * 1 (Mon 9am)" className="bg-gray-800 border-gray-600 font-mono text-sm" />
                    <p className="text-xs text-gray-500">Standard cron: min hour day month weekday</p>
                    <div className="pt-2">
                      <Label>Run For (Days)</Label>
                      <Input
                        type="number"
                        min="1"
                        max="365"
                        value={sRecurringDays}
                        onChange={(e) => setSRecurringDays(e.target.value)}
                        placeholder="7"
                        className="bg-gray-800 border-gray-600"
                      />
                      <p className="text-xs text-gray-500">After this many days, recurring schedule stops automatically.</p>
                    </div>
                  </div>
                )}
                <Button onClick={createSchedule} disabled={loading} className="w-full bg-green-600 hover:bg-green-700">{loading ? "Schedulingâ€¦" : "Create Schedule"}</Button>
              </CardContent>
            </Card>
          </div>
          <div className="col-span-8 space-y-3">
            <div className="flex items-center justify-between mb-2">
              <p className="text-sm text-gray-400">{schedules.length} schedule(s)</p>
              <Button variant="ghost" size="sm" onClick={() => fetchSchedules()}><RotateCw className="h-3 w-3 mr-1" />Refresh</Button>
            </div>
            {schedules.length === 0 && (
              <Card className="bg-gray-900 border-gray-700 text-center py-10"><CardContent><p className="text-gray-500">No schedules yet.</p></CardContent></Card>
            )}
            {schedules.map((s) => {
              const displayPlatform = s.display_platform || s.platform
              const runs = s.run_history || []
              const isExpanded = expandedSchedule === s.id
              return (
              <Card key={s.id} className="bg-gray-900 border-gray-700">
                <CardContent className="p-4">
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        <p className="font-medium">{s.name}</p>
                        <Badge className={`${PLATFORM_COLORS[displayPlatform] || "bg-gray-600"} text-white text-xs`}>{displayPlatform}</Badge>
                        <Badge className={`${statusColor(s.status)} text-white text-xs`}>{s.status}</Badge>
                        <Badge variant="outline" className="text-xs">{s.trigger_type}</Badge>
                        {s.ai_generate && <Badge className="bg-purple-700 text-white text-xs">AI</Badge>}
                        {s.brand_name && <Badge className="bg-indigo-800 text-indigo-200 text-xs">{s.brand_name}</Badge>}
                      </div>
                      <p className="text-sm text-gray-400 line-clamp-2">{s.content_template || s.content_text}</p>
                      <div className="flex flex-wrap gap-3 mt-2 text-xs text-gray-500">
                        {s.run_at && <span><Clock className="h-3 w-3 inline mr-0.5" />{new Date(s.run_at).toLocaleString()}</span>}
                        {s.cron_expr && <span className="font-mono">cron: {s.cron_expr}</span>}
                        {(s.run_count ?? 0) > 0 && <span className="text-green-500">{s.run_count} run(s)</span>}
                        {s.last_run && <span>Last run: {new Date(s.last_run).toLocaleString()}</span>}
                        {s.next_run && <span>Next: {new Date(s.next_run).toLocaleString()}</span>}
                        {runs.length > 0 && (
                          <button onClick={() => setExpandedSchedule(isExpanded ? null : s.id)}
                            className="text-blue-400 hover:underline">
                            {isExpanded ? "Hide" : "View"} run history ({runs.length})
                          </button>
                        )}
                      </div>
                      {/* Run history */}
                      {isExpanded && runs.length > 0 && (
                        <div className="mt-3 space-y-1 border-t border-gray-700 pt-3">
                          {runs.map((run, i) => (
                            <div key={i} className="flex items-center gap-2 text-xs">
                              <Badge className={`${run.status === "completed" ? "bg-green-700" : "bg-red-700"} text-white`}>
                                {run.status}
                              </Badge>
                              <span className="text-gray-500">{new Date(run.ran_at).toLocaleString()}</span>
                              {run.post_url && (
                                <a href={run.post_url} target="_blank" rel="noreferrer"
                                  className="text-blue-400 hover:underline flex items-center gap-0.5">
                                  <ExternalLink className="h-3 w-3" />view post
                                </a>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                    {s.status === "active" && (
                      <Button variant="ghost" size="sm" onClick={() => cancelSchedule(s.id)} className="text-red-400 hover:text-red-300 shrink-0 ml-2"><Trash2 className="h-4 w-4" /></Button>
                    )}
                  </div>
                </CardContent>
              </Card>
              )
            })}
          </div>
        </div>
      )}

      {/* â”€â”€ Post Now tab â”€â”€â”€ */}
      {tab === "post-now" && (
        <div className="max-w-xl space-y-5">
          <Card className="bg-gray-900 border-gray-700">
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2"><Send className="h-4 w-4 text-green-400" />Post Immediately</CardTitle>
              <CardDescription>Skip the queue â€” publish to your selected platform right now.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1">
                <Label>Platform</Label>
                <Select value={pPlatform} onValueChange={setPPlatform}>
                  <SelectTrigger className="bg-gray-800 border-gray-600"><SelectValue /></SelectTrigger>
                  <SelectContent>{PLATFORMS.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label>Campaign Topic / Brief</Label>
                <Textarea value={pContent} onChange={(e) => setPContent(e.target.value)} rows={6}
                  placeholder={pAiGenerate ? "Describe the campaign — AI will write the post and generate an image before publishing." : "Write the exact post content…"}
                  className="bg-gray-800 border-gray-600" />
              </div>
              {/* AI Generate toggle */}
              <div className="flex items-center justify-between p-3 rounded-lg bg-gray-800 border border-gray-600">
                <div>
                  <p className="text-sm font-medium">AI generate content &amp; image</p>
                  <p className="text-xs text-gray-500">Groq writes the post • RunwayML generates a visual</p>
                </div>
                <button
                  onClick={() => setPAiGenerate(!pAiGenerate)}
                  className={`relative w-11 h-6 rounded-full transition-colors ${
                    pAiGenerate ? "bg-purple-600" : "bg-gray-600"
                  }`}
                >
                  <span className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${
                    pAiGenerate ? "translate-x-5" : "translate-x-0"
                  }`} />
                </button>
              </div>
              <Button onClick={postNow} disabled={loading || !pContent} className="w-full bg-green-600 hover:bg-green-700">
                {loading ? "Postingâ€¦" : <><Send className="h-4 w-4 mr-1" />Post to {pPlatform}</>}
              </Button>
            </CardContent>
          </Card>

          {postResult && (
            <Card className="bg-gray-900 border-gray-700">
              <CardContent className="p-4 space-y-3">
                <div className="flex items-center gap-2">
                  <Badge className={postResult.status === "completed" ? "bg-green-600" : postResult.status === "failed" ? "bg-red-700" : "bg-yellow-600"}>
                    {postResult.status}
                  </Badge>
                  <span className="text-sm font-mono text-gray-400">{postResult.job_id}</span>
                </div>

                {/* AI-generated preview */}
                {(postResult.generated_content || postResult.generated_image_url) && (
                  <div className="rounded-lg border border-purple-700 bg-purple-950/30 p-3 space-y-3">
                    <p className="text-xs font-semibold text-purple-400 uppercase tracking-wide">AI Generated Preview</p>
                    {postResult.generated_image_url && (
                      <a href={postResult.generated_image_url} target="_blank" rel="noreferrer">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={postResult.generated_image_url} alt="Generated" className="w-full max-h-64 object-cover rounded border border-purple-800" />
                      </a>
                    )}
                    {postResult.generated_content && (
                      <p className="text-sm text-gray-200 whitespace-pre-wrap">{postResult.generated_content}</p>
                    )}
                  </div>
                )}

                {postResult.post_url && (
                  <a href={postResult.post_url} target="_blank" rel="noreferrer"
                    className="flex items-center gap-1 text-sm text-blue-400 hover:underline break-all">
                    <ExternalLink className="h-3 w-3 shrink-0" />{postResult.post_url}
                  </a>
                )}
                {postResult.error && <p className="text-sm text-red-400">{postResult.error}</p>}
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* â”€â”€ History tab â”€â”€â”€ */}
      {tab === "history" && (
        <div className="space-y-3">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm text-gray-400">{campaignHistory.length} campaign(s)</p>
            <Button variant="ghost" size="sm" onClick={fetchCampaignHistory}><RotateCw className="h-3 w-3 mr-1" />Refresh Campaigns</Button>
          </div>
          {campaignHistory.length === 0 ? (
            <Card className="bg-gray-900 border-gray-700 text-center py-10">
              <CardContent><p className="text-gray-500">No campaign history yet. Create a campaign plan from chat and activate a tier.</p></CardContent>
            </Card>
          ) : (
            campaignHistory.map((c) => (
              <Card key={c.id} className="bg-gray-900 border-gray-700">
                <CardContent className="p-4">
                  <div className="flex items-start justify-between gap-3 flex-wrap">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="font-medium">{c.name}</p>
                        <Badge className={`${statusColor(c.status)} text-white text-xs`}>{c.status}</Badge>
                        {c.budget_tier && <Badge className="bg-indigo-700 text-white text-xs">{c.budget_tier}</Badge>}
                      </div>
                      <p className="text-xs text-gray-500">Created: {new Date(c.created_at).toLocaleString()}</p>
                      <div className="flex flex-wrap gap-3 text-xs text-gray-400">
                        {c.start_date && <span>Start: {new Date(c.start_date).toLocaleDateString()}</span>}
                        {c.end_date && <span>End: {new Date(c.end_date).toLocaleDateString()}</span>}
                        <span>Agenda: {c.agenda_completed || 0}/{c.agenda_total || 0} completed</span>
                        {(c.agenda_failed || 0) > 0 && <span className="text-red-400">Failed: {c.agenda_failed}</span>}
                        {(c.agenda_pending || 0) > 0 && <span className="text-yellow-400">Pending: {c.agenda_pending}</span>}
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))
          )}

          <div className="h-px bg-gray-800 my-3" />
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm text-gray-400">{postHistory.length} post(s)</p>
            <Button variant="ghost" size="sm" onClick={fetchHistory}><RotateCw className="h-3 w-3 mr-1" />Refresh</Button>
          </div>
          {postHistory.length === 0 && (
            <Card className="bg-gray-900 border-gray-700 text-center py-10">
              <CardContent><p className="text-gray-500">No posts yet. Use "Post Now" to publish something.</p></CardContent>
            </Card>
          )}
          {postHistory.map((p, idx) => (
            <Card key={`${p.job_id}-${idx}`} className="bg-gray-900 border-gray-700">
              <CardContent className="p-4">
                <div className="flex items-start gap-4">
                  {/* generated image */}
                  {p.image_url && (
                    <a href={p.image_url} target="_blank" rel="noreferrer" className="shrink-0">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={p.image_url} alt="" className="w-28 h-20 object-cover rounded border border-gray-700 hover:border-purple-500 transition-colors" />
                    </a>
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <Badge className={`${PLATFORM_COLORS[p.platform] || "bg-gray-600"} text-white text-xs`}>{p.platform}</Badge>
                      <Badge className={`${p.status === "completed" ? "bg-green-600" : "bg-red-700"} text-white text-xs`}>{p.status}</Badge>
                      {p.ai_generated && <Badge className="bg-purple-700 text-white text-xs">AI</Badge>}
                      <span className="text-xs text-gray-500">{new Date(p.posted_at).toLocaleString()}</span>
                    </div>
                    {p.topic && p.topic !== p.content_snippet && (
                      <p className="text-xs text-gray-500 italic mb-1">Topic: {p.topic}</p>
                    )}
                    <p className="text-sm text-gray-300 whitespace-pre-wrap">{p.content_snippet}</p>
                    {p.post_url && (
                      <a href={p.post_url} target="_blank" rel="noreferrer"
                        className="flex items-center gap-1 text-xs text-blue-400 hover:underline mt-1 break-all">
                        <ExternalLink className="h-3 w-3 shrink-0" />{p.post_url}
                      </a>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* â”€â”€ Media tab â”€â”€â”€ */}
      {tab === "media" && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm text-gray-400">{images.length} image(s) generated</p>
            <Button variant="ghost" size="sm" onClick={fetchImages}><RotateCw className="h-3 w-3 mr-1" />Refresh</Button>
          </div>
          {images.length === 0 && (
            <Card className="bg-gray-900 border-gray-700 text-center py-10">
              <CardContent><p className="text-gray-500">No images yet. Ask the AI to generate an image in the chat.</p></CardContent>
            </Card>
          )}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            {images.map((img) => (
              <Card key={img.filename} className="bg-gray-900 border-gray-700 overflow-hidden group">
                <div className="aspect-video bg-gray-800 relative overflow-hidden">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={`${ORCHESTRATOR}${img.url}`}
                    alt={img.filename}
                    className="w-full h-full object-cover"
                    onError={(e) => { (e.currentTarget as HTMLImageElement).src = "" }}
                  />
                  <a href={`${ORCHESTRATOR}${img.url}`} target="_blank" rel="noreferrer"
                    className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                    <ExternalLink className="h-6 w-6 text-white" />
                  </a>
                </div>
                <CardContent className="p-2">
                  <p className="text-xs text-gray-400 truncate">{img.filename}</p>
                  <p className="text-xs text-gray-600">{new Date(img.created_at).toLocaleDateString()}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
