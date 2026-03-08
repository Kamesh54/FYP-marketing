document.addEventListener("DOMContentLoaded", () => {
  const chatWindow = document.getElementById("chat-window")
  const chatInput = document.getElementById("chat-input")
  const sendButton = document.getElementById("send-button")
  const fileUpload = document.getElementById("file-upload")
  const sessionIdSpan = document.getElementById("session-id")
  const chatTab = document.getElementById("chat-tab")
  const instructionsTab = document.getElementById("instructions-tab")
  const reportsTab = document.getElementById("reports-tab")
  const chatSection = document.getElementById("chat-section")
  const instructionsSection = document.getElementById("instructions-section")
  const reportsSection = document.getElementById("reports-section")
  const reportsList = document.getElementById("reports-list")

  let sessionId = localStorage.getItem("aiAssistantSessionId")
  if (!sessionId) {
    sessionId = generateSessionId()
    localStorage.setItem("aiAssistantSessionId", sessionId)
  }
  sessionIdSpan.textContent = sessionId

  const API_BASE_URL = "http://127.0.0.1:8004" // Orchestrator API

  function generateSessionId() {
    return "sess_" + Math.random().toString(36).substr(2, 9)
  }

  function appendMessage(sender, message, isHtml = false) {
    const messageElement = document.createElement("div")
    messageElement.classList.add("chat-message", sender)
    const bubble = document.createElement("div")
    bubble.classList.add("message-bubble", sender)
    if (isHtml) {
      bubble.innerHTML = message
    } else {
      bubble.textContent = message
    }
    messageElement.appendChild(bubble)
    chatWindow.appendChild(messageElement)
    chatWindow.scrollTop = chatWindow.scrollHeight // Auto-scroll to bottom
  }

  function renderResponseOptions(options) {
    if (!options || !options.length) return
    const container = document.createElement("div")
    container.classList.add("option-card-container")

    options.forEach((option) => {
      const card = document.createElement("div")
      card.classList.add("option-card")

      const header = document.createElement("div")
      header.classList.add("option-header")
      header.textContent = option.label

      const meta = document.createElement("div")
      meta.classList.add("option-meta")
      meta.textContent = `${option.tone || "Custom"} · ${option.cost_display || ""} · ${option.workflow_name || ""}`

      const preview = document.createElement("div")
      preview.classList.add("option-preview")
      preview.textContent = option.preview_text || "Toggle the preview link below to inspect the draft."

      card.appendChild(header)
      card.appendChild(meta)
      card.appendChild(preview)

      if (option.preview_url) {
        const link = document.createElement("a")
        link.href = `${API_BASE_URL}${option.preview_url}`
        link.target = "_blank"
        link.rel = "noreferrer"
        link.textContent = "Open preview"
        link.classList.add("option-link")
        card.appendChild(link)
      }

      const button = document.createElement("button")
      button.classList.add("select-option-btn")
      button.textContent = "Use this option"
      button.addEventListener("click", () => selectWorkflowOption(option.option_id, container, button))
      card.appendChild(button)

      container.appendChild(card)
    })

    chatWindow.appendChild(container)
    chatWindow.scrollTop = chatWindow.scrollHeight
  }

  async function selectWorkflowOption(optionId, container, button) {
    if (!optionId || button.disabled) return
    const initialLabel = button.textContent
    button.disabled = true
    button.textContent = "Selecting..."
    try {
      const response = await fetch(`${API_BASE_URL}/workflow/select`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ option_id: optionId, session_id: sessionId }),
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const data = await response.json()
      appendMessage("assistant", data.message || "Selection recorded.")

      container.querySelectorAll("button").forEach((btn) => {
        btn.disabled = true
        btn.classList.add("option-btn-disabled")
      })
      container.classList.add("option-card-container--selected")
    } catch (error) {
      console.error("Error selecting option:", error)
      button.disabled = false
      button.textContent = initialLabel
      appendMessage("assistant", "Couldn't record that selection. Please try again.")
    }
  }

  async function sendMessage() {
    const message = chatInput.value.trim()
    if (!message) return

    appendMessage("user", message)
    chatInput.value = ""

    try {
      const response = await fetch(`${API_BASE_URL}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ session_id: sessionId, message: message }),
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const data = await response.json()
      appendMessage("assistant", data.response)
      if (data.response_options && data.response_options.length) {
        renderResponseOptions(data.response_options)
      }

      if (data.html_report_url) {
        const reportLink = `<a href="${API_BASE_URL}${data.html_report_url}" target="_blank">View Report</a>`
        appendMessage("assistant", `Your report is ready: ${reportLink}`, true)
        addReportToList("SEO Report", `${API_BASE_URL}${data.html_report_url}`)
      }

      // Handle other types of reports/previews here based on data.response content
      // For example, if the response contains a blog URL or social media preview
      if (data.response.includes("blog page and hosted it for you on AWS S3 here:")) {
        const blogUrlMatch = data.response.match(/(https:\/\/[^\s]+)/)
        if (blogUrlMatch) {
          addReportToList("Blog Preview", blogUrlMatch[0])
        }
      }
      if (data.response.includes("- Tweeted:") || data.response.includes("- Posted on Instagram:")) {
        const tweetUrlMatch = data.response.match(/- Tweeted: (https:\/\/[^\s]+)/)
        if (tweetUrlMatch) {
          addReportToList("Twitter Post", tweetUrlMatch[1])
        }
        const instaUrlMatch = data.response.match(/- Posted on Instagram: (https:\/\/[^\s]+)/)
        if (instaUrlMatch) {
          addReportToList("Instagram Post", instaUrlMatch[1])
        }
      }
    } catch (error) {
      console.error("Error sending message:", error)
      appendMessage("assistant", "Oops! Something went wrong. Please try again.")
    }
  }

  async function uploadFile() {
    const file = fileUpload.files[0]
    if (!file) return

    const formData = new FormData()
    formData.append("file", file)

    appendMessage("user", `Uploading file: ${file.name}`)

    try {
      const response = await fetch(`${API_BASE_URL}/upload/${sessionId}`, {
        method: "POST",
        body: formData,
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const data = await response.json()
      appendMessage("assistant", data.message)
      fileUpload.value = "" // Clear the file input
    } catch (error) {
      console.error("Error uploading file:", error)
      appendMessage("assistant", "Oops! Error uploading file. Please try again.")
    }
  }

  function addReportToList(name, url) {
    const reportItem = document.createElement("div")
    reportItem.classList.add("report-item")
    reportItem.innerHTML = `
            <span>${name}</span>
            <a href="${url}" target="_blank">View</a>
        `
    reportsList.appendChild(reportItem)
    // Remove "No reports" message if it exists
    const noReportsMessage = reportsList.querySelector("p")
    if (
      noReportsMessage &&
      noReportsMessage.textContent === "No reports or previews available yet. Start a session to generate some!"
    ) {
      reportsList.removeChild(noReportsMessage)
    }
  }

  sendButton.addEventListener("click", sendMessage)
  chatInput.addEventListener("keypress", (e) => {
    if (e.key === "Enter") {
      sendMessage()
    }
  })
  fileUpload.addEventListener("change", uploadFile)

  // Tab switching logic
  chatTab.addEventListener("click", () => {
    chatTab.classList.add("active")
    instructionsTab.classList.remove("active")
    reportsTab.classList.remove("active")
    chatSection.classList.remove("hidden")
    instructionsSection.classList.add("hidden")
    reportsSection.classList.add("hidden")
  })

  instructionsTab.addEventListener("click", () => {
    instructionsTab.classList.add("active")
    chatTab.classList.remove("active")
    reportsTab.classList.remove("active")
    instructionsSection.classList.remove("hidden")
    chatSection.classList.add("hidden")
    reportsSection.classList.add("hidden")
  })

  reportsTab.addEventListener("click", () => {
    reportsTab.classList.add("active")
    chatTab.classList.remove("active")
    instructionsTab.classList.remove("active")
    reportsSection.classList.remove("hidden")
    chatSection.classList.add("hidden")
    instructionsSection.classList.add("hidden")
  })

  // Initial greeting from the assistant
  appendMessage(
    "assistant",
    "Hello! I'm your AI-powered SEO and Content assistant. Do you have an existing webpage? (Yes/No)",
  )
})
