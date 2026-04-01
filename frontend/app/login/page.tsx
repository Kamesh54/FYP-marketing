"use client"

import type React from "react"

import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card } from "@/components/ui/card"
import { Sparkles, Mail, Lock, User } from "lucide-react"

const API_BASE_URL = "http://127.0.0.1:8004"

export default function LoginPage() {
  const [isLogin, setIsLogin] = useState(true)
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [error, setError] = useState("")
  const [success, setSuccess] = useState("")
  const [isLoading, setIsLoading] = useState(false)

  const [theme, setTheme] = useState("pulse")

  useEffect(() => {
    const savedTheme = localStorage.getItem("theme") || "pulse"
    setTheme(savedTheme)
    document.body.className = `theme-${savedTheme}`
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setSuccess("")

    if (!isLogin && password !== confirmPassword) {
      setError("Passwords do not match")
      return
    }

    if (password.length < 8) {
      setError("Password must be at least 8 characters")
      return
    }

    setIsLoading(true)

    try {
      const endpoint = isLogin ? "/auth/login" : "/auth/signup"
      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      })

      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.detail || "Authentication failed")
      }

      localStorage.setItem("authToken", data.token)
      localStorage.setItem("userId", data.user_id)
      localStorage.setItem("userEmail", data.email)

      setSuccess(isLogin ? "Login successful! Redirecting..." : "Account created! Redirecting...")

      setTimeout(() => {
        window.location.href = "/"
      }, 1000)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4 relative overflow-hidden">
      <div className="scene-3d">
        <div className="floating-shape shape-cube"></div>
        <div className="floating-shape shape-sphere"></div>
        <div className="floating-shape shape-pyramid"></div>
        <div className="floating-shape shape-torus"></div>
        <div className="grid-floor"></div>
        <div className="depth-fog"></div>
      </div>

      <div className="particles-container">
        {[...Array(20)].map((_, i) => (
          <div
            key={i}
            className="particle"
            style={{
              left: `${Math.random() * 100}%`,
              top: `${Math.random() * 100}%`,
              animationDelay: `${Math.random() * 5}s`,
              animationDuration: `${5 + Math.random() * 10}s`,
            }}
          />
        ))}
      </div>

      <Card className="glass-panel border-white/10 p-8 w-full max-w-md animate-scale-in relative z-10 shadow-2xl">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="w-20 h-20 rounded-2xl glass-panel flex items-center justify-center mx-auto mb-4 animate-float border border-white/20">
            <div className="w-16 h-16 rounded-xl bg-gradient-to-br from-primary/30 to-primary/10 flex items-center justify-center">
              <Sparkles className="w-8 h-8 text-primary animate-pulse-slow" />
            </div>
          </div>
          <h1 className="text-4xl font-bold text-white mb-2 animate-fade-in">Markx.pro</h1>
          <p className="text-white/60 animate-fade-in-delay">Next-generation marketing intelligence platform</p>
        </div>

        {/* Tab Switcher */}
        <div className="flex gap-2 mb-6 p-1 rounded-xl glass-panel">
          <Button
            onClick={() => setIsLogin(true)}
            className={`flex-1 rounded-lg transition-all duration-300 ${
              isLogin
                ? "bg-primary text-white shadow-lg shadow-primary/50 scale-105"
                : "bg-transparent text-white/60 hover:bg-white/5 hover:text-white"
            }`}
          >
            Login
          </Button>
          <Button
            onClick={() => setIsLogin(false)}
            className={`flex-1 rounded-lg transition-all duration-300 ${
              !isLogin
                ? "bg-primary text-white shadow-lg shadow-primary/50 scale-105"
                : "bg-transparent text-white/60 hover:bg-white/5 hover:text-white"
            }`}
          >
            Sign Up
          </Button>
        </div>

        {/* Error/Success Messages */}
        {error && (
          <div className="mb-4 p-4 rounded-xl glass-panel border border-red-500/30 animate-shake">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse"></div>
              <p className="text-red-400 text-sm">{error}</p>
            </div>
          </div>
        )}

        {success && (
          <div className="mb-4 p-4 rounded-xl glass-panel border border-green-500/30 animate-fade-in">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></div>
              <p className="text-green-400 text-sm">{success}</p>
            </div>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="animate-slide-in-left">
            <label className="block text-white text-sm font-medium mb-2 flex items-center gap-2">
              <Mail className="w-4 h-4 text-primary" />
              Email Address
            </label>
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
              className="w-full glass-panel border-white/10 text-white placeholder:text-white/40 focus:border-primary focus:ring-2 focus:ring-primary/20 rounded-xl h-12 px-4 transition-all duration-300 hover:border-white/30"
            />
          </div>

          <div className="animate-slide-in-left" style={{ animationDelay: "0.1s" }}>
            <label className="block text-white text-sm font-medium mb-2 flex items-center gap-2">
              <Lock className="w-4 h-4 text-primary" />
              Password
            </label>
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={isLogin ? "Enter your password" : "Create a strong password"}
              required
              className="w-full glass-panel border-white/10 text-white placeholder:text-white/40 focus:border-primary focus:ring-2 focus:ring-primary/20 rounded-xl h-12 px-4 transition-all duration-300 hover:border-white/30"
            />
            {!isLogin && (
              <p className="text-white/40 text-xs mt-2 flex items-center gap-1">
                <span className="w-1 h-1 rounded-full bg-primary"></span>
                Must be 8+ characters with uppercase, lowercase, and number
              </p>
            )}
          </div>

          {!isLogin && (
            <div className="animate-slide-in-left" style={{ animationDelay: "0.2s" }}>
              <label className="block text-white text-sm font-medium mb-2 flex items-center gap-2">
                <Lock className="w-4 h-4 text-primary" />
                Confirm Password
              </label>
              <Input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Re-enter your password"
                required
                className="w-full glass-panel border-white/10 text-white placeholder:text-white/40 focus:border-primary focus:ring-2 focus:ring-primary/20 rounded-xl h-12 px-4 transition-all duration-300 hover:border-white/30"
              />
            </div>
          )}

          <Button
            type="submit"
            disabled={isLoading}
            className="w-full bg-primary hover:bg-primary/90 text-white border-0 shadow-lg shadow-primary/50 hover:shadow-xl hover:shadow-primary/60 transition-all duration-300 hover:scale-105 rounded-xl h-12 font-semibold relative overflow-hidden group animate-slide-in-left"
            style={{ animationDelay: "0.3s" }}
          >
            <span className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent translate-x-[-200%] group-hover:translate-x-[200%] transition-transform duration-1000"></span>
            <span className="relative flex items-center justify-center gap-2">
              {isLoading ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                  Processing...
                </>
              ) : (
                <>
                  <User className="w-4 h-4" />
                  {isLogin ? "Login to Dashboard" : "Create Account"}
                </>
              )}
            </span>
          </Button>
        </form>

        {isLogin && (
          <div className="mt-6 text-center animate-fade-in" style={{ animationDelay: "0.4s" }}>
            <button className="text-white/60 hover:text-white text-sm transition-colors duration-300 hover:underline">
              Forgot password?
            </button>
          </div>
        )}

        <div
          className="mt-6 pt-6 border-t border-white/10 flex items-center justify-center gap-2 animate-fade-in"
          style={{ animationDelay: "0.5s" }}
        >
          <div className="w-2 h-2 rounded-full bg-primary animate-pulse"></div>
          <span className="text-white/40 text-xs capitalize">{theme} Theme Active</span>
        </div>
      </Card>
    </div>
  )
}
