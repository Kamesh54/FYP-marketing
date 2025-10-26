"""
SEO Analysis Agent - Enhanced Version

Usage:
    pip install -r requirements.txt
    python seo_agent.py https://example.com

Generates: report_<hostname>.html

Notes:
- The script is designed to be runnable locally. It performs a single-page crawl and analysis.
- Optional features (DNS checks for SPF/DMARC, backlink checks) rely on external services/APIs and are stubbed or implemented with heuristics.

Requirements (put in requirements.txt):
requests
beautifulsoup4
tldextract
python-dateutil

Optional (recommended):
dnspython

"""

import sys
import os
import re
import time
import json
import socket
import ssl
from urllib.parse import urljoin, urlparse
from collections import Counter, defaultdict

import requests
from bs4 import BeautifulSoup
import tldextract
from dateutil import parser as dateparser

# Optional dependency
try:
    import dns.resolver
    DNS_AVAILABLE = True
except Exception:
    DNS_AVAILABLE = False

# -----------------------------
# Configuration / Weights
# -----------------------------
WEIGHTS = {
    'onpage': 0.25,
    'links': 0.15,
    'performance': 0.20,
    'usability': 0.15,
    'social': 0.10,
    'local': 0.05,
    'technical': 0.10,
}

# Utility helpers

def safe_get(url, timeout=15, allow_redirects=True):
    headers = {
        'User-Agent': 'SEO-Agent/1.0 (+https://github.com/)'  # polite UA
    }
    try:
        t0 = time.time()
        r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=allow_redirects)
        elapsed = time.time() - t0
        return r, elapsed
    except Exception as e:
        return None, None


def fetch_head(url, timeout=10):
    headers = {'User-Agent': 'SEO-Agent/1.0'}
    try:
        r = requests.head(url, headers=headers, timeout=timeout, allow_redirects=True)
        return r
    except Exception:
        return None

# -----------------------------
# Crawling + parsing
# -----------------------------

def crawl_page(url):
    """Fetches a page and returns parsed soup and raw response info."""
    r, elapsed = safe_get(url)
    if r is None:
        raise RuntimeError(f"Failed to fetch {url}")

    soup = BeautifulSoup(r.content, 'lxml')
    parsed = urlparse(r.url)

    data = {
        'final_url': r.url,
        'status_code': r.status_code,
        'elapsed': elapsed,
        'content_length': len(r.content),
        'soup': soup,
        'response': r,
    }
    return data

# -----------------------------
# Analysis functions
# -----------------------------

def analyze_onpage(soup):
    issues = []
    score_components = {}

    # Title
    title_tag = soup.find('title')
    title = title_tag.get_text().strip() if title_tag else ''
    title_len = len(title)
    score_components['title_len'] = 1 if 50 <= title_len <= 60 else max(0, 1 - abs(55 - title_len) / 55)
    if not title:
        issues.append(('title_missing', 'No page title found'))
    else:
        if title_len < 50:
            issues.append(('title_short', f'Page title is too short ({title_len} characters). Recommended: 50-60 characters.'))
        if title_len > 60:
            issues.append(('title_long', f'Page title is too long ({title_len} characters). Recommended: 50-60 characters.'))

    # Meta description
    md = soup.find('meta', attrs={'name': lambda v: v and v.lower() == 'description'})
    desc = md['content'].strip() if md and md.has_attr('content') else ''
    desc_len = len(desc)
    score_components['meta_len'] = 1 if 120 <= desc_len <= 160 else max(0, 1 - abs(140 - desc_len) / 140)
    if not desc:
        issues.append(('meta_missing', 'Meta description is missing'))
    else:
        if desc_len < 120:
            issues.append(('meta_short', f'Meta description is too short ({desc_len} characters). Recommended: 120-160 characters.'))
        if desc_len > 160:
            issues.append(('meta_long', f'Meta description is too long ({desc_len} characters). Recommended: 120-160 characters.'))

    # H tags
    h1 = [h.get_text().strip() for h in soup.find_all(re.compile('^h[1-6]$'))]
    score_components['h_tags'] = min(1, len(h1) / 2)  # want at least H1 and some H2s
    if not soup.find('h1'):
        issues.append(('h1_missing', 'Main heading (H1) tag is missing'))

    # Images alt
    imgs = soup.find_all('img')
    total_imgs = len(imgs)
    imgs_missing_alt = sum(1 for i in imgs if not i.has_attr('alt') or not i['alt'].strip())
    score_components['images_alt'] = 1 - (imgs_missing_alt / total_imgs) if total_imgs else 1
    if imgs_missing_alt:
        issues.append(('images_alt_missing', f'{imgs_missing_alt} out of {total_imgs} images are missing alt text'))

    # Canonical
    canonical = soup.find('link', rel='canonical')
    score_components['canonical'] = 1 if canonical and canonical.has_attr('href') else 0
    if not canonical:
        issues.append(('canonical_missing', 'Canonical URL tag is missing'))

    # Keyword distribution heuristic
    text = soup.get_text(separator=' ', strip=True)
    words = re.findall(r"[A-Za-z0-9'-]+", text.lower())
    word_count = len(words)
    counter = Counter(words)
    top = counter.most_common(50)
    score_components['content_amount'] = 1 if word_count >= 300 else word_count / 300

    onpage_score = (sum(score_components.values()) / max(1, len(score_components))) * 100
    return {
        'score': round(onpage_score, 2),
        'components': score_components,
        'issues': issues,
        'word_count': word_count,
        'top_words': top[:20],
        'title': title,
        'meta': desc,
    }


def analyze_links(soup, base_url):
    issues = []
    anchors = soup.find_all('a', href=True)
    internal = []
    external = []
    for a in anchors:
        href = a['href'].strip()
        if href.startswith('#'):
            continue
        full = urljoin(base_url, href)
        p = urlparse(full)
        if p.netloc == urlparse(base_url).netloc:
            internal.append(full)
        else:
            external.append(full)

    total_links = len(internal) + len(external)
    follow = sum(1 for a in anchors if not (a.has_attr('rel') and 'nofollow' in a['rel']))

    # Basic backlink heuristic: number of external links linking to us is unknown here; we leave backlink check as optional/stub.
    components = {
        'total_links': total_links,
        'internal': len(internal),
        'external': len(external),
        'follow_rate': follow / max(1, total_links),
    }

    # Friendly URLs check
    unfriendly = []
    for u in internal + external:
        path = urlparse(u).path
        if re.search(r"[?=&%]{1}", path):
            unfriendly.append(u)
    if unfriendly:
        issues.append(('unfriendly_urls', f'{len(unfriendly)} links have unfriendly URLs with query parameters'))

    # Nofollow ratio
    nofollow = sum(1 for a in anchors if a.has_attr('rel') and 'nofollow' in a['rel'])
    components['nofollow'] = nofollow

    # Score: prefer internal linking and not leaking too many externals
    score = 100
    if components['external'] / max(1, total_links) > 0.4:
        score -= 20
    if components['internal'] < 3:
        score -= 20
    if nofollow == 0:
        score -= 5  # small penalty for none

    score = max(0, score)
    return {
        'score': round(score, 2),
        'components': components,
        'issues': issues,
        'internal_links_sample': internal[:20],
        'external_links_sample': external[:20],
    }


def analyze_performance(data, soup):
    # data contains response, elapsed, content_length
    issues = []
    r = data['response']
    elapsed = data['elapsed'] or 0
    content_length = data['content_length']

    # Try to estimate image weight by inspecting img src HEAD requests (best effort)
    imgs = [img.get('src') for img in soup.find_all('img') if img.get('src')]
    img_sizes = []
    for src in imgs[:30]:  # limit to first 30 to avoid long runtime
        full = urljoin(data['final_url'], src)
        try:
            head = fetch_head(full)
            if head and head.status_code == 200:
                cl = head.headers.get('Content-Length')
                if cl and cl.isdigit():
                    img_sizes.append(int(cl))
                else:
                    # fall back to GET but small timeout
                    r2, _ = safe_get(full, timeout=6)
                    if r2 and r2.content:
                        img_sizes.append(len(r2.content))
        except Exception:
            pass

    total_img_bytes = sum(img_sizes)
    total_bytes = content_length if content_length else 0
    images_pct = (total_img_bytes / max(1, total_bytes)) if total_bytes else 0

    components = {}
    # Page size scoring
    components['page_size_mb'] = round(total_bytes / 1024 / 1024, 2)
    if components['page_size_mb'] <= 5:
        components['size_score'] = 1
    else:
        components['size_score'] = max(0, 1 - (components['page_size_mb'] - 5) / 20)
        issues.append(('page_too_large', f'Page size of {components["page_size_mb"]} MB is larger than recommended 5MB'))

    # Response time scoring (simple)
    components['ttfb'] = r.elapsed.total_seconds() if hasattr(r, 'elapsed') else elapsed
    components['time_score'] = 1 if components['ttfb'] <= 0.5 else max(0, 1 - (components['ttfb'] - 0.5) / 5)
    if components['ttfb'] > 3:
        issues.append(('slow_server', f'Server response time of {components["ttfb"]:.2f} seconds is slow'))

    # Compression heuristic
    comp = r.headers.get('Content-Encoding', '')
    components['compressed'] = bool(comp)

    # HTTP/2 check
    try:
        proto = r.raw.version
        # requests raw version: 11 for HTTP/1.1, maybe 2 for HTTP/2 depending on adapter; fallback
        # We'll inspect headers for ALPN (best-effort)
        server = r.raw._original_response.version if hasattr(r.raw, '_original_response') else None
    except Exception:
        server = None
    # We can't reliably detect HTTP/2 with requests; check negotiated protocol via tls: best-effort
    try:
        parsed = urlparse(data['final_url'])
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        if parsed.scheme == 'https':
            ctx = ssl.create_default_context()
            s = ctx.wrap_socket(socket.socket(), server_hostname=host)
            s.settimeout(2)
            s.connect((host, port))
            proto = s.selected_alpn_protocol() if hasattr(s, 'selected_alpn_protocol') else None
            s.close()
            components['http2'] = (proto == 'h2')
        else:
            components['http2'] = False
    except Exception:
        components['http2'] = False

    perf_score = (components['size_score'] * 0.5 + components['time_score'] * 0.4 + (1 if components['http2'] else 0) * 0.1) * 100
    return {
        'score': round(perf_score, 2),
        'components': components,
        'issues': issues,
        'images_total_bytes': total_img_bytes,
    }


def analyze_usability(soup, final_url):
    issues = []
    # Viewport
    meta_viewport = soup.find('meta', attrs={'name': lambda v: v and v.lower() == 'viewport'})
    if not meta_viewport:
        issues.append(('viewport_missing', 'Mobile viewport tag is missing'))

    # Plain text emails
    text = soup.get_text(' ')
    emails = re.findall(r'[\w\.-]+@[\w\.-]+', text)
    if emails:
        issues.append(('emails_plain', f'Found {len(emails)} unprotected email addresses'))

    # Favicon
    favicon = soup.find('link', rel=lambda v: v and 'icon' in v.lower())
    if not favicon:
        issues.append(('favicon_missing', 'Website favicon is missing'))

    # Tap target / font sizes - heuristics only
    components = {
        'viewport': bool(meta_viewport),
        'emails_plain': len(emails),
        'favicon': bool(favicon),
    }
    score = (components['viewport'] * 0.6 + (1 if components['emails_plain'] == 0 else 0) * 0.3 + components['favicon'] * 0.1) * 100
    return {'score': round(score, 2), 'components': components, 'issues': issues}


def analyze_social(soup):
    issues = []
    og = soup.find('meta', property=lambda v: v and v.lower().startswith('og:'))
    twitter = soup.find('meta', attrs={'name': lambda v: v and v.lower().startswith('twitter:')})
    links = [a.get('href') for a in soup.find_all('a', href=True)]
    social = {'facebook': False, 'x': False, 'instagram': False, 'linkedin': False, 'youtube': False}
    for l in links:
        if 'facebook.com' in l:
            social['facebook'] = True
        if 'twitter.com' in l or 'x.com' in l:
            social['x'] = True
        if 'instagram.com' in l:
            social['instagram'] = True
        if 'linkedin.com' in l:
            social['linkedin'] = True
        if 'youtube.com' in l:
            social['youtube'] = True

    components = {
        'og': bool(og),
        'twitter': bool(twitter),
        'profiles': sum(1 for v in social.values() if v),
    }
    if components['profiles'] == 0:
        issues.append(('no_social_profiles', 'No social media profiles are linked'))
    if not components['og']:
        issues.append(('og_missing', 'Social sharing tags (OpenGraph) are missing'))

    score = (components['og'] * 0.4 + components['twitter'] * 0.2 + min(1, components['profiles'] / 3) * 0.4) * 100
    return {'score': round(score, 2), 'components': components, 'issues': issues, 'social_profiles': social}


def analyze_local(soup):
    issues = []
    # Attempt to find address and phone
    text = soup.get_text(' ')
    phone_matches = re.findall(r'\+?\d[\d\s\-()]{6,}\d', text)
    address = None
    # Heuristic: look for elements with "address", "contact", "location"
    addr_candidates = soup.find_all(attrs={'class': re.compile('address|contact|location', re.I)})
    if addr_candidates:
        address = ' '.join(a.get_text(separator=' ', strip=True) for a in addr_candidates[:2])

    components = {
        'phone_found': bool(phone_matches),
        'address_found': bool(address),
    }
    if not components['address_found']:
        issues.append(('local_address_missing', 'Business address is not clearly displayed'))
    if not components['phone_found']:
        issues.append(('local_phone_missing', 'Contact phone number is not found'))

    score = (components['phone_found'] * 0.5 + components['address_found'] * 0.5) * 100
    return {'score': round(score, 2), 'components': components, 'issues': issues, 'address_text': address, 'phones': phone_matches}


def analyze_technical(final_url):
    issues = []
    parsed = urlparse(final_url)
    components = {}

    components['scheme'] = parsed.scheme
    # SSL
    if parsed.scheme == 'https':
        # basic SSL check via socket
        try:
            ctx = ssl.create_default_context()
            with ctx.wrap_socket(socket.socket(), server_hostname=parsed.hostname) as s:
                s.settimeout(3)
                s.connect((parsed.hostname, parsed.port or 443))
                cert = s.getpeercert()
                components['ssl_valid'] = True
                components['cert_subject'] = cert.get('subject', ())
                # expiry
                try:
                    not_after = cert.get('notAfter')
                    components['cert_expiry'] = not_after
                except Exception:
                    components['cert_expiry'] = None
        except Exception:
            components['ssl_valid'] = False
            issues.append(('ssl_invalid', 'SSL certificate appears to be invalid or connection failed'))
    else:
        issues.append(('no_https', 'Website is not using secure HTTPS connection'))
        components['ssl_valid'] = False

    # Robots.txt
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        r, _ = safe_get(robots_url)
        components['robots'] = True if r and r.status_code == 200 else False
        if r and 'Disallow:' in r.text and parsed.path in r.text:
            issues.append(('robots_blocks', 'robots.txt may be blocking this page from search engines'))
    except Exception:
        components['robots'] = False

    # Sitemap
    sitemap_url = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"
    r, _ = safe_get(sitemap_url)
    components['sitemap'] = True if r and r.status_code == 200 else False

    # DNS records for SPF/DMARC (optional)
    if DNS_AVAILABLE:
        try:
            dom = parsed.netloc
            answers = dns.resolver.resolve(dom, 'TXT')
            txts = [r.to_text() for r in answers]
            components['txt_records'] = txts
            components['spf'] = any('spf1' in t.lower() for t in txts)
            components['dmarc'] = False
            try:
                dmarc_answers = dns.resolver.resolve('_dmarc.' + dom, 'TXT')
                components['dmarc'] = True
            except Exception:
                components['dmarc'] = False
        except Exception:
            components['txt_records'] = []
            components['spf'] = False
            components['dmarc'] = False
    else:
        components['txt_records'] = []
        components['spf'] = None
        components['dmarc'] = None

    tech_score = 100
    if not components['ssl_valid']:
        tech_score -= 40
    if not components['robots']:
        tech_score -= 5
    if not components['sitemap']:
        tech_score -= 5

    return {'score': round(max(0, tech_score), 2), 'components': components, 'issues': issues}

# -----------------------------
# Recommendation engine
# -----------------------------

def generate_recommendations(analyses):
    """Generate human-readable recommendations and priority for each issue found."""
    recs = []

    # Onpage issues
    for code, msg in analyses['onpage']['issues']:
        priority = 'Medium'
        if code in ('title_missing', 'meta_missing', 'h1_missing'):
            priority = 'High'
        recs.append({'area': 'Content & Keywords', 'issue': msg, 'priority': priority, 'suggestion': suggestion_for_onpage(code)})

    # Links
    for code, msg in analyses['links']['issues']:
        recs.append({'area': 'Links & Structure', 'issue': msg, 'priority': 'Low', 'suggestion': suggestion_for_links(code)})

    # Performance
    for code, msg in analyses['performance']['issues']:
        pr = 'Medium' if code == 'page_too_large' else 'Low'
        recs.append({'area': 'Speed & Performance', 'issue': msg, 'priority': pr, 'suggestion': suggestion_for_performance(code)})

    # Usability
    for code, msg in analyses['usability']['issues']:
        recs.append({'area': 'User Experience', 'issue': msg, 'priority': 'Medium' if code == 'viewport_missing' else 'Low', 'suggestion': suggestion_for_usability(code)})

    # Social
    for code, msg in analyses['social']['issues']:
        recs.append({'area': 'Social Media', 'issue': msg, 'priority': 'Low', 'suggestion': suggestion_for_social(code)})

    # Local
    for code, msg in analyses['local']['issues']:
        recs.append({'area': 'Local Business', 'issue': msg, 'priority': 'Low', 'suggestion': suggestion_for_local(code)})

    # Technical
    for code, msg in analyses['technical']['issues']:
        pri = 'High' if code in ('ssl_invalid', 'no_https') else 'Medium'
        recs.append({'area': 'Technical Setup', 'issue': msg, 'priority': pri, 'suggestion': suggestion_for_technical(code)})

    # If Analytics not detected (simple heuristic: look for ga, gtag, analytics in scripts)
    scripts = ''.join([str(s) for s in analyses['raw_soup'].find_all('script')])
    if 'gtag(' not in scripts and 'ga(' not in scripts and 'analytics' not in scripts.lower():
        recs.append({'area': 'Analytics & Tracking', 'issue': 'Website analytics not detected', 'priority': 'Low', 'suggestion': 'Install Google Analytics or similar to monitor traffic and user behavior.'})

    # Sort recs by priority
    priority_order = {'High': 0, 'Medium': 1, 'Low': 2}
    recs.sort(key=lambda r: priority_order.get(r['priority'], 2))
    return recs


def suggestion_for_onpage(code):
    mapping = {
        'title_missing': 'Add a unique, descriptive page title. Keep it 50-60 characters and include your main keyword near the beginning.',
        'title_short': 'Expand your title to include a clear keyword and value proposition while staying under 60 characters.',
        'title_long': 'Shorten your title to under 60 characters. Put your brand name at the end if needed.',
        'meta_missing': 'Add a compelling meta description (120-160 characters) that summarizes your page and includes your target keyword.',
        'meta_short': 'Expand your meta description to around 150 characters, including the most important keywords and benefits.',
        'meta_long': 'Trim your meta description to around 150 characters. Keep the most important message in the first 120 characters.',
        'h1_missing': 'Add a clear main heading (H1) that contains your primary topic and keyword for the page.',
        'images_alt_missing': 'Add descriptive alt text to all images to improve accessibility and help search engines understand your content.',
        'canonical_missing': 'Add a canonical URL tag to prevent duplicate content issues and consolidate page authority.',
    }
    return mapping.get(code, 'Review this element and align it with SEO best practices.')


def suggestion_for_links(code):
    mapping = {
        'unfriendly_urls': 'Use clean, readable URLs that are short, use hyphens, and include keywords. Avoid long query strings when possible.',
    }
    return mapping.get(code, 'Improve your internal linking structure and ensure important pages receive internal links.')


def suggestion_for_performance(code):
    mapping = {
        'page_too_large': 'Optimize and compress images, enable browser caching, implement lazy loading, and remove unused large resources.',
        'slow_server': 'Investigate server performance issues. Consider using a CDN, improving caching, or upgrading to faster hosting.',
    }
    return mapping.get(code, 'Run a Google Lighthouse report to identify and fix the most impactful performance issues.')


def suggestion_for_usability(code):
    mapping = {
        'viewport_missing': 'Add a viewport meta tag to ensure your site displays properly on mobile devices.',
        'emails_plain': 'Replace plain email addresses with a contact form or use JavaScript obfuscation to reduce spam.',
        'favicon_missing': 'Add a favicon to improve your brand recognition in browser tabs and bookmarks.',
    }
    return mapping.get(code, 'Focus on improving mobile user experience and website accessibility.')


def suggestion_for_social(code):
    mapping = {
        'no_social_profiles': 'Create business profiles on relevant social media platforms and link to them from your website.',
        'og_missing': 'Add OpenGraph tags (og:title, og:description, og:image) to control how your page appears when shared on social media.',
    }
    return mapping.get(code, 'Implement social media meta tags and link to your official social media profiles.')


def suggestion_for_local(code):
    mapping = {
        'local_address_missing': 'Display your business address prominently and add structured data markup (LocalBusiness schema) for better local SEO.',
        'local_phone_missing': 'Include your business phone number or primary contact method clearly on the page.',
    }
    return mapping.get(code, 'Make sure your local business information is easily accessible and properly marked up.')


def suggestion_for_technical(code):
    mapping = {
        'ssl_invalid': 'Fix SSL certificate issues and ensure all pages redirect from HTTP to HTTPS for security and SEO benefits.',
        'no_https': 'Implement HTTPS for your entire website and set up 301 redirects from HTTP to HTTPS.',
        'robots_blocks': 'Review your robots.txt file to ensure you are not accidentally blocking important pages from search engines.',
    }
    return mapping.get(code, 'Ensure your website follows technical SEO best practices for optimal search engine crawling.')

def get_score_color(score):
    """Return color class based on score"""
    if score >= 80:
        return '#10B981', '#D1FAE5'  # Green
    elif score >= 60:
        return '#F59E0B', '#FEF3C7'  # Yellow
    elif score >= 40:
        return '#F97316', '#FED7AA'  # Orange
    else:
        return '#EF4444', '#FEE2E2'  # Red

def get_priority_color(priority):
    """Return color for priority badges"""
    colors = {
        'High': ('#DC2626', '#FEE2E2'),
        'Medium': ('#D97706', '#FEF3C7'),
        'Low': ('#059669', '#D1FAE5')
    }
    return colors.get(priority, ('#6B7280', '#F3F4F6'))

# -----------------------------
# HTML report generation
# -----------------------------

def render_html_report(analyses, url, output_path):
    hostname = tldextract.extract(url).registered_domain or urlparse(url).netloc
    title = f"SEO Analysis Report - {hostname}"
    now = time.strftime('%B %d, %Y at %H:%M UTC', time.gmtime())

    overall_score = 0
    # Weighted composite
    overall_score = (
        analyses['onpage']['score'] * WEIGHTS['onpage'] +
        analyses['links']['score'] * WEIGHTS['links'] +
        analyses['performance']['score'] * WEIGHTS['performance'] +
        analyses['usability']['score'] * WEIGHTS['usability'] +
        analyses['social']['score'] * WEIGHTS['social'] +
        analyses['local']['score'] * WEIGHTS['local'] +
        analyses['technical']['score'] * WEIGHTS['technical']
    )
    overall_score = round(overall_score, 2)

    # Generate recommendations HTML
    recommendations_by_priority = {'High': [], 'Medium': [], 'Low': []}
    for r in analyses['recommendations']:
        recommendations_by_priority[r['priority']].append(r)

    recs_html = ''
    for priority in ['High', 'Medium', 'Low']:
        if recommendations_by_priority[priority]:
            color, bg_color = get_priority_color(priority)
            recs_html += f'''
            <div class="priority-section">
                <h3 class="priority-title">
                    <span class="priority-badge" style="background-color: {bg_color}; color: {color};">
                        {priority} Priority
                    </span>
                    <span class="priority-count">({len(recommendations_by_priority[priority])} items)</span>
                </h3>
                <div class="recommendations-grid">
            '''
            for r in recommendations_by_priority[priority]:
                recs_html += f'''
                <div class="recommendation-card">
                    <div class="recommendation-header">
                        <span class="area-tag">{r['area']}</span>
                    </div>
                    <h4 class="issue-title">{r['issue']}</h4>
                    <p class="suggestion">{r['suggestion']}</p>
                </div>
                '''
            recs_html += '</div></div>'

    # Generate category scores HTML
    categories = [
        ('Content & Keywords', 'onpage', 'Content optimization, titles, descriptions, and keyword usage'),
        ('Speed & Performance', 'performance', 'Page load speed, file sizes, and technical performance'),
        ('User Experience', 'usability', 'Mobile-friendliness, accessibility, and user interface'),
        ('Links & Structure', 'links', 'Internal linking, external links, and site structure'),
        ('Technical Setup', 'technical', 'HTTPS, robots.txt, sitemaps, and technical configuration'),
        ('Social Media', 'social', 'Social media integration and sharing optimization'),
        ('Local Business', 'local', 'Local business information and local SEO factors'),
    ]

    category_cards = ''
    for name, key, description in categories:
        score = analyses[key]['score']
        color, bg_color = get_score_color(score)
        category_cards += f'''
        <div class="category-card">
            <div class="category-header">
                <h3 class="category-name">{name}</h3>
                <div class="score-circle" style="border-color: {color}; color: {color};">
                    {score}<span class="score-unit">/100</span>
                </div>
            </div>
            <p class="category-description">{description}</p>
            <div class="progress-bar">
                <div class="progress-fill" style="width: {score}%; background-color: {color};"></div>
            </div>
        </div>
        '''

    # Generate key metrics
    onpage = analyses['onpage']
    perf = analyses['performance']
    top_words_html = ', '.join([f"{w} ({c})" for w, c in onpage['top_words'][:10]])

    overall_color, overall_bg = get_score_color(overall_score)

    html = f'''<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
            line-height: 1.6;
            color: #1f2937;
            background: #f8fafc;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px 20px;
            border-radius: 16px;
            margin-bottom: 30px;
            text-align: center;
            box-shadow: 0 10px 25px rgba(0,0,0,0.1);
        }}
        
        .header h1 {{
            font-size: 2.5rem;
            font-weight: 700;
            margin-bottom: 10px;
        }}
        
        .header .url {{
            font-size: 1.1rem;
            opacity: 0.9;
            margin-bottom: 5px;
            word-break: break-all;
        }}
        
        .header .date {{
            font-size: 0.95rem;
            opacity: 0.8;
        }}
        
        .overall-score {{
            background: white;
            border-radius: 16px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05);
            text-align: center;
        }}
        
        .score-display {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 120px;
            height: 120px;
            border-radius: 50%;
            border: 8px solid {overall_color};
            margin-bottom: 20px;
        }}
        
        .score-number {{
            font-size: 2.5rem;
            font-weight: 700;
            color: {overall_color};
        }}
        
        .score-label {{
            font-size: 1.2rem;
            color: #6b7280;
            margin-bottom: 10px;
        }}
        
        .score-description {{
            color: #6b7280;
            max-width: 600px;
            margin: 0 auto;
        }}
        
        .categories-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }}
        
        .category-card {{
            background: white;
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        
        .category-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(0,0,0,0.1);
        }}
        
        .category-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }}
        
        .category-name {{
            font-size: 1.2rem;
            font-weight: 600;
            color: #1f2937;
        }}
        
        .score-circle {{
            display: flex;
            align-items: center;
            justify-content: center;
            width: 60px;
            height: 60px;
            border-radius: 50%;
            border: 3px solid;
            font-weight: 700;
            font-size: 0.9rem;
        }}
        
        .score-unit {{
            font-size: 0.6rem;
            opacity: 0.7;
        }}
        
        .category-description {{
            color: #6b7280;
            font-size: 0.9rem;
            margin-bottom: 15px;
        }}
        
        .progress-bar {{
            height: 8px;
            background: #e5e7eb;
            border-radius: 4px;
            overflow: hidden;
        }}
        
        .progress-fill {{
            height: 100%;
            border-radius: 4px;
            transition: width 0.3s ease;
        }}
        
        .section {{
            background: white;
            border-radius: 12px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }}
        
        .section h2 {{
            font-size: 1.8rem;
            font-weight: 700;
            color: #1f2937;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        
        .section-icon {{
            width: 32px;
            height: 32px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: bold;
        }}
        
        .priority-section {{
            margin-bottom: 30px;
        }}
        
        .priority-title {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 15px;
            font-size: 1.3rem;
            font-weight: 600;
        }}
        
        .priority-badge {{
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 0.9rem;
            font-weight: 600;
        }}
        
        .priority-count {{
            color: #6b7280;
            font-weight: 400;
            font-size: 1rem;
        }}
        
        .recommendations-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
        }}
        
        .recommendation-card {{
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 20px;
            background: #fefefe;
        }}
        
        .recommendation-header {{
            margin-bottom: 10px;
        }}
        
        .area-tag {{
            background: #f3f4f6;
            color: #374151;
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 500;
        }}
        
        .issue-title {{
            font-size: 1rem;
            font-weight: 600;
            color: #1f2937;
            margin-bottom: 8px;
        }}
        
        .suggestion {{
            color: #4b5563;
            font-size: 0.9rem;
            line-height: 1.5;
        }}
        
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }}
        
        .metric-card {{
            background: #f8fafc;
            border-radius: 8px;
            padding: 16px;
            text-align: center;
        }}
        
        .metric-value {{
            font-size: 1.5rem;
            font-weight: 700;
            color: #1f2937;
            margin-bottom: 5px;
        }}
        
        .metric-label {{
            color: #6b7280;
            font-size: 0.9rem;
        }}
        
        .details-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
        }}
        
        .detail-item {{
            border-left: 4px solid #667eea;
            padding-left: 15px;
            margin-bottom: 15px;
        }}
        
        .detail-item strong {{
            color: #1f2937;
            display: block;
            margin-bottom: 5px;
        }}
        
        .footer {{
            text-align: center;
            padding: 30px;
            color: #6b7280;
            font-size: 0.9rem;
            border-top: 1px solid #e5e7eb;
            margin-top: 40px;
        }}
        
        @media (max-width: 768px) {{
            .container {{
                padding: 10px;
            }}
            
            .header h1 {{
                font-size: 2rem;
            }}
            
            .categories-grid {{
                grid-template-columns: 1fr;
            }}
            
            .recommendations-grid {{
                grid-template-columns: 1fr;
            }}
            
            .metrics-grid {{
                grid-template-columns: repeat(2, 1fr);
            }}
        }}
        
        .no-issues {{
            text-align: center;
            color: #10b981;
            font-weight: 500;
            padding: 20px;
            background: #d1fae5;
            border-radius: 8px;
            margin: 20px 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header class="header">
            <h1>SEO Analysis Report</h1>
            <div class="url">{url}</div>
            <div class="date">Generated on {now}</div>
        </header>

        <div class="overall-score">
            <div class="score-display">
                <span class="score-number">{overall_score}</span>
            </div>
            <div class="score-label">Overall SEO Score</div>
            <div class="score-description">
                This score represents a comprehensive analysis of your website's search engine optimization across multiple key factors.
            </div>
        </div>

        <div class="categories-grid">
            {category_cards}
        </div>

        <div class="section">
            <h2>
                <span class="section-icon">!</span>
                Priority Recommendations
            </h2>
            {recs_html if recs_html else '<div class="no-issues">🎉 Great news! No major SEO issues were found. Your website is well-optimized!</div>'}
        </div>

        <div class="section">
            <h2>
                <span class="section-icon">📊</span>
                Key Metrics Overview
            </h2>
            <div class="metrics-grid">
                <div class="metric-card">
                    <div class="metric-value">{onpage['word_count']:,}</div>
                    <div class="metric-label">Words on Page</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{len(onpage['title'])}</div>
                    <div class="metric-label">Title Length</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{len(onpage['meta'])}</div>
                    <div class="metric-label">Meta Description Length</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{perf['components']['page_size_mb']} MB</div>
                    <div class="metric-label">Page Size</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{perf['components']['ttfb']:.2f}s</div>
                    <div class="metric-label">Server Response Time</div>
                </div>
                <div class="metric-card">
                    <div class="metric-value">{analyses['links']['components']['total_links']}</div>
                    <div class="metric-label">Total Links Found</div>
                </div>
            </div>
        </div>

        <div class="details-grid">
            <div class="section">
                <h2>
                    <span class="section-icon">📝</span>
                    Content Details
                </h2>
                <div class="detail-item">
                    <strong>Page Title:</strong>
                    {onpage['title'][:100]}{'...' if len(onpage['title']) > 100 else ''}
                </div>
                <div class="detail-item">
                    <strong>Meta Description:</strong>
                    {onpage['meta'][:150]}{'...' if len(onpage['meta']) > 150 else ''}
                </div>
                <div class="detail-item">
                    <strong>Most Common Words:</strong>
                    {top_words_html}
                </div>
            </div>

            <div class="section">
                <h2>
                    <span class="section-icon">🔗</span>
                    Link Analysis
                </h2>
                <div class="detail-item">
                    <strong>Internal Links:</strong>
                    {analyses['links']['components']['internal']} found
                </div>
                <div class="detail-item">
                    <strong>External Links:</strong>
                    {analyses['links']['components']['external']} found
                </div>
                <div class="detail-item">
                    <strong>NoFollow Links:</strong>
                    {analyses['links']['components']['nofollow']} found
                </div>
            </div>

            <div class="section">
                <h2>
                    <span class="section-icon">🛡️</span>
                    Technical Status
                </h2>
                <div class="detail-item">
                    <strong>HTTPS/SSL:</strong>
                    {'✅ Secure' if analyses['technical']['components']['ssl_valid'] else '❌ Not Secure'}
                </div>
                <div class="detail-item">
                    <strong>Robots.txt:</strong>
                    {'✅ Found' if analyses['technical']['components']['robots'] else '❌ Missing'}
                </div>
                <div class="detail-item">
                    <strong>Sitemap:</strong>
                    {'✅ Found' if analyses['technical']['components']['sitemap'] else '❌ Missing'}
                </div>
                <div class="detail-item">
                    <strong>HTTP/2 Support:</strong>
                    {'✅ Enabled' if analyses['performance']['components']['http2'] else '❌ Not Detected'}
                </div>
            </div>

            <div class="section">
                <h2>
                    <span class="section-icon">📱</span>
                    Social & Local
                </h2>
                <div class="detail-item">
                    <strong>OpenGraph Tags:</strong>
                    {'✅ Present' if analyses['social']['components']['og'] else '❌ Missing'}
                </div>
                <div class="detail-item">
                    <strong>Twitter Cards:</strong>
                    {'✅ Present' if analyses['social']['components']['twitter'] else '❌ Missing'}
                </div>
                <div class="detail-item">
                    <strong>Social Profiles Linked:</strong>
                    {analyses['social']['components']['profiles']} found
                </div>
                <div class="detail-item">
                    <strong>Business Contact Info:</strong>
                    {'✅ Phone & Address Found' if analyses['local']['components']['phone_found'] and analyses['local']['components']['address_found'] else '⚠️ Incomplete'}
                </div>
            </div>
        </div>

        <div class="footer">
            <p><strong>SEO Analysis Tool</strong> • This report provides insights to improve your search engine optimization.</p>
            <p>For more detailed analysis, consider integrating with Google Search Console, PageSpeed Insights, and professional SEO tools.</p>
        </div>
    </div>
</body>
</html>'''

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    return output_path

# -----------------------------
# Main orchestration
# -----------------------------

def run_audit(target_url):
    print(f" Starting SEO audit for {target_url}")
    data = crawl_page(target_url)
    soup = data['soup']

    print(" Analyzing on-page SEO...")
    onpage = analyze_onpage(soup)
    
    print(" Analyzing links and structure...")
    links = analyze_links(soup, data['final_url'])
    
    print(" Analyzing performance...")
    performance = analyze_performance(data, soup)
    
    print(" Analyzing usability...")
    usability = analyze_usability(soup, data['final_url'])
    
    print(" Analyzing social media integration...")
    social = analyze_social(soup)
    
    print("Analyzing local SEO factors...")
    local = analyze_local(soup)
    
    print("Analyzing technical setup...")
    technical = analyze_technical(data['final_url'])

    analyses = {
        'onpage': onpage,
        'links': links,
        'performance': performance,
        'usability': usability,
        'social': social,
        'local': local,
        'technical': technical,
        'raw_soup': soup,
    }

    print(" Generating recommendations...")
    analyses['recommendations'] = generate_recommendations(analyses)

    # render output
    parsed = urlparse(data['final_url'])
    host = parsed.netloc.replace(':', '_')
    out = f"report_{host}.html"
    path = render_html_report(analyses, data['final_url'], out)
    print(f" Beautiful SEO report generated: {path}")
    print(f" Open the report in your browser to view the results!")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python seo_agent.py <url>")
        print("Example: python seo_agent.py https://example.com")
        sys.exit(1)
    url = sys.argv[1]
    run_audit(url)