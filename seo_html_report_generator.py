"""
SEO HTML Report Generator
Generates richer, user-friendly HTML reports for SEO analysis results.
"""
import html
import os
from datetime import datetime
from urllib.parse import urlparse


def _score_to_percent(value) -> int:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0

    if numeric <= 1:
        numeric *= 100
    return max(0, min(100, round(numeric)))


def _score_band(score: int) -> str:
    if score >= 85:
        return "Excellent"
    if score >= 70:
        return "Strong"
    if score >= 50:
        return "Needs Work"
    return "Critical"


def _score_color(score: int) -> str:
    if score >= 85:
        return "#16a34a"
    if score >= 70:
        return "#65a30d"
    if score >= 50:
        return "#d97706"
    return "#dc2626"


def _safe_text(value, default="N/A") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return html.escape(text) if text else default


def _format_bool(value) -> str:
    return "Yes" if value else "No"


def _normalize_recommendations(recommendations):
    normalized = []
    for rec in recommendations or []:
        if not isinstance(rec, dict):
            continue
        normalized.append(
            {
                "priority": rec.get("priority", "Medium"),
                "area": rec.get("area", "SEO"),
                "issue": rec.get("issue", "Issue found"),
                "suggestion": rec.get("suggestion", "Review and improve this area."),
            }
        )
    return normalized


def _detail_rows(details: dict):
    title = details.get("title", {}) if isinstance(details.get("title"), dict) else {}
    meta = details.get("meta_description", {}) if isinstance(details.get("meta_description"), dict) else {}
    headings = details.get("headings", {}) if isinstance(details.get("headings"), dict) else {}
    images = details.get("images", {}) if isinstance(details.get("images"), dict) else {}
    links = details.get("links", {}) if isinstance(details.get("links"), dict) else {}
    content = details.get("content", {}) if isinstance(details.get("content"), dict) else {}

    return {
        "Content Structure": [
            ("Title length", title.get("length")),
            ("Meta description length", meta.get("length")),
            ("Word count", content.get("word_count")),
            ("Paragraph count", content.get("paragraph_count")),
            ("H1 headings", headings.get("h1_count")),
            ("H2 headings", headings.get("h2_count")),
            ("H3 headings", headings.get("h3_count")),
        ],
        "Media & Links": [
            ("Total images", images.get("total")),
            ("Alt text coverage", images.get("alt_coverage")),
            ("Internal links", links.get("internal")),
            ("External links", links.get("external")),
        ],
        "Technical Signals": [
            ("HTTPS enabled", _format_bool(details.get("https"))),
            ("Canonical present", _format_bool(details.get("canonical")) if "canonical" in details else None),
            ("Indexable", _format_bool(details.get("indexable")) if "indexable" in details else None),
            ("Schema markup", _format_bool(details.get("schema")) if "schema" in details else None),
        ],
    }


def generate_seo_html_report(url: str, analysis_data: dict) -> str:
    """
    Generate an HTML report from SEO analysis data.
    Returns the file path to the generated report.
    """
    try:
        domain = urlparse(url).netloc.replace("www.", "").replace(".", "_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"seo_report_{domain}_{timestamp}.html"
        filepath = os.path.join(os.getcwd(), filename)

        final_url = analysis_data.get("final_url", url)
        score_map = analysis_data.get("scores", {}) if isinstance(analysis_data.get("scores"), dict) else {}
        details = analysis_data.get("details", {}) if isinstance(analysis_data.get("details"), dict) else {}
        recommendations = _normalize_recommendations(analysis_data.get("recommendations", []))

        overall_score = _score_to_percent(
            analysis_data.get("overall_score", analysis_data.get("seo_score", score_map.get("overall", 0)))
        )
        score_label = _score_band(overall_score)
        score_color = _score_color(overall_score)

        category_scores = []
        for key, value in score_map.items():
            if key in {"overall", "recommendations", "high_priority", "medium_priority", "low_priority", "issues", "opportunities"}:
                continue
            category_scores.append(
                {
                    "label": key.replace("_", " ").title(),
                    "score": _score_to_percent(value),
                }
            )
        category_scores.sort(key=lambda item: item["score"])

        high_items = [r for r in recommendations if r["priority"] == "High"]
        medium_items = [r for r in recommendations if r["priority"] == "Medium"]
        low_items = [r for r in recommendations if r["priority"] == "Low"]

        strengths = []
        watchlist = []
        for item in sorted(category_scores, key=lambda entry: entry["score"], reverse=True):
            label = item["label"]
            score = item["score"]
            if score >= 75 and len(strengths) < 3:
                strengths.append(f"{label} is performing well at {score}/100.")
            if score < 60 and len(watchlist) < 3:
                watchlist.append(f"{label} needs attention at {score}/100.")

        if not strengths:
            strengths.append("No category is clearly strong yet; this report highlights where to improve first.")
        if not watchlist:
            watchlist.append("No critical category gaps were detected in the available SEO data.")

        recommendation_cards = []
        for idx, rec in enumerate(recommendations, start=1):
            priority = rec["priority"]
            priority_color = "#dc2626" if priority == "High" else "#d97706" if priority == "Medium" else "#16a34a"
            recommendation_cards.append(
                f"""
                <article class="recommendation-card">
                    <div class="recommendation-meta">
                        <span class="priority-pill" style="background:{priority_color}15;color:{priority_color};border-color:{priority_color}55;">{_safe_text(priority)}</span>
                        <span class="area-pill">{_safe_text(rec["area"])}</span>
                        <span class="item-number">#{idx}</span>
                    </div>
                    <h3>{_safe_text(rec["issue"])}</h3>
                    <p>{_safe_text(rec["suggestion"])}</p>
                </article>
                """
            )

        category_cards = []
        for item in category_scores:
            score = item["score"]
            color = _score_color(score)
            category_cards.append(
                f"""
                <div class="category-card">
                    <div class="category-top">
                        <div>
                            <div class="category-label">{_safe_text(item["label"])}</div>
                            <div class="category-band" style="color:{color};">{_safe_text(_score_band(score))}</div>
                        </div>
                        <div class="category-score" style="border-color:{color};color:{color};">{score}</div>
                    </div>
                    <div class="progress-track">
                        <div class="progress-fill" style="width:{score}%;background:{color};"></div>
                    </div>
                </div>
                """
            )

        metric_sections = []
        for section_name, rows in _detail_rows(details).items():
            section_rows = []
            for label, value in rows:
                if value in (None, "", "N/A"):
                    continue
                section_rows.append(
                    f"""
                    <div class="metric-row">
                        <span>{_safe_text(label)}</span>
                        <strong>{_safe_text(value)}</strong>
                    </div>
                    """
                )

            if section_rows:
                metric_sections.append(
                    f"""
                    <div class="metric-section">
                        <h3>{_safe_text(section_name)}</h3>
                        {''.join(section_rows)}
                    </div>
                    """
                )

        next_steps = []
        for rec in (high_items[:2] + medium_items[:2])[:4]:
            next_steps.append(
                f"<li><strong>{_safe_text(rec['area'])}:</strong> {_safe_text(rec['suggestion'])}</li>"
            )
        if not next_steps:
            next_steps.append("<li>No urgent remediation steps were generated from the current analysis.</li>")

        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>SEO Report - {_safe_text(final_url)}</title>
            <style>
                * {{
                    box-sizing: border-box;
                }}
                body {{
                    margin: 0;
                    font-family: Georgia, 'Times New Roman', serif;
                    color: #172033;
                    background:
                        radial-gradient(circle at top right, rgba(18, 126, 255, 0.10), transparent 30%),
                        radial-gradient(circle at left center, rgba(22, 163, 74, 0.08), transparent 28%),
                        #f6f7fb;
                }}
                .container {{
                    max-width: 1180px;
                    margin: 0 auto;
                    padding: 32px 18px 56px;
                }}
                .hero {{
                    background: linear-gradient(135deg, #0f172a, #1d4ed8 60%, #38bdf8);
                    color: #fff;
                    border-radius: 24px;
                    padding: 34px;
                    box-shadow: 0 22px 60px rgba(15, 23, 42, 0.24);
                    margin-bottom: 24px;
                }}
                .hero-grid {{
                    display: grid;
                    grid-template-columns: 1.5fr 320px;
                    gap: 24px;
                    align-items: center;
                }}
                .eyebrow {{
                    text-transform: uppercase;
                    letter-spacing: 0.14em;
                    font-size: 12px;
                    opacity: 0.8;
                    margin-bottom: 12px;
                }}
                h1 {{
                    margin: 0 0 12px;
                    font-size: 42px;
                    line-height: 1.1;
                }}
                .hero p {{
                    margin: 0;
                    font-size: 16px;
                    line-height: 1.7;
                    max-width: 760px;
                    color: rgba(255,255,255,0.88);
                }}
                .audit-url {{
                    margin-top: 18px;
                    display: inline-block;
                    padding: 10px 14px;
                    border-radius: 999px;
                    background: rgba(255,255,255,0.12);
                    border: 1px solid rgba(255,255,255,0.18);
                    font-size: 13px;
                    word-break: break-word;
                }}
                .score-panel {{
                    background: rgba(255,255,255,0.12);
                    border: 1px solid rgba(255,255,255,0.18);
                    border-radius: 22px;
                    padding: 22px;
                    text-align: center;
                    backdrop-filter: blur(12px);
                }}
                .score-ring {{
                    width: 148px;
                    height: 148px;
                    border-radius: 50%;
                    margin: 0 auto 16px;
                    border: 10px solid rgba(255,255,255,0.22);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    background: radial-gradient(circle, rgba(255,255,255,0.12), rgba(255,255,255,0.03));
                }}
                .score-number {{
                    font-size: 54px;
                    font-weight: 700;
                }}
                .score-band {{
                    font-size: 18px;
                    font-weight: 700;
                    margin-bottom: 4px;
                }}
                .score-caption {{
                    font-size: 13px;
                    opacity: 0.82;
                }}
                .grid {{
                    display: grid;
                    gap: 22px;
                }}
                .overview-grid {{
                    grid-template-columns: repeat(4, 1fr);
                    margin-bottom: 24px;
                }}
                .card {{
                    background: rgba(255,255,255,0.78);
                    backdrop-filter: blur(10px);
                    border: 1px solid rgba(148, 163, 184, 0.22);
                    border-radius: 20px;
                    box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
                }}
                .stat-card {{
                    padding: 24px;
                }}
                .stat-label {{
                    color: #5b6475;
                    font-size: 13px;
                    text-transform: uppercase;
                    letter-spacing: 0.08em;
                }}
                .stat-value {{
                    margin-top: 10px;
                    font-size: 36px;
                    font-weight: 700;
                }}
                .section {{
                    padding: 28px;
                    margin-bottom: 24px;
                }}
                .section h2 {{
                    margin: 0 0 16px;
                    font-size: 28px;
                    line-height: 1.2;
                }}
                .subdued {{
                    color: #5b6475;
                    line-height: 1.7;
                    font-size: 15px;
                }}
                .two-col {{
                    display: grid;
                    grid-template-columns: 1.15fr 0.85fr;
                    gap: 22px;
                }}
                .callout {{
                    border-radius: 16px;
                    padding: 18px;
                    background: #eef4ff;
                    border: 1px solid #cfe0ff;
                    margin-top: 16px;
                }}
                .callout h3 {{
                    margin: 0 0 10px;
                    font-size: 18px;
                }}
                .bullet-list {{
                    margin: 0;
                    padding-left: 20px;
                    color: #253046;
                    line-height: 1.7;
                }}
                .category-grid {{
                    display: grid;
                    grid-template-columns: repeat(2, 1fr);
                    gap: 16px;
                }}
                .category-card {{
                    border: 1px solid #e2e8f0;
                    border-radius: 16px;
                    padding: 18px;
                    background: #fff;
                }}
                .category-top {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    gap: 16px;
                    margin-bottom: 14px;
                }}
                .category-label {{
                    font-size: 18px;
                    font-weight: 700;
                }}
                .category-band {{
                    font-size: 13px;
                    font-weight: 600;
                    margin-top: 4px;
                }}
                .category-score {{
                    width: 58px;
                    height: 58px;
                    border-radius: 50%;
                    border: 4px solid;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-weight: 700;
                    font-size: 18px;
                }}
                .progress-track {{
                    width: 100%;
                    height: 10px;
                    border-radius: 999px;
                    background: #edf2f7;
                    overflow: hidden;
                }}
                .progress-fill {{
                    height: 100%;
                    border-radius: 999px;
                }}
                .recommendation-grid {{
                    display: grid;
                    grid-template-columns: repeat(2, 1fr);
                    gap: 16px;
                }}
                .recommendation-card {{
                    background: #fff;
                    border: 1px solid #e2e8f0;
                    border-radius: 18px;
                    padding: 18px;
                }}
                .recommendation-meta {{
                    display: flex;
                    flex-wrap: wrap;
                    gap: 8px;
                    align-items: center;
                    margin-bottom: 12px;
                }}
                .priority-pill, .area-pill, .item-number {{
                    display: inline-flex;
                    align-items: center;
                    padding: 5px 10px;
                    border-radius: 999px;
                    font-size: 12px;
                    font-weight: 700;
                    border: 1px solid transparent;
                }}
                .area-pill {{
                    background: #f1f5f9;
                    color: #334155;
                }}
                .item-number {{
                    background: #eff6ff;
                    color: #1d4ed8;
                }}
                .recommendation-card h3 {{
                    margin: 0 0 10px;
                    font-size: 18px;
                }}
                .recommendation-card p {{
                    margin: 0;
                    color: #4b5563;
                    line-height: 1.65;
                }}
                .metric-layout {{
                    display: grid;
                    grid-template-columns: repeat(3, 1fr);
                    gap: 16px;
                }}
                .metric-section {{
                    background: #fff;
                    border: 1px solid #e2e8f0;
                    border-radius: 16px;
                    padding: 18px;
                }}
                .metric-section h3 {{
                    margin: 0 0 14px;
                    font-size: 18px;
                }}
                .metric-row {{
                    display: flex;
                    justify-content: space-between;
                    gap: 12px;
                    padding: 10px 0;
                    border-bottom: 1px solid #edf2f7;
                    font-size: 14px;
                }}
                .metric-row:last-child {{
                    border-bottom: none;
                }}
                .footer {{
                    text-align: center;
                    color: #64748b;
                    font-size: 13px;
                    padding: 8px 0 18px;
                }}
                @media (max-width: 980px) {{
                    .hero-grid, .overview-grid, .two-col, .category-grid, .recommendation-grid, .metric-layout {{
                        grid-template-columns: 1fr;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <section class="hero">
                    <div class="hero-grid">
                        <div>
                            <div class="eyebrow">SEO Audit Report</div>
                            <h1>Detailed SEO findings for your page</h1>
                            <p>
                                This report summarizes the current search visibility health of the audited page,
                                highlights the biggest issues affecting performance, and gives you a practical order
                                of operations for fixing them.
                            </p>
                            <div class="audit-url">{_safe_text(final_url)}</div>
                            <div class="audit-url">Generated on {_safe_text(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))}</div>
                        </div>
                        <aside class="score-panel">
                            <div class="score-ring">
                                <div class="score-number" style="color:{score_color};">{overall_score}</div>
                            </div>
                            <div class="score-band" style="color:{score_color};">{_safe_text(score_label)}</div>
                            <div class="score-caption">Overall SEO score based on the analysis data available for this page.</div>
                        </aside>
                    </div>
                </section>

                <section class="grid overview-grid">
                    <div class="card stat-card">
                        <div class="stat-label">High Priority Issues</div>
                        <div class="stat-value" style="color:#dc2626;">{len(high_items)}</div>
                    </div>
                    <div class="card stat-card">
                        <div class="stat-label">Medium Priority Issues</div>
                        <div class="stat-value" style="color:#d97706;">{len(medium_items)}</div>
                    </div>
                    <div class="card stat-card">
                        <div class="stat-label">Low Priority Issues</div>
                        <div class="stat-value" style="color:#16a34a;">{len(low_items)}</div>
                    </div>
                    <div class="card stat-card">
                        <div class="stat-label">Total Recommendations</div>
                        <div class="stat-value" style="color:#1d4ed8;">{len(recommendations)}</div>
                    </div>
                </section>

                <section class="card section">
                    <h2>Executive Summary</h2>
                    <div class="two-col">
                        <div>
                            <p class="subdued">
                                The page currently scores <strong>{overall_score}/100</strong>, which places it in the
                                <strong>{_safe_text(score_label)}</strong> band. The biggest opportunity is to address
                                the highest-impact issues first, especially anything affecting crawlability, core metadata,
                                content structure, and image accessibility.
                            </p>
                            <div class="callout">
                                <h3>What is going well</h3>
                                <ul class="bullet-list">
                                    {''.join(f"<li>{_safe_text(item)}</li>" for item in strengths)}
                                </ul>
                            </div>
                        </div>
                        <div>
                            <div class="callout" style="background:#fff7ed;border-color:#fed7aa;">
                                <h3>What needs attention first</h3>
                                <ul class="bullet-list">
                                    {''.join(f"<li>{_safe_text(item)}</li>" for item in watchlist)}
                                </ul>
                            </div>
                            <div class="callout" style="background:#f0fdf4;border-color:#bbf7d0;">
                                <h3>Recommended next steps</h3>
                                <ul class="bullet-list">
                                    {''.join(next_steps)}
                                </ul>
                            </div>
                        </div>
                    </div>
                </section>

                <section class="card section">
                    <h2>Score Breakdown</h2>
                    <p class="subdued">
                        These category scores show where the page is strongest and where deeper optimization work is likely to have the biggest SEO impact.
                    </p>
                    <div class="category-grid">
                        {''.join(category_cards) if category_cards else '<p class="subdued">No category breakdown was included in the analysis response.</p>'}
                    </div>
                </section>

                <section class="card section">
                    <h2>Recommendations and Issues</h2>
                    <p class="subdued">
                        Each recommendation below includes the issue detected, its urgency, and the action that should be taken.
                    </p>
                    <div class="recommendation-grid">
                        {''.join(recommendation_cards) if recommendation_cards else '<p class="subdued">No issues were included in this analysis.</p>'}
                    </div>
                </section>

                <section class="card section">
                    <h2>Detailed Metrics</h2>
                    <p class="subdued">
                        These measurements give users more context behind the score, including content depth, heading structure, link balance, and technical indicators.
                    </p>
                    <div class="metric-layout">
                        {''.join(metric_sections) if metric_sections else '<p class="subdued">Detailed metric sections were not available in the analysis payload.</p>'}
                    </div>
                </section>

                <div class="footer">
                    Generated by FYP Marketing SEO Analyzer
                </div>
            </div>
        </body>
        </html>
        """

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html_content)

        return filepath

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to generate HTML report: {e}")
        raise
