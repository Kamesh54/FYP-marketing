@echo off
SET PY=%~dp0venv\Scripts\python.exe

ECHO Killing old processes...
netstat -aon | findstr " LISTENING" > "%TEMP%\ag_ports.txt"
FOR %%P IN (5000 8000 8001 8002 8003 8004 8005 8006 8007 8008 8009 8010) DO (
    FOR /F "tokens=5" %%T IN ('findstr ":%%P " "%TEMP%\ag_ports.txt"') DO (
        taskkill /F /PID %%T >nul 2>&1
    )
)
DEL "%TEMP%\ag_ports.txt" >nul 2>&1

ECHO Starting agents...
START "Webcrawler:8000"    cmd /k "%PY%" webcrawler.py
START "Keywords:8001"      cmd /k "%PY%" keywordExtraction.py
START "GapAnalyzer:8002"   cmd /k "%PY%" CompetitorGapAnalyzerAgent.py
START "Content:8003"       cmd /k "%PY%" content_agent.py
START "Image:8005"         cmd /k "%PY%" image_agent.py
START "Brand:8006"         cmd /k "%PY%" brand_agent.py
START "Critic:8007"        cmd /k "%PY%" critic_agent.py
START "Campaign:8008"      cmd /k "%PY%" campaign_agent.py
START "Research:8009"      cmd /k "%PY%" research_agent.py
START "SEO:5000"           cmd /k "%PY%" seo_agent.py
START "Reddit:8010"        cmd /k "%PY%" reddit_agent.py
START "Orchestrator:8004"  cmd /k "%PY%" orchestrator.py

ECHO Done. All 12 agents launched.
