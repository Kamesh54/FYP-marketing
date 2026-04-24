"""
Fast SEO Analysis - Lightweight version for chat integration
Returns quick results without full crawl/rendering
"""
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Real browser User-Agents
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
]

def fast_fetch_page(url: str, timeout: int = 15) -> dict:
    """Quickly fetch page without full crawl"""
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
        return {
            'success': False,
            'url': url,
            'error': str(e),
        }

def fast_analyze_onpage(soup: BeautifulSoup) -> dict:
    """Quick on-page analysis"""
    issues = []
    score = 1.0
    
    # Title
    title = soup.find('title')
    if not title or not title.string or len(title.string.strip()) == 0:
        issues.append({
            'area': 'Content & Keywords',
            'issue': 'No page title found',
            'priority': 'High',
            'suggestion': 'Add a unique, descriptive page title. Keep it 50-60 characters and include your main keyword near the beginning.'
        })
        score -= 0.15
    elif len(title.string) < 30 or len(title.string) > 60:
        issues.append({
            'area': 'Content & Keywords',
            'issue': f'Title length is {len(title.string)} characters (ideal: 50-60)',
            'priority': 'Medium',
            'suggestion': 'Optimize your title length to 50-60 characters for better search visibility.'
        })
        score -= 0.05
    
    # Meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if not meta_desc or not meta_desc.get('content'):
        issues.append({
            'area': 'Content & Keywords',
            'issue': 'Meta description is missing',
            'priority': 'High',
            'suggestion': 'Add a compelling meta description (120-160 characters) that summarizes your page and includes your target keyword.'
        })
        score -= 0.15
    elif len(meta_desc.get('content', '')) < 120 or len(meta_desc.get('content', '')) > 160:
        issues.append({
            'area': 'Content & Keywords',
            'issue': f'Meta description length is {len(meta_desc.get("content", ""))} characters (ideal: 120-160)',
            'priority': 'Medium',
            'suggestion': 'Optimize your meta description length for better search visibility.'
        })
        score -= 0.05
    
    # H1 tags
    h1_tags = soup.find_all('h1')
    if len(h1_tags) == 0:
        issues.append({
            'area': 'Content & Keywords',
            'issue': 'No H1 tag found',
            'priority': 'High',
            'suggestion': 'Add a single H1 tag that contains your primary keyword. H1 tags help search engines understand your page topic.'
        })
        score -= 0.10
    elif len(h1_tags) > 1:
        issues.append({
            'area': 'Content & Keywords',
            'issue': f'Multiple H1 tags found ({len(h1_tags)})',
            'priority': 'Medium',
            'suggestion': 'Use only one H1 tag per page. Multiple H1 tags can confuse search engines about your page topic.'
        })
        score -= 0.05
    
    # Heading structure
    h2_tags = soup.find_all('h2')
    if len(h2_tags) == 0:
        issues.append({
            'area': 'Content & Keywords',
            'issue': 'No H2 tags found',
            'priority': 'Low',
            'suggestion': 'Add H2 subheadings to organize your content. This improves both readability and SEO.'
        })
        score -= 0.03
    
    # Images without alt text
    images = soup.find_all('img')
    images_without_alt = [img for img in images if not img.get('alt') or img.get('alt').strip() == '']
    if images_without_alt:
        issues.append({
            'area': 'Accessibility & SEO',
            'issue': f'{len(images_without_alt)} images missing alt text',
            'priority': 'High',
            'suggestion': f'Add descriptive alt text to all {len(images_without_alt)} images. Alt text helps search engines understand your images and improves accessibility.'
        })
        score -= 0.10
    
    # Internal links
    internal_links = []
    base_domain = urlparse(soup.find('base')['href'] if soup.find('base') else 'http://example.com').netloc
    for a in soup.find_all('a', href=True):
        href_domain = urlparse(a['href']).netloc
        if not href_domain or href_domain == base_domain:
            internal_links.append(a)
    
    if len(internal_links) < 3:
        issues.append({
            'area': 'Internal Linking',
            'issue': f'Only {len(internal_links)} internal links found',
            'priority': 'Medium',
            'suggestion': 'Add more internal links to improve site structure and help search engines crawl your content.'
        })
        score -= 0.05
    
    return {
        'score': max(0, score),
        'issues': issues,
        'title_length': len(title.string) if title and title.string else 0,
        'h1_count': len(h1_tags),
        'h2_count': len(h2_tags),
        'images_count': len(images),
        'internal_links_count': len(internal_links),
    }

def fast_analyze_technical(url: str) -> dict:
    """Quick technical SEO checks (without slow DNS/SSL analysis)"""
    issues = []
    score = 1.0
    
    parsed = urlparse(url)
    
    # Check if HTTPS
    if parsed.scheme != 'https':
        issues.append({
            'area': 'Technical SEO',
            'issue': 'Not using HTTPS',
            'priority': 'High',
            'suggestion': 'Migrate your site to HTTPS. It\'s required by Google for proper security and SEO ranking.'
        })
        score -= 0.20
    
    # Check for robots.txt
    try:
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        r = requests.head(robots_url, timeout=5)
        if r.status_code != 200:
            issues.append({
                'area': 'Technical SEO',
                'issue': 'robots.txt not accessible',
                'priority': 'Low',
                'suggestion': 'Ensure robots.txt is properly configured to guide search engine crawlers.'
            })
            score -= 0.05
    except:
        pass
    
    return {
        'score': max(0, score),
        'issues': issues,
        'protocol': parsed.scheme,
    }

def run_fast_seo_analysis(url: str) -> dict:
    """
    Fast SEO analysis for chat integration
    Complete in 20-30 seconds instead of 90+ seconds
    """
    try:
        # 1. Fetch page quickly
        page_data = fast_fetch_page(url)
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
        
        # 2. Quick analysis
        onpage = fast_analyze_onpage(soup)
        technical = fast_analyze_technical(final_url)
        
        # 3. Combine scores
        overall_score = (onpage['score'] * 0.7 + technical['score'] * 0.3)
        
        # 4. Combine issues
        all_issues = onpage.get('issues', []) + technical.get('issues', [])
        
        # 5. Sort by priority
        priority_order = {'High': 0, 'Medium': 1, 'Low': 2}
        all_issues.sort(key=lambda x: priority_order.get(x.get('priority', 'Low'), 3))
        
        # 6. Calculate priority counts
        high_count = len([i for i in all_issues if i.get('priority') == 'High'])
        medium_count = len([i for i in all_issues if i.get('priority') == 'Medium'])
        low_count = len([i for i in all_issues if i.get('priority') == 'Low'])
        
        return {
            'status': 'completed',
            'url': url,
            'final_url': final_url,
            'seo_score': overall_score,
            'scores': {
                'overall': overall_score,
                'onpage': onpage['score'],
                'technical': technical['score'],
                'recommendations': len(all_issues),
                'high_priority': high_count,
                'medium_priority': medium_count,
                'low_priority': low_count,
            },
            'recommendations': all_issues[:10],  # Top 10 recommendations
            'issues': all_issues,
            'timestamp': datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Fast SEO analysis failed: {e}")
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
        result = run_fast_seo_analysis(sys.argv[1])
        import json
        print(json.dumps(result, indent=2))
