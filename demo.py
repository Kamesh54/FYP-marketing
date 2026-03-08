"""
demo.py  –  End-to-End Pipeline Demo
======================================
Runs the full multi-agent workflow and saves a self-contained HTML report.

Usage:
    python demo.py
    python demo.py --topic "cloud kitchen Chennai" --brand "SpiceBox" --url "https://spicebox.in"

Make sure all agents are running first (start.bat).
"""

import argparse
import json
import os
import sys
import time
import requests
from datetime import datetime

# ─────────────────────────── CONFIG ───────────────────────────
KEYWORD_AGENT   = "http://127.0.0.1:8001"
GAP_AGENT       = "http://127.0.0.1:8002"
CONTENT_AGENT   = "http://127.0.0.1:8003"
POLL_INTERVAL   = 3   # seconds between status polls
MAX_WAIT        = 300  # seconds before giving up

BOLD  = "\033[1m"
GREEN = "\033[92m"
CYAN  = "\033[96m"
YELLOW= "\033[93m"
RED   = "\033[91m"
RESET = "\033[0m"


# ─────────────────────────── HELPERS ──────────────────────────

def banner(text):
    line = "═" * (len(text) + 4)
    print(f"\n{CYAN}{BOLD}╔{line}╗")
    print(f"║  {text}  ║")
    print(f"╚{line}╝{RESET}")

def step(n, text):
    print(f"\n{YELLOW}{BOLD}[STEP {n}] {text}{RESET}")

def ok(text):
    print(f"  {GREEN}✔  {text}{RESET}")

def fail(text):
    print(f"  {RED}✘  {text}{RESET}")
    sys.exit(1)

def info(text):
    print(f"  {CYAN}→  {text}{RESET}")


def check_service(url, name):
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        ok(f"{name} is UP  ({url})")
        return True
    except Exception as e:
        fail(f"{name} is DOWN at {url} — start it first!\n    Error: {e}")


def post_job(url, payload, service_name):
    try:
        r = requests.post(url, json=payload, timeout=120)
        r.raise_for_status()
        data = r.json()
        job_id = data.get("job_id")
        if not job_id:
            fail(f"{service_name} did not return a job_id. Response: {data}")
        ok(f"Job submitted → {job_id}")
        return job_id
    except Exception as e:
        fail(f"Failed to submit job to {service_name}: {e}")


def poll_job(status_url, job_label):
    elapsed = 0
    while elapsed < MAX_WAIT:
        try:
            r = requests.get(status_url, timeout=10)
            r.raise_for_status()
            data = r.json()
            status = data.get("status", "unknown")
            if status == "completed":
                ok(f"{job_label} completed in {elapsed}s")
                return data
            elif status == "failed":
                fail(f"{job_label} failed: {data.get('message', 'unknown error')}")
            else:
                info(f"  [{elapsed:>3}s]  status = {status} …")
        except Exception as e:
            info(f"  [{elapsed:>3}s]  polling error: {e}")
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
    fail(f"{job_label} timed out after {MAX_WAIT}s")


def read_result_file(path, label):
    if not path or not os.path.exists(path):
        fail(f"Result file not found for {label}: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ─────────────────────────── PIPELINE ─────────────────────────

def run_pipeline(topic, brand, url):
    banner("Multi-Agent Content Marketing Platform — LIVE DEMO")
    print(f"  Topic  : {BOLD}{topic}{RESET}")
    print(f"  Brand  : {BOLD}{brand}{RESET}")
    print(f"  URL    : {BOLD}{url or '(none)'}{RESET}")
    print(f"  Time   : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # ── 0. Health checks ───────────────────────────────────────
    step(0, "Verifying all agents are running")
    check_service(KEYWORD_AGENT, "Keyword Extractor (8001)")
    check_service(GAP_AGENT,     "Gap Analyzer      (8002)")
    check_service(CONTENT_AGENT, "Content Agent     (8003)")

    # ── 1. Keyword Extraction ──────────────────────────────────
    step(1, "Keyword Extraction  →  Agent 8001")
    info(f"Statement: \"{topic}\"")
    kw_job_id = post_job(
        f"{KEYWORD_AGENT}/extract-keywords",
        {"customer_statement": topic, "max_results": 3, "max_pages": 1},
        "Keyword Extractor"
    )
    kw_status = poll_job(f"{KEYWORD_AGENT}/status/{kw_job_id}", "Keyword Extraction")
    kw_data = read_result_file(kw_status.get("results_file"), "Keywords")

    # Summarise
    total_kw = sum(len(c.get("short_keywords", [])) + len(c.get("long_tail_keywords", [])) for c in kw_data)
    ok(f"Competitors crawled : {len(kw_data)}")
    ok(f"Total keywords found: {total_kw}")
    for comp in kw_data:
        print(f"    • {comp.get('competitor_name','?')}  ({comp.get('url','')})")
        print(f"      Top keywords: {', '.join(comp.get('short_keywords', [])[:5])}")

    # ── 2. Competitor Gap Analysis ─────────────────────────────
    step(2, "Competitor Gap Analysis  →  Agent 8002")
    gap_job_id = post_job(
        f"{GAP_AGENT}/analyze-keyword-gap",
        {
            "company_name": brand,
            "company_url": url or None,
            "product_description": f"{brand} — {topic}",
            "max_competitors": 3,
            "max_pages": 1
        },
        "Gap Analyzer"
    )
    gap_status = poll_job(f"{GAP_AGENT}/status/{gap_job_id}", "Gap Analysis")
    gap_data = read_result_file(gap_status.get("results_file"), "Gap Analysis")

    ga = gap_data.get("gap_analysis", {})
    summary = gap_data.get("summary", {})
    ok(f"Missing short keywords     : {summary.get('missing_short_keywords', 0)}")
    ok(f"Missing long-tail keywords : {summary.get('missing_long_tail_keywords', 0)}")
    ok(f"Unique brand keywords      : {summary.get('unique_company_keywords', 0)}")
    ok(f"Organic opportunities      : {summary.get('organic_opportunities', 0)}")
    print(f"\n  {BOLD}Top recommendations:{RESET}")
    for r in ga.get("recommendations", [])[:3]:
        print(f"    → {r}")

    # ── 3. Blog Generation ─────────────────────────────────────
    step(3, "SEO Blog Generation  →  Agent 8003")
    # Flatten best keywords for the blog
    best_kws = [c.get("short_keywords", [])[:5] for c in kw_data]
    flat_kws = [kw for group in best_kws for kw in group][:15]
    info(f"Seeding blog with keywords: {', '.join(flat_kws[:8])}")

    blog_job_id = post_job(
        f"{CONTENT_AGENT}/generate-blog",
        {
            "business_details": f"{brand} — {topic}",
            "keywords": {"short_keywords": flat_kws, "long_tail_keywords": []},
            "target_tone": "professional",
            "blog_length": "medium"
        },
        "Content Agent"
    )
    blog_status = poll_job(f"{CONTENT_AGENT}/status/{blog_job_id}", "Blog Generation")

    # Download the blog HTML
    blog_html = ""
    try:
        dl = requests.get(f"{CONTENT_AGENT}/download/html/{blog_job_id}", timeout=30)
        dl.raise_for_status()
        blog_html = dl.text
        ok(f"Blog HTML downloaded ({len(blog_html):,} chars)")
    except Exception as e:
        info(f"Could not download blog HTML: {e}")
        # try reading from file path in status
        blog_file = blog_status.get("output_file") or blog_status.get("results_file")
        if blog_file and os.path.exists(blog_file):
            with open(blog_file, "r", encoding="utf-8") as f:
                blog_html = f.read()
            ok(f"Blog HTML read from file ({len(blog_html):,} chars)")

    # ── 4. Build Master Report ─────────────────────────────────
    step(4, "Building HTML report")
    report_path = build_report(topic, brand, kw_data, gap_data, blog_html)
    ok(f"Report saved → {report_path}")

    banner("DEMO COMPLETE")
    print(f"\n  Open this file in your browser:\n")
    print(f"  {BOLD}{os.path.abspath(report_path)}{RESET}\n")
    return report_path


# ─────────────────────────── REPORT ───────────────────────────

def build_report(topic, brand, kw_data, gap_data, blog_html):
    ga      = gap_data.get("gap_analysis", {})
    summary = gap_data.get("summary", {})
    comp_info   = gap_data.get("competitor_analysis", {})
    competitors = comp_info.get("competitor_details", [])

    # Keyword cards
    kw_cards = ""
    for comp in kw_data:
        kws = ", ".join(comp.get("short_keywords", [])[:8])
        kw_cards += f"""
        <div class="card">
            <h3>🌐 {comp.get('competitor_name','Unknown')}</h3>
            <a href="{comp.get('url','#')}" target="_blank" class="url">{comp.get('url','')}</a>
            <p class="kw-list">{kws}</p>
        </div>"""

    # Gap pills
    def pills(items, cls):
        return "".join(f'<span class="pill {cls}">{i}</span>' for i in items[:12])

    missing_short_pills  = pills(ga.get("missing_keywords", {}).get("short", []),    "pill-red")
    missing_long_pills   = pills(ga.get("missing_keywords", {}).get("long_tail", []),"pill-orange")
    unique_pills         = pills(
        ga.get("unique_company_keywords", {}).get("short", []) +
        ga.get("unique_company_keywords", {}).get("long_tail", []), "pill-green")
    opps_pills           = pills(
        ga.get("organic_opportunities", {}).get("short", []) +
        ga.get("organic_opportunities", {}).get("long_tail", []), "pill-blue")

    recs_html = "".join(f"<li>{r}</li>" for r in ga.get("recommendations", []))
    insights_html = "".join(f"<li>{i}</li>" for i in ga.get("competitive_insights", []))

    comp_rows = "".join(
        f"""<tr>
              <td>{c.get('name','?')}</td>
              <td>{c.get('url','')}</td>
              <td>{c.get('short_keywords_count',0)}</td>
              <td>{c.get('long_tail_keywords_count',0)}</td>
           </tr>""" for c in competitors)

    blog_section = f"""
        <div class="blog-wrapper">
            <iframe srcdoc="{blog_html.replace('"', '&quot;')}" style="width:100%;height:700px;border:none;border-radius:12px;"></iframe>
        </div>""" if blog_html else "<p><em>Blog not generated.</em></p>"

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Demo Report — {brand}</title>
<style>
  :root{{--bg:#0f1117;--card:#1a1d27;--accent:#6c63ff;--green:#22c55e;--red:#ef4444;--orange:#f97316;--blue:#3b82f6;--text:#e2e8f0;--sub:#94a3b8;}}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'Segoe UI',sans-serif;background:var(--bg);color:var(--text);padding:40px 20px}}
  h1{{font-size:2rem;background:linear-gradient(135deg,#6c63ff,#22c55e);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:4px}}
  .meta{{color:var(--sub);font-size:.85rem;margin-bottom:40px}}
  h2{{font-size:1.2rem;color:var(--accent);margin:40px 0 16px;letter-spacing:.5px;text-transform:uppercase}}
  .stat-row{{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:24px}}
  .stat{{background:var(--card);border-radius:12px;padding:20px 28px;flex:1;min-width:160px;border:1px solid #ffffff10}}
  .stat .num{{font-size:2rem;font-weight:700;color:var(--accent)}}
  .stat .lbl{{color:var(--sub);font-size:.8rem;margin-top:4px}}
  .cards{{display:flex;gap:16px;flex-wrap:wrap}}
  .card{{background:var(--card);border-radius:12px;padding:20px;flex:1;min-width:260px;border:1px solid #ffffff10}}
  .card h3{{margin-bottom:6px;font-size:1rem}}
  .url{{color:var(--accent);font-size:.78rem;word-break:break-all;display:block;margin-bottom:8px}}
  .kw-list{{color:var(--sub);font-size:.82rem;line-height:1.6}}
  .pill{{display:inline-block;padding:3px 10px;border-radius:20px;font-size:.75rem;margin:3px}}
  .pill-red{{background:#ef444420;color:#ef4444;border:1px solid #ef444440}}
  .pill-orange{{background:#f9731620;color:#f97316;border:1px solid #f9731640}}
  .pill-green{{background:#22c55e20;color:#22c55e;border:1px solid #22c55e40}}
  .pill-blue{{background:#3b82f620;color:#3b82f6;border:1px solid #3b82f640}}
  table{{width:100%;border-collapse:collapse;background:var(--card);border-radius:12px;overflow:hidden}}
  th{{background:#6c63ff20;color:var(--accent);padding:12px 16px;text-align:left;font-size:.8rem;text-transform:uppercase}}
  td{{padding:11px 16px;border-top:1px solid #ffffff08;font-size:.85rem;color:var(--sub)}}
  ul{{padding-left:20px;color:var(--sub);line-height:1.9;font-size:.9rem}}
  .section{{margin-bottom:48px}}
  .badge{{display:inline-block;background:var(--accent);color:#fff;padding:2px 10px;border-radius:6px;font-size:.72rem;margin-left:8px;vertical-align:middle}}
  .blog-wrapper{{border-radius:12px;overflow:hidden;border:1px solid #ffffff15}}
</style>
</head>
<body>

<h1>🚀 Multi-Agent Platform — Demo Report</h1>
<p class="meta">Brand: <strong>{brand}</strong> &nbsp;|&nbsp; Topic: <strong>{topic}</strong> &nbsp;|&nbsp; Generated: {ts}</p>

<!-- ── SUMMARY STATS ── -->
<div class="section">
<h2>📊 Pipeline Summary</h2>
<div class="stat-row">
  <div class="stat"><div class="num">{len(kw_data)}</div><div class="lbl">Competitors Crawled</div></div>
  <div class="stat"><div class="num">{summary.get('missing_short_keywords',0) + summary.get('missing_long_tail_keywords',0)}</div><div class="lbl">Keyword Gaps Found</div></div>
  <div class="stat"><div class="num">{summary.get('unique_company_keywords',0)}</div><div class="lbl">Unique Brand Keywords</div></div>
  <div class="stat"><div class="num">{summary.get('organic_opportunities',0)}</div><div class="lbl">Organic Opportunities</div></div>
  <div class="stat"><div class="num">{'✓' if blog_html else '–'}</div><div class="lbl">Blog Generated</div></div>
</div>
</div>

<!-- ── STEP 1: KEYWORDS ── -->
<div class="section">
<h2>🔍 Step 1 — Competitor Keyword Extraction <span class="badge">Agent 8001</span></h2>
<div class="cards">{kw_cards}</div>
</div>

<!-- ── STEP 2: GAP ANALYSIS ── -->
<div class="section">
<h2>📈 Step 2 — Competitor Gap Analysis <span class="badge">Agent 8002</span></h2>

<h2 style="font-size:.95rem;color:var(--sub);margin-top:0;text-transform:none">Competitors Analyzed</h2>
<table style="margin-bottom:24px">
  <thead><tr><th>Name</th><th>URL</th><th>Short KWs</th><th>Long-tail KWs</th></tr></thead>
  <tbody>{comp_rows}</tbody>
</table>

<p style="color:var(--sub);font-size:.85rem;margin-bottom:10px"><strong style="color:var(--text)">Missing Short Keywords</strong> — your competitors rank for these, you don't:</p>
<div style="margin-bottom:16px">{missing_short_pills or '<em style="color:var(--sub)">None found</em>'}</div>

<p style="color:var(--sub);font-size:.85rem;margin-bottom:10px"><strong style="color:var(--text)">Missing Long-tail Keywords:</strong></p>
<div style="margin-bottom:16px">{missing_long_pills or '<em style="color:var(--sub)">None found</em>'}</div>

<p style="color:var(--sub);font-size:.85rem;margin-bottom:10px"><strong style="color:var(--text)">Your Unique Keywords</strong> — competitive advantage:</p>
<div style="margin-bottom:16px">{unique_pills or '<em style="color:var(--sub)">None found</em>'}</div>

<p style="color:var(--sub);font-size:.85rem;margin-bottom:10px"><strong style="color:var(--text)">Organic Opportunities:</strong></p>
<div style="margin-bottom:24px">{opps_pills or '<em style="color:var(--sub)">None found</em>'}</div>

<h2 style="font-size:.95rem;color:var(--sub);margin-top:0;text-transform:none">AI Recommendations</h2>
<ul>{recs_html or '<li>No recommendations generated.</li>'}</ul>

<h2 style="font-size:.95rem;color:var(--sub);margin-top:16px;text-transform:none">Competitive Insights</h2>
<ul>{insights_html or '<li>No insights generated.</li>'}</ul>
</div>

<!-- ── STEP 3: BLOG ── -->
<div class="section">
<h2>✍️ Step 3 — SEO Blog Post <span class="badge">Agent 8003</span></h2>
{blog_section}
</div>

</body>
</html>"""

    fname = f"demo_report_{brand.replace(' ','_').lower()}_{int(time.time())}.html"
    with open(fname, "w", encoding="utf-8") as f:
        f.write(html)
    return fname


# ─────────────────────────── ENTRY ────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-Agent Platform End-to-End Demo")
    parser.add_argument("--topic", default="cloud kitchen food delivery Chennai",
                        help="Market/product topic to analyse")
    parser.add_argument("--brand", default="SpiceBox",
                        help="Your brand name")
    parser.add_argument("--url",   default="",
                        help="Your website URL (optional)")
    args = parser.parse_args()

    run_pipeline(
        topic=args.topic,
        brand=args.brand,
        url=args.url or None
    )
