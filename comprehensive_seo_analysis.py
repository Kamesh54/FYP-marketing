"""
Comprehensive SEO Analysis - Detailed version for /seo page
Provides thorough analysis with all metrics, best practices, and actionable recommendations
Takes 20-30 seconds but gives complete insights
"""
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
from datetime import datetime
import logging
import time

logger = logging.getLogger(__name__)

# Real browser User-Agents
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
]

def fetch_page(url: str, timeout: int = 15) -> dict:
    """Fetch page with details"""
    try:
        headers = {'User-Agent': USER_AGENTS[0]}
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        return {
            'success': True,
            'url': url,
            'final_url': response.url,
            'status_code': response.status_code,
            'soup': soup,
            'content_length': len(response.content),
        }
    except Exception as e:
        logger.error(f"Error fetching {url}: {e}")
        return {'success': False, 'url': url, 'error': str(e)}

def analyze_seo_comprehensive(soup: BeautifulSoup, url: str) -> dict:
    """Comprehensive SEO analysis covering all factors"""
    issues = []
    score = 1.0
    details = {}
    
    # ═════════════════════════════════════════════════════════════
    # 1. TITLE TAG ANALYSIS
    # ═════════════════════════════════════════════════════════════
    title = soup.find('title')
    title_text = title.string.strip() if title and title.string else ""
    details['title'] = {
        'present': bool(title_text),
        'text': title_text,
        'length': len(title_text),
    }
    
    if not title_text:
        issues.append({
            'area': 'On-Page SEO',
            'issue': 'Missing page title tag',
            'priority': 'High',
            'suggestion': 'Add a unique, descriptive title (50-60 characters). For example: "Premium Water Bottles - Hydration Solutions | YourBrand"'
        })
        score -= 0.15
    elif len(title_text) < 30:
        issues.append({
            'area': 'On-Page SEO',
            'issue': f'Title too short ({len(title_text)} chars)',
            'priority': 'High',
            'suggestion': 'Expand your title to 50-60 characters. Include your main keyword and brand name for better SEO.'
        })
        score -= 0.10
    elif len(title_text) > 65:
        issues.append({
            'area': 'On-Page SEO',
            'issue': f'Title too long ({len(title_text)} chars)',
            'priority': 'Medium',
            'suggestion': 'Shorten your title to 50-60 characters to ensure it displays fully in search results.'
        })
        score -= 0.05
    
    # ═════════════════════════════════════════════════════════════
    # 2. META DESCRIPTION ANALYSIS
    # ═════════════════════════════════════════════════════════════
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    desc_text = meta_desc.get('content', '').strip() if meta_desc else ""
    details['meta_description'] = {
        'present': bool(desc_text),
        'text': desc_text[:100] + '...' if len(desc_text) > 100 else desc_text,
        'length': len(desc_text),
    }
    
    if not desc_text:
        issues.append({
            'area': 'On-Page SEO',
            'issue': 'Missing meta description tag',
            'priority': 'High',
            'suggestion': 'Add a compelling meta description (120-160 characters). Example: "Discover our premium water bottles designed for active lifestyles. Free shipping on orders over $50. Shop now!"'
        })
        score -= 0.15
    elif len(desc_text) < 120:
        issues.append({
            'area': 'On-Page SEO',
            'issue': f'Meta description too short ({len(desc_text)} chars)',
            'priority': 'Medium',
            'suggestion': 'Expand to 120-160 characters to fully capture the snippet in search results.'
        })
        score -= 0.08
    elif len(desc_text) > 160:
        issues.append({
            'area': 'On-Page SEO',
            'issue': f'Meta description too long ({len(desc_text)} chars)',
            'priority': 'Medium',
            'suggestion': 'Shorten to 120-160 characters to avoid truncation in search results.'
        })
        score -= 0.05
    
    # ═════════════════════════════════════════════════════════════
    # 3. HEADING HIERARCHY ANALYSIS
    # ═════════════════════════════════════════════════════════════
    h1_tags = soup.find_all('h1')
    h2_tags = soup.find_all('h2')
    h3_tags = soup.find_all('h3')
    h_all = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
    
    details['headings'] = {
        'h1_count': len(h1_tags),
        'h2_count': len(h2_tags),
        'h3_count': len(h3_tags),
        'total': len(h_all),
    }
    
    if len(h1_tags) == 0:
        issues.append({
            'area': 'Content & Keywords',
            'issue': 'Missing H1 heading (main heading)',
            'priority': 'High',
            'suggestion': 'Add one H1 tag containing your primary keyword. This helps search engines understand your page topic. Example: <h1>Premium Water Bottles for Athletes</h1>'
        })
        score -= 0.12
    elif len(h1_tags) > 1:
        issues.append({
            'area': 'Content & Keywords',
            'issue': f'Multiple H1 tags found ({len(h1_tags)})',
            'priority': 'High',
            'suggestion': 'Use only ONE H1 tag per page. Search engines use H1 to understand main topic. Use H2 for subtopics instead.'
        })
        score -= 0.10
    
    if len(h2_tags) == 0 and len(h1_tags) > 0:
        issues.append({
            'area': 'Content & Keywords',
            'issue': 'No H2 subheadings found',
            'priority': 'Medium',
            'suggestion': 'Add H2 tags to organize content into logical sections. This improves readability and SEO.'
        })
        score -= 0.06
    
    # ═════════════════════════════════════════════════════════════
    # 4. META TAGS & TECHNICAL ANALYSIS
    # ═════════════════════════════════════════════════════════════
    
    # Viewport tag
    viewport = soup.find('meta', attrs={'name': 'viewport'})
    if not viewport:
        issues.append({
            'area': 'Mobile & Technical',
            'issue': 'Missing viewport meta tag',
            'priority': 'High',
            'suggestion': 'Add <meta name="viewport" content="width=device-width, initial-scale=1.0"> to your <head> for mobile responsiveness.'
        })
        score -= 0.10
    else:
        details['mobile_responsive'] = True
    
    # Canonical tag
    canonical = soup.find('link', attrs={'rel': 'canonical'})
    if not canonical:
        issues.append({
            'area': 'Technical SEO',
            'issue': 'Missing canonical URL tag',
            'priority': 'Medium',
            'suggestion': 'Add <link rel="canonical" href="https://yoursite.com/page"> to prevent duplicate content penalties.'
        })
        score -= 0.08
    else:
        details['canonical'] = canonical.get('href')
    
    # Language attribute
    html_tag = soup.find('html')
    lang = html_tag.get('lang') if html_tag else None
    if not lang:
        issues.append({
            'area': 'International SEO',
            'issue': 'Missing language attribute on HTML tag',
            'priority': 'Low',
            'suggestion': 'Add lang attribute to <html> tag. Example: <html lang="en">. This helps search engines understand your content language.'
        })
        score -= 0.02
    
    # ═════════════════════════════════════════════════════════════
    # 5. IMAGE ANALYSIS
    # ═════════════════════════════════════════════════════════════
    images = soup.find_all('img')
    images_without_alt = [img for img in images if not img.get('alt') or img.get('alt').strip() == '']
    
    details['images'] = {
        'total': len(images),
        'without_alt': len(images_without_alt),
        'alt_coverage': f"{round((len(images) - len(images_without_alt)) / len(images) * 100)}%" if images else "0%"
    }
    
    if images_without_alt:
        percentage = round(len(images_without_alt) / len(images) * 100)
        issues.append({
            'area': 'Accessibility & Images',
            'issue': f'{len(images_without_alt)} of {len(images)} images missing alt text ({percentage}%)',
            'priority': 'High',
            'suggestion': f'Add descriptive alt text to all images. Alt text helps search engines understand images and improves accessibility. Example: alt="Water bottle with measurement markings"'
        })
        score -= 0.12
    
    # ═════════════════════════════════════════════════════════════
    # 6. LINKS ANALYSIS
    # ═════════════════════════════════════════════════════════════
    all_links = soup.find_all('a', href=True)
    parsed_url = urlparse(url)
    base_domain = parsed_url.netloc
    
    internal_links = []
    external_links = []
    broken_anchors = []
    
    for a in all_links:
        href = a.get('href', '')
        if not href or href.startswith('#'):
            broken_anchors.append(a)
        else:
            link_domain = urlparse(href).netloc
            if not link_domain or link_domain == base_domain or link_domain == base_domain.replace('www.', ''):
                internal_links.append(href)
            else:
                external_links.append(href)
    
    details['links'] = {
        'total': len(all_links),
        'internal': len(internal_links),
        'external': len(external_links),
        'anchor_only': len(broken_anchors),
    }
    
    if len(internal_links) < 3:
        issues.append({
            'area': 'Internal Linking',
            'issue': f'Very few internal links ({len(internal_links)})',
            'priority': 'Medium',
            'suggestion': f'Add more internal links to improve site structure and SEO. Link to important pages like: product categories, about page, blog posts.'
        })
        score -= 0.08
    
    # ═════════════════════════════════════════════════════════════
    # 7. HTTPS & SECURITY
    # ═════════════════════════════════════════════════════════════
    if parsed_url.scheme != 'https':
        issues.append({
            'area': 'Security & Trust',
            'issue': 'Not using HTTPS (SSL certificate)',
            'priority': 'High',
            'suggestion': 'Migrate to HTTPS immediately. Google ranks HTTPS sites higher. It also shows a security badge to visitors.'
        })
        score -= 0.15
    else:
        details['https'] = True
    
    # ═════════════════════════════════════════════════════════════
    # 8. STRUCTURED DATA (Schema.org)
    # ═════════════════════════════════════════════════════════════
    schema_tags = soup.find_all('script', attrs={'type': 'application/ld+json'})
    if not schema_tags:
        issues.append({
            'area': 'Structured Data',
            'issue': 'No structured data (Schema.org) found',
            'priority': 'Low',
            'suggestion': 'Add JSON-LD structured data for rich snippets. E.g., Product, Organization, Article schema. This can improve CTR in search results.'
        })
        score -= 0.05
    
    # ═════════════════════════════════════════════════════════════
    # 9. ROBOTS & META TAGS
    # ═════════════════════════════════════════════════════════════
    robots = soup.find('meta', attrs={'name': 'robots'})
    
    # OG Tags
    og_tags = soup.find_all('meta', attrs={'property': lambda x: x and x.startswith('og:')})
    twitter_tags = soup.find_all('meta', attrs={'name': lambda x: x and x.startswith('twitter:')})
    
    details['social_meta'] = {
        'og_tags': len(og_tags),
        'twitter_tags': len(twitter_tags),
    }
    
    if not og_tags:
        issues.append({
            'area': 'Social Media',
            'issue': 'Missing Open Graph (OG) tags',
            'priority': 'Low',
            'suggestion': 'Add OG tags for better social media sharing. Example: og:title, og:description, og:image'
        })
        score -= 0.03
    
    # ═════════════════════════════════════════════════════════════
    # 10. CONTENT ANALYSIS
    # ═════════════════════════════════════════════════════════════
    text = soup.get_text()
    word_count = len(text.split())
    paragraphs = len(soup.find_all('p'))
    
    details['content'] = {
        'word_count': word_count,
        'paragraph_count': paragraphs,
    }
    
    if word_count < 300:
        issues.append({
            'area': 'Content Quality',
            'issue': f'Content too short ({word_count} words)',
            'priority': 'Medium',
            'suggestion': 'Expand content to at least 300-500 words. Longer, comprehensive articles rank better in search results.'
        })
        score -= 0.10
    
    # Sort issues by priority
    priority_order = {'High': 0, 'Medium': 1, 'Low': 2}
    issues.sort(key=lambda x: priority_order.get(x.get('priority', 'Low'), 3))
    
    return {
        'score': max(0, score),
        'issues': issues,
        'details': details,
    }

def run_comprehensive_seo_analysis(url: str) -> dict:
    """
    Comprehensive SEO analysis for /seo page
    More detailed than fast version, takes 20-30 seconds
    """
    start_time = time.time()
    
    try:
        # 1. Fetch page
        page_data = fetch_page(url)
        if not page_data['success']:
            return {
                'status': 'error',
                'error': page_data.get('error', 'Failed to fetch URL'),
                'seo_score': 0.0,
                'issues': [],
                'recommendations': [],
            }
        
        soup = page_data['soup']
        final_url = page_data['final_url']
        
        # 2. Comprehensive analysis
        analysis = analyze_seo_comprehensive(soup, final_url)
        
        # 3. Prepare response
        overall_score = analysis['score']
        all_issues = analysis['issues']
        
        return {
            'status': 'completed',
            'url': url,
            'final_url': final_url,
            'seo_score': overall_score,
            'scores': {
                'overall': overall_score,
                'recommendations': len(all_issues),
                'high_priority': len([i for i in all_issues if i.get('priority') == 'High']),
                'medium_priority': len([i for i in all_issues if i.get('priority') == 'Medium']),
                'low_priority': len([i for i in all_issues if i.get('priority') == 'Low']),
            },
            'recommendations': all_issues,
            'details': analysis['details'],
            'timestamp': datetime.now().isoformat(),
            'analysis_time': f"{time.time() - start_time:.1f}s",
        }
    except Exception as e:
        logger.error(f"Comprehensive SEO analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            'status': 'error',
            'error': str(e),
            'seo_score': 0.0,
            'issues': [],
            'recommendations': [],
        }

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        result = run_comprehensive_seo_analysis(sys.argv[1])
        import json
        print(json.dumps(result, indent=2))
