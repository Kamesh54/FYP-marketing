class MessageFormatter {
    private codeBlockId = 0
  
    format(text: string): string {
      if (!text) return ""
  
      let formatted = this.normalizeText(text)
  
      // Escape HTML first to prevent XSS
      formatted = this.escapeHtml(formatted)
  
      // Format code blocks (must be done before inline code)
      formatted = this.formatCodeBlocks(formatted)
  
      // Format inline code
      formatted = this.formatInlineCode(formatted)
  
      // Format bold text
      formatted = this.formatBold(formatted)

      // Format markdown headings so raw ### markers do not appear in the UI
      formatted = this.formatHeadings(formatted)
  
      // Format italic text
      formatted = this.formatItalic(formatted)
  
      // Format links
      formatted = this.formatLinks(formatted)
  
      // Format lists
      formatted = this.formatLists(formatted)
  
      // Format blockquotes
      formatted = this.formatBlockquotes(formatted)
  
      // Format line breaks and paragraphs
      formatted = this.formatParagraphs(formatted)
  
      return formatted
    }

    private normalizeText(text: string): string {
      return text
        .replace(/\r\n/g, "\n")
        .replace(/âœ…/g, "")
        .replace(/âœ“/g, "")
        .replace(/âœ”/g, "")
        .replace(/âœ—/g, "")
        .replace(/âš ï¸/g, "Warning:")
        .replace(/âš /g, "Warning:")
        .replace(/ðŸ“£/g, "")
        .replace(/ðŸ“/g, "")
        .replace(/ðŸ”/g, "")
        .replace(/ðŸ”„/g, "")
        .replace(/Ã¢â‚¬Â¦/g, "...")
        .replace(/Ã¢â‚¬â€œ/g, "-")
        .replace(/Ã¢â‚¬â€/g, "-")
        .replace(/Ã¢â‚¬Â¢/g, "•")
        .replace(/Ã‚Â·/g, "·")
        .replace(/Ã‚/g, "")
        .replace(/Ã¢Å“Â¦/g, "")
        .replace(/â€¦/g, "...")
        .replace(/â€“/g, "-")
        .replace(/â€”/g, "-")
        .replace(/â€¢/g, "•")
        .replace(/â€˜|â€™/g, "'")
        .replace(/â€œ|â€/g, '"')
        .replace(/âœ¦/g, "")
        .replace(/âœ/g, "")
        .replace(/Â/g, "")
        .replace(/â(?=\S)/g, "")
        .replace(/[ \t]+\n/g, "\n")
        .replace(/\n{3,}/g, "\n\n")
    }

    private escapeHtml(text: string): string {
      const div = document.createElement("div")
      div.textContent = text
      return div.innerHTML
    }
  
    private formatCodeBlocks(text: string): string {
      const codeBlockRegex = /```(\w+)?\n([\s\S]*?)```/g
  
      return text.replace(codeBlockRegex, (match, language, code) => {
        const id = `code-block-${this.codeBlockId++}`
        const lang = language || "text"
  
        const codeContent = code
          .replace(/&lt;/g, "<")
          .replace(/&gt;/g, ">")
          .replace(/&amp;/g, "&")
          .replace(/&quot;/g, '"')
          .replace(/&#039;/g, "'")
  
        return `<div class="code-block-wrapper">
          <div class="code-block-header">
            <span class="code-language">${lang}</span>
            <button class="copy-code-button" onclick="window.copyCode('${id}')">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <path d="M4 2a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v2h2a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2v-2H4a2 2 0 0 1-2-2V2z"/>
              </svg>
              Copy
            </button>
          </div>
          <pre class="code-block"><code id="${id}" class="language-${lang}">${codeContent}</code></pre>
        </div>`
      })
    }
  
    private formatInlineCode(text: string): string {
      return text.replace(/`([^`\n]+)`/g, '<code class="inline-code">$1</code>')
    }
  
    private formatBold(text: string): string {
      return text.replace(/\*\*([^*\n]+?)\*\*/g, "<strong>$1</strong>").replace(/__([^_\n]+?)__/g, "<strong>$1</strong>")
    }

    private formatHeadings(text: string): string {
      return text.replace(/^\s*(#{1,6})\s+(.+)$/gm, (_match, hashes: string, content: string) => {
        const level = Math.min(hashes.length, 6)
        return `<h${level} class="message-heading message-heading-${level}">${content.trim()}</h${level}>`
      })
    }
  
    private formatItalic(text: string): string {
      return text
        .replace(/(?<!\*)\*(?!\*)([^*\n]+?)\*(?!\*)/g, "<em>$1</em>")
        .replace(/(?<!_)_(?!_)([^_\n]+?)_(?!_)/g, "<em>$1</em>")
    }
  
    private formatLinks(text: string): string {
      const urlRegex = /(https?:\/\/[^\s<]+)/g
      return text.replace(urlRegex, '<a href="$1" target="_blank" rel="noopener noreferrer" class="message-link">$1</a>')
    }
  
    private formatLists(text: string): string {
      let formatted = text
  
      // Unordered lists
      const unorderedListRegex = /(?:^|\n)((?:[â€¢\-*] .+\n?)+)/gm
      formatted = formatted.replace(unorderedListRegex, (match, listItems) => {
        const items = listItems
          .split("\n")
          .filter((line: string) => line.trim())
          .map((line: string) => {
            const content = line.replace(/^[â€¢\-*] /, "").trim()
            return `<li>${content}</li>`
          })
          .join("")
        return `\n<ul class="message-list">${items}</ul>\n`
      })
  
      // Ordered lists
      const orderedListRegex = /(?:^|\n)((?:\d+\. .+\n?)+)/gm
      formatted = formatted.replace(orderedListRegex, (match, listItems) => {
        const items = listItems
          .split("\n")
          .filter((line: string) => line.trim())
          .map((line: string) => {
            const content = line.replace(/^\d+\. /, "").trim()
            return `<li>${content}</li>`
          })
          .join("")
        return `\n<ol class="message-list">${items}</ol>\n`
      })
  
      return formatted
    }
  
    private formatBlockquotes(text: string): string {
      const blockquoteRegex = /(?:^|\n)((?:&gt; .+\n?)+)/gm
      return text.replace(blockquoteRegex, (match, quoteLines) => {
        const content = quoteLines
          .split("\n")
          .filter((line: string) => line.trim())
          .map((line: string) => line.replace(/^&gt; /, "").trim())
          .join("<br>")
        return `\n<blockquote class="message-blockquote">${content}</blockquote>\n`
      })
    }
  
    private formatParagraphs(text: string): string {
      const paragraphs = text.split(/\n\n+/)
  
      return paragraphs
        .map((para) => {
          if (
            para.trim().startsWith("<div") ||
            para.trim().startsWith("<ul") ||
            para.trim().startsWith("<ol") ||
            para.trim().startsWith("<h") ||
            para.trim().startsWith("<pre") ||
            para.trim().startsWith("<blockquote")
          ) {
            return para
          }
  
          const withBreaks = para.replace(/\n/g, "<br>")
          return withBreaks.trim() ? `<p class="message-paragraph">${withBreaks}</p>` : ""
        })
        .filter((p) => p)
        .join("")
    }
  }
  
  // Global copy function for code blocks
  if (typeof window !== "undefined") {
    ;(window as any).copyCode = (codeId: string) => {
      const codeElement = document.getElementById(codeId)
      if (!codeElement) return
  
      const code = codeElement.textContent || ""
  
      navigator.clipboard.writeText(code).then(
        () => {
          const button = codeElement.closest(".code-block-wrapper")?.querySelector(".copy-code-button")
          if (!button) return
  
          const originalHTML = button.innerHTML
          button.innerHTML = `<svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
            <path d="M13.854 3.646a.5.5 0 0 1 0 .708l-7 7a.5.5 0 0 1-.708 0l-3.5-3.5a.5.5 0 1 1 .708-.708L6.5 10.293l6.646-6.647a.5.5 0 0 1 .708 0z"/>
          </svg>Copied!`
  
          setTimeout(() => {
            button.innerHTML = originalHTML
          }, 2000)
        },
        (err) => {
          console.error("Failed to copy code:", err)
        },
      )
    }
  }
  
  export const messageFormatter = new MessageFormatter()
  

