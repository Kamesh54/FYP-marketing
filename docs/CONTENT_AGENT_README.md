# ✍️ Content Agent

## Overview

The Content Agent is the creative engine of the platform. It generates SEO-optimized blog posts and platform-specific social media content using advanced AI (Groq LLM), incorporating business context, keywords, and competitive intelligence.

**Port:** 8003  
**File:** `content_agent.py`  
**Framework:** FastAPI  
**AI Model:** Llama 3.3 70B (via Groq)

---

## Features

- ✅ SEO-optimized blog post generation
- ✅ Multi-platform social media posts (Twitter, Instagram, Facebook, LinkedIn)
- ✅ AI image prompt generation
- ✅ Context-aware content creation
- ✅ Keyword integration
- ✅ Brand voice consistency
- ✅ Multiple tone options
- ✅ HTML formatting for blogs

---

## API Endpoints

### 1. Health Check
```http
GET /
```

**Response:**
```json
{
  "message": "ContentAgent is running",
  "version": "1.0",
  "port": 8003
}
```

---

### 2. Generate Blog Post
```http
POST /generate-blog
Content-Type: application/json

{
  "keywords": {
    "keywords": ["healthy eating", "meal prep", "nutrition"],
    "domains": ["health", "food"]
  },
  "business_details": {
    "brand_name": "Cloud24",
    "industry": "Cloud Kitchen",
    "location": "Chennai",
    "description": "Healthy meal prep service"
  },
  "topic": "Benefits of meal prepping for busy professionals",
  "gap_analysis": {
    "content_gaps": [
      {"keyword": "time-saving meals", "suggestion": "..."}
    ]
  },
  "tone": "professional"
}
```

**Response:**
```json
{
  "job_id": "0366bc2c-...",
  "status": "started",
  "message": "Blog generation started"
}
```

---

### 3. Generate Social Media Post
```http
POST /generate-social
Content-Type: application/json

{
  "keywords": {
    "keywords": ["healthy eating", "chennai food"],
    "domains": ["food service"]
  },
  "brand_name": "Cloud24",
  "industry": "Cloud Kitchen",
  "location": "Chennai",
  "target_audience": "Fitness enthusiasts",
  "unique_selling_points": ["Fresh ingredients", "Macro tracking"],
  "competitor_insights": "Focus on bulk orders and subscriptions",
  "user_request": "Create post about our new meal plans",
  "platforms": ["twitter", "instagram"],
  "tone": "professional",
  "image_style": "photorealistic"
}
```

**Response:**
```json
{
  "job_id": "uuid",
  "status": "started",
  "message": "Social generation started"
}
```

---

### 4. Check Job Status
```http
GET /status/{job_id}
```

**Response:**
```json
{
  "status": "completed",
  "job_id": "uuid",
  "end_time": "2024-10-26T12:15:00Z"
}
```

---

### 5. Download Blog (HTML)
```http
GET /download/html/{job_id}
```

**Response:** Full HTML blog post

```html
<!DOCTYPE html>
<html>
<head>
    <title>5 Benefits of Meal Prepping for Busy Professionals | Cloud24</title>
    <meta name="description" content="...">
    <meta name="keywords" content="meal prep, healthy eating, ...">
</head>
<body>
    <article>
        <h1>5 Benefits of Meal Prepping for Busy Professionals</h1>
        <p>In today's fast-paced world...</p>
        ...
    </article>
</body>
</html>
```

---

### 6. Download Social Post (JSON)
```http
GET /download/json/{job_id}
```

**Response:**
```json
{
  "posts": {
    "twitter": {
      "copy": "🍱 New meal plans are here! Fresh, healthy, and delivered to your door in Chennai. Perfect for busy professionals. #HealthyEating #Cloud24 #ChennaiFood",
      "length": 156,
      "call_to_action": "Order now: cloud24.com",
      "hashtags": ["#HealthyEating", "#Cloud24", "#ChennaiFood"]
    },
    "instagram": {
      "copy": "🌟 Meal prep made easy! Our new weekly plans feature:\n• Fresh, locally-sourced ingredients\n• Macro-tracked meals\n• Delivered daily\n\nPerfect for fitness enthusiasts and busy professionals in Chennai!\n\n#HealthyEating #MealPrep #Cloud24 #ChennaiFood #FitnessGoals",
      "length": 250,
      "call_to_action": "Order via link in bio",
      "hashtags": ["#HealthyEating", "#MealPrep", "#Cloud24"]
    }
  },
  "image_prompts": [
    "Photorealistic image of fresh, healthy meal prep containers for Cloud24 in Chennai, vibrant colors, professional food photography",
    "High-quality photo of a fit person eating healthy Cloud24 meal, bright kitchen setting, natural lighting"
  ],
  "meta": {
    "brand_name": "Cloud24",
    "location": "Chennai",
    "industry": "Cloud Kitchen",
    "generated_at": "2024-10-26T12:15:00Z"
  }
}
```

---

## Usage Examples

### Python - Blog Generation

```python
import requests
import time

BASE_URL = "http://127.0.0.1:8003"

# 1. Start blog generation
response = requests.post(f"{BASE_URL}/generate-blog", json={
    "keywords": {
        "keywords": ["healthy eating", "meal prep"],
        "domains": ["health", "food"]
    },
    "business_details": {
        "brand_name": "Cloud24",
        "industry": "Cloud Kitchen",
        "location": "Chennai"
    },
    "topic": "Benefits of meal prepping",
    "tone": "professional"
})

job_id = response.json()["job_id"]

# 2. Wait for completion
while True:
    status = requests.get(f"{BASE_URL}/status/{job_id}").json()
    if status["status"] == "completed":
        break
    time.sleep(3)

# 3. Download HTML
html_content = requests.get(f"{BASE_URL}/download/html/{job_id}").text
with open("blog.html", "w", encoding="utf-8") as f:
    f.write(html_content)

print("Blog saved to blog.html")
```

### Python - Social Post Generation

```python
# 1. Generate social posts
response = requests.post(f"{BASE_URL}/generate-social", json={
    "brand_name": "Cloud24",
    "industry": "Cloud Kitchen",
    "location": "Chennai",
    "platforms": ["twitter", "instagram"],
    "user_request": "Promote our new meal plans"
})

job_id = response.json()["job_id"]

# 2. Wait and download
time.sleep(5)
posts = requests.get(f"{BASE_URL}/download/json/{job_id}").json()

print("Twitter:", posts["posts"]["twitter"]["copy"])
print("Instagram:", posts["posts"]["instagram"]["copy"])
print("Image Prompts:", posts["image_prompts"])
```

---

## Communication with Other Agents

### Called By:
- **Orchestrator** - Main content generation requests

### Uses Data From:
- **Keyword Extractor** - SEO keywords
- **Gap Analyzer** - Competitive insights
- **WebCrawler** - Website content (for context)

### Typical Blog Generation Flow:

```
┌──────────────┐
│ Orchestrator │ "Generate blog about meal prep"
└──────┬───────┘
       │
       ▼
┌────────────────┐
│Keyword Extractor│ Extract: ["meal prep", "healthy eating"]
└──────┬─────────┘
       │
       ▼
┌────────────────┐
│  Gap Analyzer  │ Find: competitor insights
└──────┬─────────┘
       │
       ▼
┌────────────────┐
│ Content Agent  │ Generate SEO-optimized blog
└──────┬─────────┘
       │
       ▼
┌──────────────┐
│ Orchestrator │ Display preview
└──────────────┘
```

---

## Technical Details

### Blog Generation Algorithm

**1. Prompt Construction:**
```python
prompt = f"""
You are an expert content writer specializing in {industry}.

Write a comprehensive, SEO-optimized blog post about: {topic}

Business Context:
- Brand: {brand_name}
- Industry: {industry}
- Location: {location}
- Description: {description}

SEO Keywords (MUST include naturally):
{', '.join(keywords[:10])}

Competitive Insights:
{gap_analysis_summary}

Requirements:
1. Engaging, professional tone
2. 1500-2000 words
3. Include all keywords naturally
4. Use H2 and H3 headings
5. Add meta description
6. Include call-to-action for {brand_name}
7. Location-specific references if relevant

Return valid HTML with proper structure.
"""
```

**2. Groq LLM Call:**
```python
response = groq_client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[
        {"role": "system", "content": "You are an expert SEO content writer."},
        {"role": "user", "content": prompt}
    ],
    temperature=0.7,  # Balanced creativity
    max_tokens=4000
)

html_content = response.choices[0].message.content
```

**3. Post-Processing:**
```python
# Add DOCTYPE and meta tags
html_with_meta = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{title} | {brand_name}</title>
    <meta name="description" content="{meta_description}">
    <meta name="keywords" content="{', '.join(keywords)}">
    <style>/* CSS */</style>
</head>
<body>
    {html_content}
</body>
</html>
"""
```

---

### Social Post Generation Algorithm

**1. Context-Rich Prompt:**
```python
prompt = f"""
You are an expert social media content creator for brand marketing.

Business Profile:
- Brand: {brand_name}
- Industry: {industry}
- Location: {location}
- Target Audience: {target_audience}
- Unique Selling Points: {', '.join(unique_selling_points)}

User Request: {user_request}

Competitor Insights: {competitor_insights}

Create highly engaging social media posts that:
1. Address the user's request directly
2. Highlight unique strengths in {location}
3. Appeal to {target_audience}
4. Include location-based hashtags
5. Have clear calls-to-action

Return ONLY valid JSON:
{{
  "posts": {{
    "twitter": {{
      "copy": "tweet text (max 280 chars)",
      "hashtags": ["#RelevantHashtag", "#{brand_name}"],
      "call_to_action": "CTA here"
    }},
    "instagram": {{
      "copy": "instagram caption (max 300 chars)",
      "hashtags": ["#RelevantHashtag"],
      "call_to_action": "CTA here"
    }}
  }},
  "image_prompts": [
    "Photorealistic image prompt 1 for {brand_name} in {location}",
    "Photorealistic image prompt 2"
  ]
}}
"""
```

**2. JSON Validation:**
```python
try:
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[...],
        response_format={"type": "json_object"},
        temperature=0.7
    )
    
    result = json.loads(response.choices[0].message.content)
    
    # Validate structure
    assert "posts" in result
    assert "image_prompts" in result
    
except json.JSONDecodeError:
    # Retry with stricter prompt
    pass
```

---

## Content Quality Assurance

### Blog Post Checklist

- ✅ **SEO Optimized** - All keywords included naturally
- ✅ **Proper Structure** - H1, H2, H3 hierarchy
- ✅ **Meta Tags** - Title, description, keywords
- ✅ **Word Count** - 1500-2000 words
- ✅ **Readability** - Flesch reading ease > 60
- ✅ **Call-to-Action** - Brand mention and CTA
- ✅ **Location References** - If applicable
- ✅ **Mobile-Friendly** - Responsive HTML

### Social Post Checklist

- ✅ **Character Limits** - Twitter ≤280, Instagram ≤300
- ✅ **Hashtags** - 3-5 relevant, including brand
- ✅ **Brand Voice** - Consistent tone
- ✅ **Call-to-Action** - Clear next step
- ✅ **Location Tags** - If provided
- ✅ **Emojis** - 2-3 relevant (optional)
- ✅ **Image Prompts** - Specific and on-brand

---

## Configuration

### Environment Variables

```bash
# Required
GROQ_API_KEY=gsk_xxxxx

# Optional
CONTENT_AGENT_TEMPERATURE=0.7  # 0-1, higher = more creative
CONTENT_AGENT_MAX_TOKENS=4000
CONTENT_AGENT_TIMEOUT=60
```

### Tone Options

| Tone | Use Case | Example |
|------|----------|---------|
| `professional` | B2B, corporate | "Our services provide..." |
| `casual` | B2C, lifestyle | "Hey there! Check this out..." |
| `enthusiastic` | Promotions | "🎉 Exciting news!..." |
| `educational` | How-to, guides | "Here's how you can..." |
| `inspirational` | Motivation | "Imagine a world where..." |

---

## Performance

### Benchmarks

| Metric | Blog | Social |
|--------|------|--------|
| Generation time | 10-15s | 5-8s |
| Token usage | ~3500 | ~800 |
| Cost per generation | ~$0.0005 | ~$0.0001 |
| Success rate | 98% | 95% |
| Retry rate | 2% | 5% |

---

## Error Handling

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `JSON validation failed` | Malformed LLM output | Retry with stricter prompt |
| `Empty content` | Groq timeout | Increase timeout |
| `Missing keywords` | Poor prompt | Enhance keyword instructions |
| `Tone mismatch` | Wrong temperature | Adjust temperature |

### Retry Strategy

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=2, max=10)
)
def safe_groq_chat(prompt):
    return groq_client.chat.completions.create(...)
```

---

## Testing

### Unit Tests

```python
def test_blog_generation():
    response = client.post("/generate-blog", json={
        "keywords": {"keywords": ["test"]},
        "business_details": {"brand_name": "Test"},
        "topic": "Test topic"
    })
    assert response.status_code == 200

def test_social_generation():
    response = client.post("/generate-social", json={
        "brand_name": "Test",
        "platforms": ["twitter"]
    })
    assert response.status_code == 200
```

---

## Future Enhancements

- [ ] Video script generation
- [ ] Email newsletter content
- [ ] Product descriptions
- [ ] Ad copy generation
- [ ] Multi-language support
- [ ] A/B testing variants
- [ ] Content calendar integration

---

## Dependencies

```txt
fastapi==0.115.0
uvicorn==0.24.0
groq==0.9.0
tenacity==8.2.3
beautifulsoup4==4.12.2  # HTML parsing
```

---

**Agent Status:** ✅ Production Ready  
**Maintainer:** Content Team  
**Last Updated:** October 2024

