/**
 * Message Formatter
 * Formats assistant messages with markdown support
 */

class MessageFormatter {
    constructor() {
        this.codeBlockId = 0;
    }

    /**
     * Main formatting function
     * Converts markdown to HTML
     */
    format(text) {
        if (!text) return '';
        
        let formatted = text;
        
        // Escape HTML first to prevent XSS
        formatted = this.escapeHtml(formatted);
        
        // Format code blocks (must be done before inline code)
        formatted = this.formatCodeBlocks(formatted);
        
        // Format inline code
        formatted = this.formatInlineCode(formatted);
        
        // Format bold text
        formatted = this.formatBold(formatted);
        
        // Format italic text
        formatted = this.formatItalic(formatted);
        
        // Format links
        formatted = this.formatLinks(formatted);
        
        // Format lists
        formatted = this.formatLists(formatted);
        
        // Format line breaks and paragraphs
        formatted = this.formatParagraphs(formatted);
        
        // Format blockquotes
        formatted = this.formatBlockquotes(formatted);
        
        return formatted;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    formatCodeBlocks(text) {
        // Match code blocks with optional language
        const codeBlockRegex = /```(\w+)?\n([\s\S]*?)```/g;
        
        return text.replace(codeBlockRegex, (match, language, code) => {
            const id = `code-block-${this.codeBlockId++}`;
            const lang = language || 'text';
            
            // Unescape the code content
            const codeContent = code
                .replace(/&lt;/g, '<')
                .replace(/&gt;/g, '>')
                .replace(/&amp;/g, '&')
                .replace(/&quot;/g, '"')
                .replace(/&#039;/g, "'");
            
            return `<div class="code-block-wrapper">
                <div class="code-block-header">
                    <span class="code-language">${lang}</span>
                    <button class="copy-code-button" onclick="copyCode('${id}')">
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                            <path d="M4 2a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v2h2a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2v-2H4a2 2 0 0 1-2-2V2z"/>
                        </svg>
                        Copy
                    </button>
                </div>
                <pre class="code-block"><code id="${id}" class="language-${lang}">${codeContent}</code></pre>
            </div>`;
        });
    }

    formatInlineCode(text) {
        // Match inline code (single backticks)
        // But skip if it's part of a code block
        return text.replace(/`([^`\n]+)`/g, '<code class="inline-code">$1</code>');
    }

    formatBold(text) {
        // Match **text** or __text__
        return text
            .replace(/\*\*([^*\n]+?)\*\*/g, '<strong>$1</strong>')
            .replace(/__([^_\n]+?)__/g, '<strong>$1</strong>');
    }

    formatItalic(text) {
        // Match *text* or _text_ (but not if part of bold)
        return text
            .replace(/(?<!\*)\*(?!\*)([^*\n]+?)\*(?!\*)/g, '<em>$1</em>')
            .replace(/(?<!_)_(?!_)([^_\n]+?)_(?!_)/g, '<em>$1</em>');
    }

    formatLinks(text) {
        // Auto-link URLs
        const urlRegex = /(https?:\/\/[^\s<]+)/g;
        return text.replace(urlRegex, '<a href="$1" target="_blank" rel="noopener noreferrer" class="message-link">$1</a>');
    }

    formatLists(text) {
        // Unordered lists (- item or * item)
        let formatted = text;
        
        // Match consecutive lines starting with - or *
        const unorderedListRegex = /(?:^|\n)((?:[•\-\*] .+\n?)+)/gm;
        formatted = formatted.replace(unorderedListRegex, (match, listItems) => {
            const items = listItems
                .split('\n')
                .filter(line => line.trim())
                .map(line => {
                    const content = line.replace(/^[•\-\*] /, '').trim();
                    return `<li>${content}</li>`;
                })
                .join('');
            return `\n<ul class="message-list">${items}</ul>\n`;
        });
        
        // Ordered lists (1. item)
        const orderedListRegex = /(?:^|\n)((?:\d+\. .+\n?)+)/gm;
        formatted = formatted.replace(orderedListRegex, (match, listItems) => {
            const items = listItems
                .split('\n')
                .filter(line => line.trim())
                .map(line => {
                    const content = line.replace(/^\d+\. /, '').trim();
                    return `<li>${content}</li>`;
                })
                .join('');
            return `\n<ol class="message-list">${items}</ol>\n`;
        });
        
        return formatted;
    }

    formatParagraphs(text) {
        // Split by double line breaks and wrap in paragraphs
        const paragraphs = text.split(/\n\n+/);
        
        return paragraphs
            .map(para => {
                // Don't wrap if already in a block element
                if (para.trim().startsWith('<div') || 
                    para.trim().startsWith('<ul') || 
                    para.trim().startsWith('<ol') ||
                    para.trim().startsWith('<pre') ||
                    para.trim().startsWith('<blockquote')) {
                    return para;
                }
                
                // Convert single line breaks to <br>
                const withBreaks = para.replace(/\n/g, '<br>');
                
                return withBreaks.trim() ? `<p class="message-paragraph">${withBreaks}</p>` : '';
            })
            .filter(p => p)
            .join('');
    }

    formatBlockquotes(text) {
        // Match lines starting with >
        const blockquoteRegex = /(?:^|\n)((?:&gt; .+\n?)+)/gm;
        return text.replace(blockquoteRegex, (match, quoteLines) => {
            const content = quoteLines
                .split('\n')
                .filter(line => line.trim())
                .map(line => line.replace(/^&gt; /, '').trim())
                .join('<br>');
            return `\n<blockquote class="message-blockquote">${content}</blockquote>\n`;
        });
    }
}

// Global copy function for code blocks
function copyCode(codeId) {
    const codeElement = document.getElementById(codeId);
    if (!codeElement) return;
    
    const code = codeElement.textContent;
    
    navigator.clipboard.writeText(code).then(() => {
        // Show feedback
        const button = codeElement.closest('.code-block-wrapper').querySelector('.copy-code-button');
        const originalText = button.innerHTML;
        button.innerHTML = `<svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
            <path d="M13.854 3.646a.5.5 0 0 1 0 .708l-7 7a.5.5 0 0 1-.708 0l-3.5-3.5a.5.5 0 1 1 .708-.708L6.5 10.293l6.646-6.647a.5.5 0 0 1 .708 0z"/>
        </svg>Copied!`;
        
        setTimeout(() => {
            button.innerHTML = originalText;
        }, 2000);
    }).catch(err => {
        console.error('Failed to copy code:', err);
    });
}

// Export formatter instance
const messageFormatter = new MessageFormatter();

// Add CSS styles for formatted elements
const formatterStyles = `
<style>
.message-paragraph {
    margin: 0.5em 0;
    line-height: 1.6;
}

.inline-code {
    background: rgba(110, 118, 129, 0.1);
    padding: 0.2em 0.4em;
    border-radius: 3px;
    font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
    font-size: 0.9em;
    color: #c7254e;
}

.code-block-wrapper {
    margin: 1em 0;
    border-radius: 8px;
    overflow: hidden;
    background: #282c34;
}

.code-block-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 12px;
    background: #21252b;
    border-bottom: 1px solid #181a1f;
}

.code-language {
    font-size: 0.75em;
    color: #abb2bf;
    text-transform: uppercase;
    font-weight: 600;
}

.copy-code-button {
    background: transparent;
    border: none;
    color: #abb2bf;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 0.85em;
    transition: background 0.2s;
}

.copy-code-button:hover {
    background: rgba(255, 255, 255, 0.1);
}

.code-block {
    margin: 0;
    padding: 12px;
    overflow-x: auto;
    background: #282c34;
}

.code-block code {
    font-family: 'Monaco', 'Menlo', 'Courier New', monospace;
    font-size: 0.9em;
    line-height: 1.5;
    color: #abb2bf;
    display: block;
    white-space: pre;
}

.message-list {
    margin: 0.5em 0;
    padding-left: 1.5em;
}

.message-list li {
    margin: 0.3em 0;
    line-height: 1.5;
}

.message-link {
    color: #007bff;
    text-decoration: none;
    border-bottom: 1px solid transparent;
    transition: border-color 0.2s;
}

.message-link:hover {
    border-bottom-color: #007bff;
}

.message-blockquote {
    margin: 0.5em 0;
    padding: 0.5em 1em;
    border-left: 4px solid #007bff;
    background: rgba(0, 123, 255, 0.05);
    font-style: italic;
    color: #555;
}

strong {
    font-weight: 600;
    color: #1a1a1a;
}

em {
    font-style: italic;
}
</style>
`;

// Inject styles if not already present
if (!document.getElementById('formatter-styles')) {
    const styleEl = document.createElement('div');
    styleEl.id = 'formatter-styles';
    styleEl.innerHTML = formatterStyles;
    document.head.appendChild(styleEl.firstElementChild);
}

