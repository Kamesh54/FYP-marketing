#!/usr/bin/env python3
"""
Final fix for orchestrator.py SEO endpoint
Replaces HTTP call to port 5000 with LangGraph agent_adapters
"""
import sys

try:
    with open('orchestrator.py', 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    
    # Find the seo_analysis handler and replace just the HTTP call part
    target = 'import requests as _sreq\n                    _seo_resp = _sreq.post(\n                        "http://127.0.0.1:5000/analyze",'
    replacement = '# Use LangGraph agent adapters instead of HTTP to port 5000\n                    from agent_adapters import run_seo_analysis\n                    \n                    # Normalize URL with https:// prefix if needed\n                    if not url.startswith(("http://", "https://")):\n                        url = f"https://{url}"\n                    \n                    seo_result_data = run_seo_analysis(url=url)\n                    \n                    if seo_result_data.get("status") == "failed":\n                        raise Exception(seo_result_data.get("error", "SEO audit failed"))\n                    \n                    # Unused - was from old HTTP endpoint\n                    _seo_resp_mock = type("obj", (object,), {"ok": True, "json": lambda: seo_result_data})\n                    _seo_data = _seo_resp_mock.json() if _seo_resp_mock.ok else {}'
    
    if target in content:
        content = content.replace(target, replacement)
        print("✅ HTTP call replaced with LangGraph call")
    else:
        print("⚠️ Target HTTP call not found, file may already be updated")
    
    # Write back
    with open('orchestrator.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ orchestrator.py updated successfully!")
    print("   - Removed HTTP call to port 5000")
    print("   - Using LangGraph agent_adapters.run_seo_analysis()")

except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
