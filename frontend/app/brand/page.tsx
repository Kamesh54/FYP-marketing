"use client"

import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { ArrowLeft, Building2, Globe, Palette, Wand2, Save, Trash2, Plus } from "lucide-react"
import Link from "next/link"

const API_BASE = "http://127.0.0.1:8004"
const BRAND_API = "http://127.0.0.1:8006"

interface BrandProfile {
  id?: number
  brand_name: string
  description: string
  target_audience: string
  tone: string
  industry: string
  tagline: string
  website_url: string
  colors: string[]
  fonts: string[]
  tone_preference: string
  auto_extracted?: boolean
  logo_url?: string
  unique_selling_points?: string[]
}

const emptyBrand: BrandProfile = {
  brand_name: "",
  description: "",
  target_audience: "",
  tone: "professional",
  industry: "",
  tagline: "",
  website_url: "",
  colors: [],
  fonts: [],
  tone_preference: "",
}

/** Coerce null/undefined fields to safe defaults so <Input value={}> never gets null */
function normalizeBrand(b: any): BrandProfile {
  // Pull extra fields from metadata blob if present
  const meta = b.metadata && typeof b.metadata === "object" ? b.metadata : {}
  const usps: string[] = (
    b.unique_selling_points ?? meta.unique_selling_points ?? []
  ).filter(Boolean)
  return {
    id: b.id,
    brand_name: b.brand_name || "",
    description: b.description || meta.description || "",
    target_audience: b.target_audience || meta.target_audience || "",
    tone: b.tone || "professional",
    industry: b.industry || meta.industry || "",
    tagline: b.tagline || "",
    website_url: b.website_url || meta.website || "",
    colors: Array.isArray(b.colors) ? b.colors : [],
    fonts: Array.isArray(b.fonts) ? b.fonts : [],
    tone_preference: b.tone_preference || "",
    auto_extracted: Boolean(b.auto_extracted),
    logo_url: b.logo_url || meta?.assets?.logo?.[0]?.url || "",
    unique_selling_points: usps,
  }
}

export default function BrandPage() {
  const [brands, setBrands] = useState<BrandProfile[]>([])
  const [selected, setSelected] = useState<BrandProfile | null>(null)
  const [form, setForm] = useState<BrandProfile>(emptyBrand)
  const [extractUrl, setExtractUrl] = useState("")
  const [extracting, setExtracting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState("")
  const [userId, setUserId] = useState<number | null>(null)
  const [token, setToken] = useState("")

  useEffect(() => {
    const t = localStorage.getItem("authToken")
    const uid = localStorage.getItem("userId")
    if (t) setToken(t)
    setUserId(uid ? parseInt(uid) : 1)
  }, [])

  useEffect(() => {
    if (userId) {
      fetchBrands()
      // Refresh whenever the tab gets focus (e.g. after chatting in main page)
      const onFocus = () => fetchBrands()
      window.addEventListener("focus", onFocus)
      return () => window.removeEventListener("focus", onFocus)
    }
  }, [userId])

  async function fetchBrands() {
    if (!userId) return
    try {
      // Try brand_agent (8006) first
      const r = await fetch(`${BRAND_API}/brands/${userId}`)
      if (r.ok) {
        const data = await r.json()
        const normalized = (data.brands || []).map(normalizeBrand)
        setBrands(normalized)
        // Auto-select: prefer previously active brand, else first
        const savedBrandName = localStorage.getItem("activeBrandName")
        const toSelect = normalized.find((b: BrandProfile) => b.brand_name === savedBrandName) || normalized[0]
        if (toSelect) {
          setSelected(toSelect)
          setForm(toSelect)
          localStorage.setItem("activeBrandName", toSelect.brand_name)
        }
        return
      }
    } catch (_) {}
    // Fallback: orchestrator /brand-profile (returns single profile)
    try {
      const headers: Record<string, string> = {}
      const t = localStorage.getItem("authToken")
      if (t) headers["Authorization"] = `Bearer ${t}`
      const r = await fetch(`${API_BASE}/brand-profile`, { headers })
      if (r.ok) {
        const data = await r.json()
        if (data.profile) {
          const p = data.profile
          const meta = typeof p.metadata === "string"
            ? JSON.parse(p.metadata || "{}")
            : (p.metadata || {})
          const single = normalizeBrand({ ...meta, ...p, metadata: undefined })
          setBrands([single])
          setSelected(single)
          setForm(single)
        }
      }
    } catch (e) {
      console.error("fetchBrands failed:", e)
    }
  }

  function selectBrand(b: BrandProfile) {
    setSelected(b)
    setForm(normalizeBrand(b))
    localStorage.setItem("activeBrandName", b.brand_name)
  }

  function newBrand() {
    setSelected(null)
    setForm({ ...emptyBrand })
  }

  async function saveBrand() {
    if (!userId || !form.brand_name) return
    setSaving(true)
    setMsg("")
    try {
      const method = selected ? "PUT" : "POST"
      const url = selected
        ? `${BRAND_API}/brand/${userId}/${encodeURIComponent(selected.brand_name)}`
        : `${BRAND_API}/brand`
      const body = selected
        ? form
        : { user_id: userId, ...form }
      const r = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })
      if (r.ok) {
        setMsg("Brand saved successfully!")
        fetchBrands()
      } else {
        setMsg("Save failed: " + (await r.text()))
      }
    } catch (e: any) {
      setMsg("Error: " + e.message)
    }
    setSaving(false)
  }

  async function deleteBrand() {
    if (!userId || !selected) return
    if (!confirm(`Delete brand "${selected.brand_name}"?`)) return
    try {
      await fetch(`${BRAND_API}/brand/${userId}/${encodeURIComponent(selected.brand_name)}`, {
        method: "DELETE",
      })
      setSelected(null)
      setForm({ ...emptyBrand })
      fetchBrands()
    } catch (e) {
      console.error(e)
    }
  }

  async function autoExtract() {
    if (!userId || !extractUrl) return
    setExtracting(true)
    setMsg("")
    try {
      const r = await fetch(`${BRAND_API}/brand/extract`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId,
          brand_name: form.brand_name || extractUrl.replace(/https?:\/\//, "").split("/")[0],
          website_url: extractUrl,
        }),
      })
      if (r.ok) {
        const data = await r.json()
        setMsg("Brand auto-extracted and saved!")
        fetchBrands()
        const extracted = data.extracted_data || {}
        const resolvedName = data.brand_name || form.brand_name || extractUrl.replace(/https?:\/\//, "").split("/")[0]
        setForm((f) => ({
          ...f,
          ...extracted,
          brand_name: resolvedName,
          website_url: extractUrl,
          logo_url: data.logo_url || extracted.logo_url || f.logo_url || "",
          colors: (data.colors && data.colors.length > 0) ? data.colors : (extracted.colors || f.colors),
        }))
        localStorage.setItem("activeBrandName", resolvedName)
      } else {
        setMsg("Extraction failed")
      }
    } catch (e: any) {
      setMsg("Error: " + e.message)
    }
    setExtracting(false)
  }

  const addColor = () => setForm((f) => ({ ...f, colors: [...f.colors, "#000000"] }))
  const removeColor = (i: number) =>
    setForm((f) => ({ ...f, colors: f.colors.filter((_, idx) => idx !== i) }))
  const updateColor = (i: number, v: string) =>
    setForm((f) => ({ ...f, colors: f.colors.map((c, idx) => (idx === i ? v : c)) }))

  return (
    <div className="min-h-screen bg-gray-950 text-white p-6 overflow-y-auto">
      {/* Header */}
      <div className="flex items-center gap-4 mb-8">
        <Link href="/">
          <Button variant="ghost" size="sm"><ArrowLeft className="h-4 w-4 mr-1" />Back</Button>
        </Link>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Building2 className="h-6 w-6 text-purple-400" />
          Brand Profiles
        </h1>
      </div>

      <div className="grid grid-cols-12 gap-6">
        {/* Sidebar — brand list */}
        <div className="col-span-3 space-y-3">
          <Button onClick={newBrand} size="sm" className="w-full bg-purple-600 hover:bg-purple-700">
            <Plus className="h-4 w-4 mr-1" />New Brand
          </Button>
          {brands.map((b) => (
            <Card
              key={b.brand_name}
              className={`cursor-pointer border transition-all ${
                selected?.brand_name === b.brand_name
                  ? "border-purple-500 bg-gray-800"
                  : "border-gray-700 bg-gray-900 hover:border-gray-500"
              }`}
              onClick={() => selectBrand(b)}
            >
              <CardContent className="p-3">
                <div className="flex items-center gap-2">
                  {b.logo_url && (
                    <img src={b.logo_url} alt="" className="w-8 h-8 rounded object-contain bg-gray-800 border border-gray-700 p-0.5 shrink-0" />
                  )}
                  <div className="min-w-0">
                    <p className="font-medium text-sm truncate">{b.brand_name}</p>
                    <p className="text-xs text-gray-400 truncate">{b.industry || "No industry"}</p>
                  </div>
                </div>
                {b.auto_extracted && (
                  <Badge variant="secondary" className="text-xs mt-1">Auto-extracted</Badge>
                )}
              </CardContent>
            </Card>
          ))}
          {brands.length === 0 && (
            <p className="text-gray-500 text-sm text-center py-4">No brands yet.</p>
          )}
        </div>

        {/* Form */}
        <div className="col-span-9">
          <Card className="bg-gray-900 border-gray-700">
            <CardHeader>
              <div className="flex items-center gap-4">
                {form.logo_url && (
                  <img src={form.logo_url} alt="logo" className="w-14 h-14 rounded-lg object-contain bg-gray-800 border border-gray-700 p-1" />
                )}
                <div>
                  <CardTitle>{selected ? `Edit: ${selected.brand_name}` : "New Brand"}</CardTitle>
                  <CardDescription>
                    {selected ? `${selected.industry || ""} · ${selected.auto_extracted ? "Auto-extracted" : "Manual"}` : "Fill in the form manually or auto-extract from a URL."}
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-5">
              {/* Auto-extract */}
              <div className="flex gap-2 p-3 bg-gray-800 rounded-lg">
                <Globe className="h-4 w-4 text-blue-400 mt-2.5 shrink-0" />
                <Input
                  placeholder="https://yourbrand.com — auto-extract brand signals"
                  value={extractUrl}
                  onChange={(e) => setExtractUrl(e.target.value)}
                  className="bg-gray-700 border-gray-600 flex-1"
                />
                <Button
                  onClick={autoExtract}
                  disabled={extracting || !extractUrl}
                  className="bg-blue-600 hover:bg-blue-700 shrink-0"
                >
                  {extracting ? "Extracting…" : <><Wand2 className="h-4 w-4 mr-1" />Extract</>}
                </Button>
              </div>

              {/* Basic fields */}
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <Label>Brand Name *</Label>
                  <Input value={form.brand_name} onChange={(e) => setForm((f) => ({ ...f, brand_name: e.target.value }))} className="bg-gray-800 border-gray-600" />
                </div>
                <div className="space-y-1">
                  <Label>Industry</Label>
                  <Input value={form.industry} onChange={(e) => setForm((f) => ({ ...f, industry: e.target.value }))} placeholder="e.g. beauty, saas, fintech" className="bg-gray-800 border-gray-600" />
                </div>
                <div className="space-y-1">
                  <Label>Tagline</Label>
                  <Input value={form.tagline} onChange={(e) => setForm((f) => ({ ...f, tagline: e.target.value }))} className="bg-gray-800 border-gray-600" />
                </div>
                <div className="space-y-1">
                  <Label>Tone</Label>
                  <Select value={form.tone} onValueChange={(v) => setForm((f) => ({ ...f, tone: v }))}>
                    <SelectTrigger className="bg-gray-800 border-gray-600"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {["professional","casual","playful","authoritative","inspirational"].map((t) => (
                        <SelectItem key={t} value={t}>{t}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="space-y-1">
                <Label>Description</Label>
                <Textarea value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} rows={3} className="bg-gray-800 border-gray-600" />
              </div>

              <div className="space-y-1">
                <Label>Target Audience</Label>
                <Input value={form.target_audience} onChange={(e) => setForm((f) => ({ ...f, target_audience: e.target.value }))} className="bg-gray-800 border-gray-600" />
              </div>

              <div className="space-y-1">
                <Label>Tone / Writing Style (adjectives)</Label>
                <Input value={form.tone_preference} onChange={(e) => setForm((f) => ({ ...f, tone_preference: e.target.value }))} placeholder="e.g. warm, witty, direct" className="bg-gray-800 border-gray-600" />
              </div>

              <div className="space-y-1">
                <Label>Website URL</Label>
                <Input value={form.website_url} onChange={(e) => setForm((f) => ({ ...f, website_url: e.target.value }))} placeholder="https://yourbrand.com" className="bg-gray-800 border-gray-600" />
              </div>

              {/* Unique Selling Points */}
              {(form.unique_selling_points?.length ?? 0) > 0 && (
                <div className="space-y-2">
                  <Label>Unique Selling Points</Label>
                  <ul className="space-y-1">
                    {form.unique_selling_points!.map((usp, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-gray-300">
                        <span className="text-purple-400 mt-0.5">✦</span>
                        {usp}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Logo URL */}
              <div className="space-y-1">
                <Label>Logo URL</Label>
                <Input value={form.logo_url || ""} onChange={(e) => setForm((f) => ({ ...f, logo_url: e.target.value }))} placeholder="https://…/logo.png" className="bg-gray-800 border-gray-600" />
              </div>

              {/* Brand colors */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label className="flex items-center gap-1"><Palette className="h-4 w-4" />Brand Colors</Label>
                  <Button variant="ghost" size="sm" onClick={addColor}><Plus className="h-3 w-3" /></Button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {form.colors.map((c, i) => (
                    <div key={i} className="flex items-center gap-1">
                      <input type="color" value={c} onChange={(e) => updateColor(i, e.target.value)} className="w-8 h-8 rounded cursor-pointer border-0 bg-transparent" />
                      <span className="text-xs text-gray-400">{c}</span>
                      <button onClick={() => removeColor(i)} className="text-red-400 hover:text-red-300 text-xs">×</button>
                    </div>
                  ))}
                  {form.colors.length === 0 && <p className="text-xs text-gray-500">No colors added.</p>}
                </div>
              </div>

              {/* Actions */}
              {msg && <p className={`text-sm ${msg.includes("success") ? "text-green-400" : "text-red-400"}`}>{msg}</p>}

              <div className="flex gap-3 pt-2">
                <Button onClick={saveBrand} disabled={saving || !form.brand_name} className="bg-purple-600 hover:bg-purple-700">
                  {saving ? "Saving…" : <><Save className="h-4 w-4 mr-1" />Save Brand</>}
                </Button>
                {selected && (
                  <Button variant="destructive" onClick={deleteBrand}>
                    <Trash2 className="h-4 w-4 mr-1" />Delete
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
