"use client"

import type React from "react"

import { useState, useEffect, useRef } from "react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import {
  Send,
  Plus,
  LogOut,
  Menu,
  X,
  Upload,
  Eye,
  Sparkles,
  Check,
  RotateCw,
  XCircle,
  Trash2,
  ImageIcon,
  Settings,
  BarChart3,
  Instagram,
  Twitter,
  MessageSquare,
  Calendar,
  TrendingUp,
  Bell,
  Building2,
  Search,
  Zap,
} from "lucide-react"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { messageFormatter } from "@/lib/message-formatter"
import Link from "next/link"

const API_BASE_URL = "http://127.0.0.1:8004"

interface Message {
  role: "user" | "assistant"
  content: string
  timestamp?: string
  responseOptions?: WorkflowOption[]
  selectedOption?: { label: string; content_id: string }
}

interface WorkflowOption {
  option_id: string
  label: string
  tone?: string
  cost_display?: string
  workflow_name?: string
  preview_text?: string
  preview_url?: string
  workflow_agents?: string[]
  content_id?: string
  content_type?: string
  twitter_copy?: string
  instagram_copy?: string
  hashtags?: string[]
  critic?: {
    overall: number
    intent: number
    brand: number
    quality: number
    passed: boolean
    text: string
  }
}

interface ContentPreview {
  content_id: string
  type: "blog" | "post"
}

// ADDED interface for content details
interface ContentDetails {
  content: string
  preview_url?: string
  metadata?: {
    image_path?: string
  }
}

interface Session {
  id: string
  title: string
}

interface Asset {
  url: string
  filename: string
  uploaded_at: string
  size: number
  content_type: string
  asset_type: string
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [sessions, setSessions] = useState<Session[]>([])
  const [userEmail, setUserEmail] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)
  const [showUploadModal, setShowUploadModal] = useState(false)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [assetType, setAssetType] = useState("general")
  const [workflowOptions, setWorkflowOptions] = useState<WorkflowOption[]>([])
  const [workflowsDisabled, setWorkflowsDisabled] = useState(false)
  const [regeneratingCardId, setRegeneratingCardId] = useState<string | null>(null)
  const [currentTheme, setCurrentTheme] = useState("pulse")
  const [contentPreview, setContentPreview] = useState<ContentPreview | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [showAssetsModal, setShowAssetsModal] = useState(false)
  // ADDED state for content details
  const [contentDetails, setContentDetails] = useState<ContentDetails | null>(null)
  const [showManagerModal, setShowManagerModal] = useState(false)
  const [showPerformanceModal, setShowPerformanceModal] = useState(false)
  const [assets, setAssets] = useState<Asset[]>([])
  const [assetsLoading, setAssetsLoading] = useState(false)

  const [hitlCount, setHitlCount] = useState(0)
  const hitlPollerRef = useRef<NodeJS.Timeout | null>(null)

  const chatContainerRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    checkAuth()
  }, [])

  // Poll for pending HITL events every 5 seconds
  useEffect(() => {
    const sid = currentSessionId || localStorage.getItem("session_id") || "default"
    hitlPollerRef.current = setInterval(async () => {
      try {
        const r = await fetch(`${API_BASE_URL}/hitl/pending/${sid}`)
        if (r.ok) {
          const d = await r.json()
          setHitlCount((d.events || []).length)
        }
      } catch (_) {}
    }, 5000)
    return () => { if (hitlPollerRef.current) clearInterval(hitlPollerRef.current) }
  }, [currentSessionId])

  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight
    }
  }, [messages, workflowOptions, contentPreview])

  useEffect(() => {
    if (showAssetsModal) {
      fetchAssets()
    }
  }, [showAssetsModal])

  const checkAuth = async () => {
    const token = localStorage.getItem("authToken")
    if (!token) {
      window.location.href = "/login"
      return
    }

    try {
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), 5000)

      const response = await fetch(`${API_BASE_URL}/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
        signal: controller.signal,
      })

      clearTimeout(timeoutId)

      if (!response.ok) {
        throw new Error("Auth failed")
      }

      const user = await response.json()
      setUserEmail(user.email)
      await loadSessions()
    } catch (error) {
      console.error("Auth check failed:", error)
      localStorage.removeItem("authToken")
      window.location.href = "/login"
    }
  }

  const loadSessions = async () => {
    try {
      const token = localStorage.getItem("authToken")
      const response = await fetch(`${API_BASE_URL}/sessions`, {
        headers: { Authorization: `Bearer ${token}` },
      })

      const data = await response.json()
      setSessions(data.sessions || [])
    } catch (error) {
      console.error("Failed to load sessions:", error)
    }
  }

  const createNewSession = async () => {
    try {
      const token = localStorage.getItem("authToken")
      const response = await fetch(`${API_BASE_URL}/sessions/new`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      })

      const data = await response.json()
      setCurrentSessionId(data.session_id)
      setMessages([])
      setWorkflowOptions([])
      setWorkflowsDisabled(false)
      setContentPreview(null) // Clear content preview on new session
      setContentDetails(null) // Clear content details on new session
      await loadSessions()
    } catch (error) {
      console.error("Failed to create session:", error)
    }
  }

  const loadSession = async (sessionId: string) => {
    try {
      const token = localStorage.getItem("authToken")
      const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}/messages`, {
        headers: { Authorization: `Bearer ${token}` },
      })

      const data = await response.json()
      setCurrentSessionId(sessionId)
      setMessages(data.messages || [])
      setWorkflowOptions([])
      setWorkflowsDisabled(false)
      setContentPreview(null) // Clear content preview on session load
      setContentDetails(null) // Clear content details on session load
      await loadSessions()
    } catch (error) {
      console.error("Failed to load session:", error)
    }
  }

  const deleteSession = async (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation()

    if (!confirm("Delete this conversation?")) return

    try {
      const token = localStorage.getItem("authToken")
      await fetch(`${API_BASE_URL}/sessions/${sessionId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      })

      if (sessionId === currentSessionId) {
        setCurrentSessionId(null)
        setMessages([])
        setWorkflowOptions([])
        setContentPreview(null) // Clear content preview on session delete
        setContentDetails(null) // Clear content details on session delete
      }

      await loadSessions()
    } catch (error) {
      console.error("Failed to delete session:", error)
    }
  }

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return

    const userMessage = input.trim()
    setInput("")
    setMessages((prev) => [...prev, { role: "user", content: userMessage }])
    setIsLoading(true)
    setContentPreview(null) // Clear content preview on new user message
    setContentDetails(null) // Clear content details on new user message

    try {
      const token = localStorage.getItem("authToken")
      const response = await fetch(`${API_BASE_URL}/chat`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          session_id: currentSessionId,
          message: userMessage,
          active_brand: localStorage.getItem("activeBrandName") || undefined,
        }),
      })

      const data = await response.json()

      // Persist SEO audit data so the /seo page can display it immediately
      if (data.seo_result) {
        localStorage.setItem("lastSeoAudit", JSON.stringify({
          ...data.seo_result,
          audited_at: new Date().toISOString(),
        }))
      }

      const incomingOptions: WorkflowOption[] = data.response_options && data.response_options.length > 0
        ? data.response_options
        : []

      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.response, responseOptions: incomingOptions },
      ])

      if (data.session_id !== currentSessionId) {
        setCurrentSessionId(data.session_id)
        await loadSessions()
      }

      if (incomingOptions.length > 0) {
        setWorkflowOptions(incomingOptions)
        setWorkflowsDisabled(false)
      }
    } catch (error) {
      console.error("Send message error:", error)
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "âš ï¸ Connection error. Please check if the server is running.",
        },
      ])
    } finally {
      setIsLoading(false)
    }
  }

  // ADDED function to fetch and display content preview
  const fetchContentPreview = async (contentId: string, type: "blog" | "post") => {
    setPreviewLoading(true)
    try {
      const token = localStorage.getItem("authToken")
      const response = await fetch(`${API_BASE_URL}/content/${contentId}/details`, {
        headers: { Authorization: `Bearer ${token}` },
      })

      if (response.ok) {
        const details = await response.json()
        setContentDetails(details)
      }
    } catch (error) {
      console.error("Preview fetch error:", error)
    } finally {
      setPreviewLoading(false)
    }
  }

  const selectWorkflowOption = async (option: WorkflowOption) => {
    if (!option?.option_id || !currentSessionId || workflowsDisabled) return

    setWorkflowsDisabled(true)

    try {
      const token = localStorage.getItem("authToken")
      const response = await fetch(`${API_BASE_URL}/workflow/select`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          session_id: currentSessionId,
          option_id: option.option_id,
        }),
      })

      const data = await response.json()

      // Replace the cards in the message that contained this option with a "selected" chip
      setMessages((prev) =>
        prev.map((msg) => {
          if (msg.responseOptions?.some((o) => o.option_id === option.option_id)) {
            return {
              ...msg,
              responseOptions: undefined,
              selectedOption: { label: option.label, content_id: option.content_id ?? "" },
            }
          }
          return msg
        })
      )
      setWorkflowOptions([])

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.message || "Selection recorded.",
        },
      ])

      if (option.content_id && option.content_type) {
        const preview = {
          content_id: option.content_id,
          type: option.content_type as "blog" | "post",
        }
        setContentPreview(preview)
        await fetchContentPreview(option.content_id, option.content_type as "blog" | "post")
      }
    } catch (error) {
      console.error("Selection error:", error)
      setWorkflowsDisabled(false)
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Couldn't process selection. Please try again.",
        },
      ])
    }
  }

  const approveContent = async (contentId: string) => {
    try {
      const token = localStorage.getItem("authToken")
      const response = await fetch(`${API_BASE_URL}/content/${contentId}/approve`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ approved: true }),
      })

      const data = await response.json()
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `âœ… Content published successfully!\n\n${data.url ? `View at: ${data.url}` : ""}`,
        },
      ])
      setContentPreview(null)
      setContentDetails(null)
    } catch (error) {
      console.error("Approval error:", error)
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "âš ï¸ Failed to publish content. Please try again.",
        },
      ])
    }
  }

  const rejectContent = async (contentId: string) => {
    try {
      const token = localStorage.getItem("authToken")
      await fetch(`${API_BASE_URL}/content/${contentId}/approve`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ approved: false }),
      })

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Content cancelled.",
        },
      ])
      setContentPreview(null)
      setContentDetails(null)
    } catch (error) {
      console.error("Reject error:", error)
    }
  }

  const regenerateContent = async (contentId: string) => {
    setMessages((prev) => [
      ...prev,
      {
        role: "assistant",
        content: "Regenerating content...",
      },
    ])
    setContentPreview(null)
    setContentDetails(null)
  }

  const regenerateCardImage = async (contentId: string) => {
    if (!contentId) return
    setRegeneratingCardId(contentId)
    try {
      const token = localStorage.getItem("authToken")
      const res = await fetch(`${API_BASE_URL}/content/${contentId}/regenerate-image`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      // Update the card in both the messages array (inline cards) and workflowOptions (legacy)
      const patchOptions = (opts: WorkflowOption[]) =>
        opts.map((opt) =>
          opt.content_id === contentId ? { ...opt, preview_url: data.preview_url } : opt
        )
      setMessages((prev) =>
        prev.map((msg) =>
          msg.responseOptions
            ? { ...msg, responseOptions: patchOptions(msg.responseOptions) }
            : msg
        )
      )
      setWorkflowOptions((prev) => patchOptions(prev))
    } catch (err) {
      console.error("Regenerate image failed:", err)
    } finally {
      setRegeneratingCardId(null)
    }
  }

  const fetchAssets = async () => {
    try {
      setAssetsLoading(true)
      const token = localStorage.getItem("authToken")
      const response = await fetch(`${API_BASE_URL}/user/assets`, {
        headers: { Authorization: `Bearer ${token}` },
      })

      if (response.ok) {
        const data = await response.json()
        setAssets(data.assets || [])
      } else {
        console.error("Failed to fetch assets")
        setAssets([])
      }
    } catch (error) {
      console.error("Error fetching assets:", error)
      setAssets([])
    } finally {
      setAssetsLoading(false)
    }
  }

  const handleUpload = async () => {
    if (!uploadFile || !currentSessionId) return

    try {
      const token = localStorage.getItem("authToken")
      const formData = new FormData()
      formData.append("file", uploadFile)

      setMessages((prev) => [
        ...prev,
        {
          role: "user",
          content: `ðŸ“· Uploading ${uploadFile.name} as ${assetType}...`,
        },
      ])

      const response = await fetch(`${API_BASE_URL}/upload/${currentSessionId}?asset_type=${assetType}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      })

      const data = await response.json()

      if (data.s3_url) {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: `âœ… Image uploaded successfully!\n\n**Type:** ${assetType}\n**S3 URL:** ${data.s3_url}`,
          },
        ])
        // Refresh assets after successful upload
        await fetchAssets()
      } else {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: `âœ… Image uploaded successfully!\n\n**Type:** ${assetType}`,
          },
        ])
        // Refresh assets even if no S3 URL
        await fetchAssets()
      }

      setShowUploadModal(false)
      setUploadFile(null)
    } catch (error) {
      console.error("Upload error:", error)
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "âŒ Upload failed. Please try again.",
        },
      ])
    }
  }

  const logout = () => {
    localStorage.removeItem("authToken")
    localStorage.removeItem("userId")
    localStorage.removeItem("userEmail")
    window.location.href = "/login"
  }

  const switchTheme = (theme: string) => {
    setCurrentTheme(theme)
    document.body.className = document.body.className.replace(/theme-\w+/, `theme-${theme}`)
  }

  return (
    <>
      <div className="bg-elements">
        <div className="floating-cube"></div>
        <div className="floating-sphere"></div>
        <div className="floating-pyramid"></div>
        <div className="grid-floor"></div>
      </div>

      <div className="flex h-screen overflow-hidden relative z-10">
        {/* Sidebar */}
        <div
          className={`${
            isSidebarOpen ? "translate-x-0" : "-translate-x-full"
          } fixed lg:relative z-50 w-72 h-full glass-effect-strong transition-transform duration-300 animate-slide-in-left flex flex-col`}
        >
          <div className="p-4 border-b" style={{ borderColor: `rgba(var(--border), 0.5)` }}>
            <div className="flex items-center gap-3 mb-4">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center shadow-glow"
                style={{
                  background: `rgba(var(--primary), 0.2)`,
                  border: `2px solid rgba(var(--primary), 0.4)`,
                }}
              >
                <div className="grid grid-cols-3 grid-rows-2 gap-[3px] w-6 h-4">
                  {[...Array(6)].map((_, i) => (
                    <span
                      key={i}
                      className="neural-dot w-[6px] h-[6px] rounded-full"
                      style={{ backgroundColor: `rgba(var(--primary), 0.8)` }}
                    />
                  ))}
                </div>
              </div>
              <div>
                <h1 className="font-display text-xl font-bold text-gradient">Markx.pro</h1>
                <p className="text-xs" style={{ color: `rgba(var(--text-secondary), 1)` }}>
                  AI Platform
                </p>
              </div>
            </div>

            <Button onClick={createNewSession} className="w-full btn-primary border-0">
              <Plus className="w-4 h-4 mr-2" />
              New Chat
            </Button>
          </div>

          {/* Sessions List */}
          <div className="flex-1 overflow-y-auto p-2">
            {sessions.length === 0 ? (
              <p className="text-sm text-center py-8" style={{ color: `rgba(var(--text-disabled), 1)` }}>
                No conversations yet
              </p>
            ) : (
              sessions.map((session, index) => (
                <div
                  key={session.id}
                  onClick={() => loadSession(session.id)}
                  style={{
                    animationDelay: `${index * 50}ms`,
                    background: session.id === currentSessionId ? `rgba(var(--surface-hover), 0.6)` : "transparent",
                    borderColor: session.id === currentSessionId ? `rgba(var(--border), 0.8)` : "transparent",
                  }}
                  className={`
                    group relative p-3 mb-2 rounded-lg cursor-pointer border
                    transition-all duration-300 animate-fade-in nav-shine
                    hover:bg-opacity-60
                  `}
                >
                  <span className="text-sm block truncate pr-8" style={{ color: `rgba(var(--text-primary), 1)` }}>
                    {session.title}
                  </span>
                  <button
                    onClick={(e) => deleteSession(session.id, e)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity duration-200 p-1 rounded"
                    style={{
                      backgroundColor: "rgba(244, 67, 54, 0.2)",
                      color: "rgb(244, 67, 54)",
                    }}
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))
            )}
          </div>

          <div className="p-4 border-t space-y-3" style={{ borderColor: `rgba(var(--border), 0.5)` }}>
            {/* Theme Switcher */}
            <div>
              <label className="text-xs mb-2 block" style={{ color: `rgba(var(--text-secondary), 1)` }}>
                Theme
              </label>
              <Select value={currentTheme} onValueChange={switchTheme}>
                <SelectTrigger
                  className="w-full glass-effect"
                  style={{
                    borderColor: `rgba(var(--border), 0.5)`,
                    color: `rgba(var(--text-primary), 1)`,
                    background: `rgba(var(--surface), 0.4)`,
                  }}
                >
                  <SelectValue placeholder="Select theme" />
                </SelectTrigger>
                <SelectContent
                  style={{
                    background: `rgba(var(--surface), 0.95)`,
                    borderColor: `rgba(var(--border), 0.5)`,
                  }}
                >
                  {["pulse", "aurora", "midnight", "cyber"].map((theme) => (
                    <SelectItem key={theme} value={theme} className="capitalize">
                      {theme}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <Button
              onClick={() => setShowManagerModal(true)}
              variant="outline"
              className="w-full glass-effect"
              style={{
                borderColor: `rgba(var(--border), 0.5)`,
                color: `rgba(var(--text-primary), 1)`,
              }}
            >
              <Settings className="w-4 h-4 mr-2" />
              Manager
            </Button>

            <Button
              onClick={() => setShowPerformanceModal(true)}
              variant="outline"
              className="w-full glass-effect"
              style={{
                borderColor: `rgba(var(--border), 0.5)`,
                color: `rgba(var(--text-primary), 1)`,
              }}
            >
              <BarChart3 className="w-4 h-4 mr-2" />
              Performance
            </Button>

            <Button
              onClick={() => setShowAssetsModal(true)}
              variant="outline"
              className="w-full glass-effect"
              style={{
                borderColor: `rgba(var(--border), 0.5)`,
                color: `rgba(var(--text-primary), 1)`,
              }}
            >
              <Eye className="w-4 h-4 mr-2" />
              View Assets
            </Button>

            {/* Navigation Links */}
            <div className="space-y-1">
              <Link href="/brand">
                <Button variant="ghost" className="w-full justify-start text-sm" style={{ color: `rgba(var(--text-secondary), 1)` }}>
                  <Building2 className="w-4 h-4 mr-2" />Brands
                </Button>
              </Link>
              <Link href="/content">
                <Button variant="ghost" className="w-full justify-start text-sm" style={{ color: `rgba(var(--text-secondary), 1)` }}>
                  <Bell className="w-4 h-4 mr-2" />
                  Content Approval
                  {hitlCount > 0 && (
                    <span className="ml-auto bg-yellow-500 text-black text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center">
                      {hitlCount}
                    </span>
                  )}
                </Button>
              </Link>
              <Link href="/campaigns">
                <Button variant="ghost" className="w-full justify-start text-sm" style={{ color: `rgba(var(--text-secondary), 1)` }}>
                  <Calendar className="w-4 h-4 mr-2" />Campaigns
                </Button>
              </Link>
              <Link href="/analytics">
                <Button variant="ghost" className="w-full justify-start text-sm" style={{ color: `rgba(var(--text-secondary), 1)` }}>
                  <TrendingUp className="w-4 h-4 mr-2" />Analytics
                </Button>
              </Link>
              <a href="http://localhost:8080/critic_dashboard.html" target="_blank" rel="noopener noreferrer">
                <Button variant="ghost" className="w-full justify-start text-sm" style={{ color: `rgba(var(--text-secondary), 1)` }}>
                  <BarChart3 className="w-4 h-4 mr-2" />Critic Log
                </Button>
              </a>
              <Link href="/seo">
                <Button variant="ghost" className="w-full justify-start text-sm" style={{ color: `rgba(var(--text-secondary), 1)` }}>
                  <Search className="w-4 h-4 mr-2" />SEO Audit
                </Button>
              </Link>
              <Link href="/prompt-log">
                <Button variant="ghost" className="w-full justify-start text-sm" style={{ color: `rgba(var(--text-secondary), 1)` }}>
                  <Zap className="w-4 h-4 mr-2" />Prompt Evolution
                </Button>
              </Link>
            </div>

            <div className="flex items-center gap-3 p-3 rounded-lg" style={{ background: `rgba(var(--surface), 0.4)` }}>
              <div
                className="w-8 h-8 rounded-full flex items-center justify-center font-semibold shadow-glow"
                style={{
                  background: `linear-gradient(135deg, rgba(var(--secondary), 0.7), rgba(var(--secondary-dark), 0.4))`,
                  color: `rgba(var(--text-primary), 1)`,
                }}
              >
                <Sparkles className="w-6 h-6 animate-pulse-slow" style={{ color: `rgba(var(--primary), 1)` }} />
              </div>
              <h1 className="text-xl font-bold font-display" style={{ color: `rgba(var(--text-primary), 1)` }}>
                AI Marketing Assistant
              </h1>
            </div>

            <Button
              onClick={logout}
              variant="outline"
              className="w-full glass-effect bg-transparent"
              style={{
                borderColor: `rgba(var(--border), 0.5)`,
                color: "rgb(244, 67, 54)",
                background: "transparent",
              }}
            >
              <LogOut className="w-4 h-4 mr-2" />
              Logout
            </Button>
          </div>
        </div>

        {/* Main Area */}
        <div className="flex-1 flex flex-col">
          <div
            className="glass-effect p-4 flex items-center justify-between animate-fade-in"
            style={{ borderBottom: `1px solid rgba(var(--border), 0.5)` }}
          >
            <Button
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              variant="ghost"
              size="icon"
              className="lg:hidden"
              style={{ color: `rgba(var(--text-primary), 1)` }}
            >
              {isSidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </Button>
            <div className="flex items-center gap-2">
              <div
                className="w-10 h-10 rounded-lg flex items-center justify-center shadow-glow"
                style={{
                  background: `rgba(var(--primary), 0.2)`,
                  border: `1px solid rgba(var(--primary), 0.4)`,
                }}
              >
                <Sparkles className="w-6 h-6 animate-pulse-slow" style={{ color: `rgba(var(--primary), 1)` }} />
              </div>
              <h1 className="text-xl font-bold font-display" style={{ color: `rgba(var(--text-primary), 1)` }}>
                AI Marketing Assistant
              </h1>
            </div>
            <div className="w-10" />
          </div>

          {/* Chat Container */}
          <div ref={chatContainerRef} className="flex-1 overflow-y-auto p-4 lg:p-6 space-y-4">
            {messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full animate-scale-in">
                <div
                  className="w-20 h-20 rounded-full flex items-center justify-center mb-6 animate-pulse-slow shadow-glow"
                  style={{ background: `rgba(var(--primary), 0.2)` }}
                >
                  <Sparkles className="w-10 h-10" style={{ color: `rgba(var(--primary), 1)` }} />
                </div>
                <h2 className="text-3xl font-bold mb-2 font-display" style={{ color: `rgba(var(--text-primary), 1)` }}>
                  How can I help you today?
                </h2>
                <p className="text-center max-w-md" style={{ color: `rgba(var(--text-secondary), 1)` }}>
                  Start a conversation to generate SEO-optimized content, blog posts, and social media content.
                </p>
              </div>
            ) : (
              <>
                {messages.map((message, index) => (
                  <div key={index} className="flex flex-col gap-4">
                    {/* Message bubble row */}
                    <div
                      style={{ animationDelay: `${index * 50}ms` }}
                      className={`flex gap-4 animate-fade-in ${message.role === "user" ? "justify-end" : "justify-start"}`}
                    >
                      {message.role === "assistant" && (
                        <div
                          className="w-10 h-10 rounded-full flex items-center justify-center font-semibold flex-shrink-0 shadow-glow"
                          style={{
                            background: `linear-gradient(135deg, rgba(var(--primary), 1), rgba(var(--primary-dark), 1))`,
                            color: `rgba(var(--text-primary), 1)`,
                          }}
                        >
                          AI
                        </div>
                      )}

                      <div
                        className={`max-w-2xl p-4 rounded-2xl ${
                          message.role === "user" ? "shadow-glow" : "glass-effect"
                        }`}
                        style={
                          message.role === "user"
                            ? {
                                background: `linear-gradient(135deg, rgba(var(--primary), 1), rgba(var(--primary-dark), 1))`,
                                color: `rgba(var(--text-primary), 1)`,
                              }
                            : {
                                color: `rgba(var(--text-primary), 1)`,
                                borderColor: `rgba(var(--border), 0.5)`,
                              }
                        }
                      >
                        {message.role === "assistant" ? (
                          <div
                            className="whitespace-pre-wrap leading-relaxed formatted-content"
                            dangerouslySetInnerHTML={{ __html: messageFormatter.format(message.content) }}
                          />
                        ) : (
                          <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
                        )}
                      </div>

                      {message.role === "user" && (
                        <div
                          className="w-10 h-10 rounded-full flex items-center justify-center font-semibold flex-shrink-0"
                          style={{
                            background: `rgba(var(--surface), 0.6)`,
                            color: `rgba(var(--text-primary), 1)`,
                          }}
                        >
                          {userEmail[0]?.toUpperCase()}
                        </div>
                      )}
                    </div>

                    {/* â”€â”€ Selected chip (replaces cards after approval) â”€â”€ */}
                    {message.role === "assistant" && message.selectedOption && (
                      <div className="ml-14 animate-fade-in">
                        <div
                          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold"
                          style={{
                            background: `rgba(var(--primary), 0.15)`,
                            border: `1px solid rgba(var(--primary), 0.4)`,
                            color: `rgba(var(--text-primary), 1)`,
                          }}
                        >
                          <Check className="w-4 h-4" style={{ color: `rgba(var(--primary), 1)` }} />
                          Selected: {message.selectedOption.label}
                        </div>
                      </div>
                    )}

                    {/* â”€â”€ Inline option cards for this message â”€â”€ */}
                    {message.role === "assistant" && (message.responseOptions?.length ?? 0) > 0 && (
                      <div className="ml-14 animate-scale-in">
                        <p className="text-xs font-semibold mb-3" style={{ color: `rgba(var(--text-secondary), 1)` }}>
                          Pick the concept that fits best:
                        </p>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          {message.responseOptions!.map((option, optIdx) => (
                            <Card
                              key={option.option_id}
                              style={{
                                animationDelay: `${optIdx * 100}ms`,
                                background: `rgba(var(--surface), 0.4)`,
                                borderColor: `rgba(var(--border), 0.5)`,
                              }}
                              className={`glass-effect p-4 space-y-3 animate-fade-in transition-all duration-300 ${
                                workflowsDisabled ? "opacity-60" : "shadow-glow-hover hover:scale-[1.02]"
                              }`}
                            >
                              {/* Header: label + tone badge */}
                              <div className="flex items-start justify-between gap-2">
                                <h3 className="font-semibold text-base leading-tight" style={{ color: `rgba(var(--text-primary), 1)` }}>
                                  {option.label}
                                </h3>
                                <span
                                  className="px-2 py-0.5 rounded-full text-xs whitespace-nowrap flex-shrink-0"
                                  style={{ background: `rgba(var(--surface-hover), 0.8)`, color: `rgba(var(--text-secondary), 1)` }}
                                >
                                  {option.tone || "Custom"}
                                </span>
                              </div>

                              {/* Image area â€” social post cards */}
                              {option.content_type === "post" && (
                                <div className="relative overflow-hidden rounded-lg border" style={{ borderColor: `rgba(var(--border), 0.4)` }}>
                                  {option.preview_url ? (
                                    <>
                                      <img
                                        src={`${API_BASE_URL}${option.preview_url}`}
                                        alt="Generated image"
                                        className="w-full h-36 object-cover"
                                        onError={(e) => {
                                          const el = e.currentTarget as HTMLImageElement
                                          el.style.display = "none"
                                          const fb = el.nextElementSibling as HTMLElement
                                          if (fb) fb.style.display = "flex"
                                        }}
                                      />
                                      <div className="hidden items-center justify-center h-36 text-xs" style={{ color: `rgba(var(--text-secondary), 1)` }}>
                                        <ImageIcon className="w-8 h-8 opacity-40" />
                                      </div>
                                    </>
                                  ) : (
                                    <div className="flex items-center justify-center h-36 text-xs" style={{ color: `rgba(var(--text-secondary), 1)`, background: `rgba(var(--surface-hover), 0.4)` }}>
                                      <div className="text-center">
                                        <ImageIcon className="w-8 h-8 mx-auto mb-1 opacity-40" />
                                        <span>Image generating...</span>
                                      </div>
                                    </div>
                                  )}
                                  <div className="absolute top-1 right-1 bg-black/60 text-white text-xs px-1.5 py-0.5 rounded">AI</div>
                                  {regeneratingCardId === option.content_id && (
                                    <div className="absolute inset-0 flex items-center justify-center bg-black/50 rounded-lg">
                                      <div className="flex flex-col items-center gap-2 text-white text-xs">
                                        <div className="animate-spin rounded-full h-8 w-8 border-2 border-white border-t-transparent" />
                                        <span>Generating...</span>
                                      </div>
                                    </div>
                                  )}
                                </div>
                              )}

                              {/* Copy preview */}
                              {option.content_type === "post" && option.instagram_copy ? (
                                <div className="space-y-2 text-xs">
                                  {option.instagram_copy && (
                                    <div className="p-2 rounded-lg" style={{ background: `rgba(var(--surface-hover), 0.5)` }}>
                                      <span className="font-semibold" style={{ color: `rgba(var(--text-primary), 0.9)` }}>ðŸ“¸ Instagram</span>
                                      <p className="mt-1 line-clamp-3 leading-relaxed" style={{ color: `rgba(var(--text-secondary), 1)` }}>{option.instagram_copy}</p>
                                    </div>
                                  )}
                                  {option.hashtags && option.hashtags.length > 0 && (
                                    <p className="text-xs truncate" style={{ color: `rgba(var(--primary), 0.8)` }}>
                                      {option.hashtags.slice(0, 5).join(" ")}
                                    </p>
                                  )}
                                </div>
                              ) : (
                                <p className="text-sm line-clamp-3" style={{ color: `rgba(var(--text-secondary), 1)` }}>
                                  {option.preview_text || "Preview available after selection"}
                                </p>
                              )}

                              {/* Cost badge */}
                              <div className="flex flex-wrap gap-1.5 text-xs">
                                <span className="px-2 py-0.5 rounded-full" style={{ background: `rgba(var(--surface-hover), 0.6)`, color: `rgba(var(--text-secondary), 1)` }}>
                                  {option.cost_display}
                                </span>
                                {option.workflow_name && (
                                  <span className="px-2 py-0.5 rounded-full" style={{ background: `rgba(var(--surface-hover), 0.6)`, color: `rgba(var(--text-secondary), 1)` }}>
                                    {option.workflow_name}
                                  </span>
                                )}
                              </div>

                              {/* â”€â”€ Critic Score Panel â”€â”€ */}
                              {option.critic && Object.keys(option.critic).length > 0 && (
                                <div className="rounded-lg p-3 space-y-2" style={{
                                  background: `rgba(var(--surface-hover), 0.5)`,
                                  border: `1px solid rgba(var(--border), 0.4)`
                                }}>
                                  <div className="flex items-center justify-between">
                                    <span className="text-xs font-semibold" style={{ color: `rgba(var(--text-secondary), 1)` }}>
                                      ðŸ¤– AI Critic
                                    </span>
                                    <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${
                                      option.critic.passed
                                        ? 'bg-green-500/20 text-green-400'
                                        : 'bg-red-500/20 text-red-400'
                                    }`}>
                                      {option.critic.overall.toFixed(2)} {option.critic.passed ? 'âœ“ Pass' : 'âœ— Review'}
                                    </span>
                                  </div>
                                  <div className="grid grid-cols-3 gap-2 text-xs text-center">
                                    {([['Intent', option.critic.intent], ['Brand', option.critic.brand], ['Quality', option.critic.quality]] as [string, number][]).map(([lbl, val]) => (
                                      <div key={lbl}>
                                        <div className="font-semibold" style={{ color: `rgba(var(--text-primary), 0.95)` }}>{val.toFixed(2)}</div>
                                        <div style={{ color: `rgba(var(--text-secondary), 1)` }}>{lbl}</div>
                                      </div>
                                    ))}
                                  </div>
                                  {option.critic.text && (
                                    <p className="text-xs italic line-clamp-2" style={{ color: `rgba(var(--text-secondary), 0.85)` }}>
                                      &ldquo;{option.critic.text}&rdquo;
                                    </p>
                                  )}
                                </div>
                              )}

                              {/* Action buttons */}
                              <div className="flex gap-2 pt-1">
                                {option.content_type === "post" && option.content_id && (
                                  <Button
                                    onClick={() => regenerateCardImage(option.content_id!)}
                                    disabled={regeneratingCardId === option.content_id || workflowsDisabled}
                                    variant="outline" size="sm" className="glass-effect"
                                    style={{ borderColor: `rgba(var(--border), 0.5)`, color: `rgba(var(--text-primary), 1)` }}
                                    title="Regenerate AI image"
                                  >
                                    {regeneratingCardId === option.content_id
                                      ? <div className="animate-spin rounded-full h-3.5 w-3.5 border-2 border-current border-t-transparent" />
                                      : <RotateCw className="w-3.5 h-3.5" />}
                                  </Button>
                                )}
                                {option.preview_url && (
                                  <Button
                                    onClick={() => window.open(`${API_BASE_URL}${option.preview_url}`, "_blank")}
                                    variant="outline" size="sm" className="glass-effect"
                                    style={{ borderColor: `rgba(var(--border), 0.5)`, color: `rgba(var(--text-primary), 1)` }}
                                  >
                                    <Eye className="w-4 h-4 mr-1" />
                                    {option.content_type === "post" ? "Image" : "Preview"}
                                  </Button>
                                )}
                                <Button
                                  onClick={() => selectWorkflowOption(option)}
                                  disabled={workflowsDisabled}
                                  size="sm" className="flex-1 btn-primary border-0"
                                >
                                  {option.content_type === "post" ? "Approve & Post" : "Select"}
                                </Button>
                              </div>
                            </Card>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ))}

                {/* ADDED content preview card */}
                {contentPreview && (
                  <Card
                    className="glass-effect max-w-4xl mx-auto animate-scale-in border-2 overflow-hidden"
                    style={{
                      borderColor: `rgba(var(--primary), 0.5)`,
                      background: `rgba(var(--surface), 0.6)`,
                    }}
                  >
                    <div className="p-6">
                      <div className="flex items-center justify-between mb-4">
                        <h3 className="text-lg font-semibold" style={{ color: `rgba(var(--text-primary), 1)` }}>
                          Content Preview
                        </h3>
                        <span
                          className={`px-3 py-1 rounded-full text-xs font-bold uppercase ${
                            contentPreview.type === "blog"
                              ? "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200"
                              : "bg-pink-100 text-pink-800 dark:bg-pink-900 dark:text-pink-200"
                          }`}
                        >
                          {contentPreview.type}
                        </span>
                      </div>

                      {previewLoading ? (
                        <div className="flex items-center justify-center py-12">
                          <div
                            className="animate-spin rounded-full h-12 w-12 border-b-2"
                            style={{ borderColor: `rgba(var(--primary), 1)` }}
                          />
                        </div>
                      ) : (
                        <>
                          {contentPreview.type === "blog" ? (
                            <iframe
                              src={`${API_BASE_URL}/preview/blog/${contentPreview.content_id}`}
                              className="w-full h-[400px] rounded-lg border"
                              style={{ borderColor: `rgba(var(--border), 0.5)` }}
                              title="Blog Preview"
                            />
                          ) : (
                            <div className="space-y-4">
                              <div className="p-6 rounded-lg" style={{ background: `rgba(var(--surface-hover), 0.4)` }}>
                                {contentDetails?.preview_url || contentDetails?.metadata?.image_path ? (
                                  <div className="relative group">
                                    <img
                                      src={`${API_BASE_URL}/preview/image/${encodeURIComponent(
                                        contentDetails.preview_url || contentDetails.metadata?.image_path || "",
                                      )}`}
                                      alt="Generated social media post"
                                      className="w-full max-w-lg mx-auto rounded-lg border-2 shadow-lg transition-transform duration-300 group-hover:scale-105"
                                      style={{ borderColor: `rgba(var(--primary), 0.3)` }}
                                      onError={(e) => {
                                        e.currentTarget.style.display = "none"
                                        const errorDiv = e.currentTarget.nextElementSibling as HTMLElement
                                        if (errorDiv) errorDiv.style.display = "block"
                                      }}
                                    />
                                    <div
                                      className="hidden text-center py-12"
                                      style={{ color: `rgba(var(--text-secondary), 1)` }}
                                    >
                                      <ImageIcon className="w-16 h-16 mx-auto mb-3 opacity-50" />
                                      <p>Image preview not available</p>
                                    </div>
                                  </div>
                                ) : (
                                  <div
                                    className="text-center py-12"
                                    style={{ color: `rgba(var(--text-secondary), 1)` }}
                                  >
                                    <ImageIcon className="w-16 h-16 mx-auto mb-3 opacity-50" />
                                    <p>Image will be generated on approval</p>
                                  </div>
                                )}
                              </div>

                              {contentDetails?.content && (
                                <div
                                  className="p-4 rounded-lg border"
                                  style={{
                                    background: `rgba(var(--surface), 0.3)`,
                                    borderColor: `rgba(var(--border), 0.5)`,
                                  }}
                                >
                                  <strong className="block mb-2" style={{ color: `rgba(var(--text-primary), 1)` }}>
                                    Post Text:
                                  </strong>
                                  <p
                                    className="text-sm leading-relaxed"
                                    style={{ color: `rgba(var(--text-secondary), 1)` }}
                                  >
                                    {contentDetails.content}
                                  </p>
                                </div>
                              )}
                            </div>
                          )}

                          <div className="flex gap-3 mt-6">
                            <Button
                              onClick={() => approveContent(contentPreview.content_id)}
                              className="flex-1 btn-primary border-0 group"
                            >
                              <Check className="w-4 h-4 mr-2 group-hover:scale-110 transition-transform" />
                              Approve & Publish
                            </Button>
                            <Button
                              onClick={() => regenerateContent(contentPreview.content_id)}
                              variant="outline"
                              className="flex-1 glass-effect"
                              style={{
                                borderColor: `rgba(var(--border), 0.5)`,
                                color: `rgba(var(--text-primary), 1)`,
                              }}
                            >
                              <RotateCw className="w-4 h-4 mr-2" />
                              Regenerate
                            </Button>
                            <Button
                              onClick={() => rejectContent(contentPreview.content_id)}
                              variant="outline"
                              className="flex-1"
                              style={{
                                borderColor: "rgba(244, 67, 54, 0.5)",
                                color: "rgb(244, 67, 54)",
                                background: "rgba(244, 67, 54, 0.1)",
                              }}
                            >
                              <XCircle className="w-4 h-4 mr-2" />
                              Cancel
                            </Button>
                          </div>
                        </>
                      )}
                    </div>
                  </Card>
                )}

                {/* Loading Indicator */}
                {isLoading && (
                  <div className="flex gap-4 animate-fade-in">
                    <div
                      className="w-10 h-10 rounded-full flex items-center justify-center font-semibold shadow-glow"
                      style={{
                        background: `linear-gradient(135deg, rgba(var(--primary), 1), rgba(var(--primary-dark), 1))`,
                        color: `rgba(var(--text-primary), 1)`,
                      }}
                    >
                      AI
                    </div>
                    <div className="glass-effect p-4 rounded-2xl" style={{ borderColor: `rgba(var(--border), 0.5)` }}>
                      <div className="flex gap-2">
                        {[0, 0.2, 0.4].map((delay, i) => (
                          <div
                            key={i}
                            className="w-2 h-2 rounded-full animate-pulse"
                            style={{
                              animationDelay: `${delay}s`,
                              background: `rgba(var(--text-secondary), 1)`,
                            }}
                          />
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>

          {/* Input Area */}
          <div className="glass-effect p-4" style={{ borderTop: `1px solid rgba(var(--border), 0.5)` }}>
            <div className="max-w-4xl mx-auto flex gap-3">
              <Button
                onClick={() => setShowUploadModal(true)}
                variant="outline"
                size="icon"
                className="glass-effect"
                style={{
                  borderColor: `rgba(var(--border), 0.5)`,
                  color: `rgba(var(--text-primary), 1)`,
                }}
              >
                <Upload className="w-5 h-5" />
              </Button>

              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyPress={(e) => e.key === "Enter" && !e.shiftKey && sendMessage()}
                placeholder="Type your message..."
                disabled={isLoading}
                className="flex-1 glass-effect"
                style={{
                  borderColor: `rgba(var(--border), 0.5)`,
                  color: `rgba(var(--text-primary), 1)`,
                  background: `rgba(var(--surface), 0.4)`,
                }}
              />

              <Button onClick={sendMessage} disabled={isLoading || !input.trim()} size="icon" className="btn-primary">
                <Send className="w-5 h-5" />
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Upload Modal */}
      {showUploadModal && (
        <div
          className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4 animate-fade-in"
          onClick={() => setShowUploadModal(false)}
        >
          <Card
            onClick={(e) => e.stopPropagation()}
            className="glass-effect-strong border-white/20 p-6 w-full max-w-md animate-scale-in"
          >
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-bold text-white">Upload Image</h2>
              <Button
                onClick={() => setShowUploadModal(false)}
                variant="ghost"
                size="icon"
                className="text-white hover:bg-white/10"
              >
                <X className="w-5 h-5" />
              </Button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-white text-sm font-medium mb-2">Asset Type</label>
                <select
                  value={assetType}
                  onChange={(e) => setAssetType(e.target.value)}
                  className="w-full p-3 rounded-lg bg-white/10 border border-white/20 text-white focus:border-primary focus:ring-primary/20"
                >
                  <option value="general">General</option>
                  <option value="logo">Logo</option>
                  <option value="product">Product</option>
                  <option value="reference">Reference</option>
                </select>
              </div>

              <div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                  className="hidden"
                />
                <Button
                  onClick={() => fileInputRef.current?.click()}
                  variant="outline"
                  className="w-full border-white/20 text-white hover:bg-white/10"
                >
                  <ImageIcon className="w-4 h-4 mr-2" />
                  {uploadFile ? uploadFile.name : "Choose File"}
                </Button>
              </div>

              {uploadFile && (
                <div className="p-4 rounded-lg bg-white/5 border border-white/10">
                  <p className="text-white text-sm">
                    <strong>Selected:</strong> {uploadFile.name}
                  </p>
                  <p className="text-white/60 text-xs mt-1">{(uploadFile.size / 1024 / 1024).toFixed(2)} MB</p>
                </div>
              )}

              <Button
                onClick={handleUpload}
                disabled={!uploadFile}
                className="w-full bg-primary hover:bg-primary/90 text-white border-0"
              >
                Upload
              </Button>
            </div>
          </Card>
        </div>
      )}

      {/* Assets Modal */}
      {showAssetsModal && (
        <div
          className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4 animate-fade-in"
          onClick={() => setShowAssetsModal(false)}
        >
          <Card
            onClick={(e) => e.stopPropagation()}
            className="glass-effect-strong border-white/20 p-6 w-full max-w-3xl max-h-[80vh] overflow-auto animate-scale-in"
          >
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-bold text-white">Your Assets</h2>
              <Button
                onClick={() => setShowAssetsModal(false)}
                variant="ghost"
                size="icon"
                className="text-white hover:bg-white/10"
              >
                <X className="w-5 h-5" />
              </Button>
            </div>

            {assetsLoading ? (
              <div className="flex items-center justify-center py-12">
                <div
                  className="animate-spin rounded-full h-12 w-12 border-b-2"
                  style={{ borderColor: `rgba(var(--primary), 1)` }}
                />
              </div>
            ) : assets.length === 0 ? (
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                <div className="glass-effect border border-white/10 rounded-lg p-4 text-center">
                  <ImageIcon className="w-12 h-12 mx-auto text-white/40 mb-2" />
                  <p className="text-white/60 text-sm">No assets yet</p>
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
                {assets.map((asset, idx) => (
                  <div
                    key={`${asset.url}-${idx}`}
                    className="glass-effect border border-white/10 rounded-lg overflow-hidden group hover:scale-105 transition-transform duration-300"
                  >
                    <div className="aspect-square bg-black/30 overflow-hidden relative">
                      <img
                        src={asset.url}
                        alt={asset.filename || `Asset ${idx + 1}`}
                        className="w-full h-full object-cover"
                        onError={(e) => {
                          const target = e.target as HTMLImageElement
                          target.style.display = "none"
                          const parent = target.parentElement
                          if (parent) {
                            const errorDiv = document.createElement("div")
                            errorDiv.className = "flex items-center justify-center h-full"
                            errorDiv.innerHTML = `
                              <div class="text-center p-4">
                                <svg class="w-12 h-12 mx-auto text-white/40 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path>
                                </svg>
                                <p class="text-white/60 text-xs">Image not available</p>
                              </div>
                            `
                            parent.appendChild(errorDiv)
                          }
                        }}
                      />
                      <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
                        <a
                          href={asset.url}
                          target="_blank"
                          rel="noreferrer"
                          className="bg-black/60 backdrop-blur-sm px-2 py-1 rounded text-xs text-white hover:bg-black/80"
                        >
                          Open
                        </a>
                      </div>
                    </div>
                    <div className="p-3 space-y-1">
                      <p className="text-sm text-white truncate font-medium">{asset.filename || `Asset ${idx + 1}`}</p>
                      <p className="text-xs text-white/60 uppercase tracking-wide">
                        Type: {asset.asset_type || "general"}
                      </p>
                      {asset.uploaded_at && (
                        <p className="text-xs text-white/40">
                          {new Date(asset.uploaded_at).toLocaleDateString()}
                        </p>
                      )}
                      {asset.size && (
                        <p className="text-xs text-white/40">
                          {(asset.size / 1024 / 1024).toFixed(2)} MB
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      )}

      {/* Manager Modal */}
      {showManagerModal && (
        <div
          className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4 animate-fade-in"
          onClick={() => setShowManagerModal(false)}
        >
          <Card
            onClick={(e) => e.stopPropagation()}
            className="glass-effect-strong border-white/20 p-6 w-full max-w-2xl max-h-[80vh] overflow-auto animate-scale-in"
          >
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-bold text-white">Social Media Manager</h2>
              <Button
                onClick={() => setShowManagerModal(false)}
                variant="ghost"
                size="icon"
                className="text-white hover:bg-white/10"
              >
                <X className="w-5 h-5" />
              </Button>
            </div>

            <div className="space-y-4">
              {/* Instagram */}
              <div className="glass-effect border border-white/10 rounded-lg p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <Instagram className="w-6 h-6 text-pink-500" />
                    <h3 className="text-lg font-semibold text-white">Instagram</h3>
                  </div>
                  <span className="px-3 py-1 rounded-full text-xs font-semibold bg-green-500/20 text-green-400 border border-green-500/30">
                    In Use
                  </span>
                </div>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-white/60">Username:</span>
                    <span className="text-white">@ganesh.s_sg</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-white/60">Status:</span>
                    <span className="text-green-400">Connected</span>
                  </div>
                </div>
              </div>
            </div>
          </Card>
        </div>
      )}

      {/* Performance Modal */}
      {showPerformanceModal && (
        <div
          className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4 animate-fade-in overflow-auto"
          onClick={() => setShowPerformanceModal(false)}
        >
          <Card
            onClick={(e) => e.stopPropagation()}
            className="glass-effect-strong border-white/20 p-6 w-full max-w-6xl max-h-[90vh] overflow-auto animate-scale-in my-8"
          >
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-bold text-white">Performance Analytics</h2>
              <Button
                onClick={() => setShowPerformanceModal(false)}
                variant="ghost"
                size="icon"
                className="text-white hover:bg-white/10"
              >
                <X className="w-5 h-5" />
              </Button>
            </div>

            {/* First Row: 75% Analytics + 25% Scheduling */}
            <div className="grid grid-cols-3 gap-4 mb-6">
              {/* Analytics Section - 75% */}
              <div className="col-span-2 space-y-4">
                {/* Engagement Rates */}
                <div className="glass-effect border border-white/10 rounded-lg p-4">
                  <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                    <TrendingUp className="w-5 h-5" />
                    Engagement Rates
                  </h3>
                  <div className="grid grid-cols-1 gap-4">
                    <div className="p-4 rounded-lg" style={{ background: `rgba(var(--surface), 0.3)` }}>
                      <div className="flex items-center gap-2 mb-2">
                        <Instagram className="w-5 h-5 text-pink-500" />
                        <span className="text-white font-semibold">Instagram</span>
                      </div>
                      <div className="text-3xl font-bold text-pink-400 mb-1">0.0%</div>
                      <div className="text-xs text-white/60">0% from last week</div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Scheduling Section - 25% */}
              <div className="space-y-4">
                <div className="glass-effect border border-white/10 rounded-lg p-4">
                  <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                    <Calendar className="w-5 h-5" />
                    Schedule Posts
                  </h3>
                  <div className="space-y-3">
                    <div>
                      <label className="text-xs text-white/60 mb-1 block">Instagram</label>
                      <Select defaultValue="today">
                        <SelectTrigger
                          className="w-full"
                          style={{
                            background: `rgba(var(--surface), 0.5)`,
                            borderColor: `rgba(var(--border), 0.5)`,
                            color: `rgba(var(--text-primary), 1)`,
                          }}
                        >
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="today">Today</SelectItem>
                          <SelectItem value="tomorrow">Tomorrow</SelectItem>
                          <SelectItem value="week">This Week</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                </div>
              </div>
            </div>

          </Card>
        </div>
      )}
    </>
  )
}
