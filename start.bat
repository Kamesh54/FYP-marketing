@echo off
REM ============================================================================
REM  AI Multi-Agent System Launcher with Port Cleanup
REM ============================================================================
REM This script kills any process using ports 8000–8004, then launches each
REM microservice in its own command prompt window.
REM Make sure dependencies are installed: pip install -r requirements.txt
REM ============================================================================


FOR %%P IN (8000 8001 8002 8003 8004) DO (
    FOR /F "tokens=5" %%T IN ('netstat -aon ^| findstr :%%P') DO (
        ECHO Killing process on ports
        taskkill /F /PID %%T >nul 2>&1
    )
)
timeout /t 2 /nobreak >nul

ECHO Starting all AI agent microservices...
ECHO.

REM --- Start Microservice Agents ---
ECHO Launching Web Crawler on port 8000...
START "web crawler (Port 8000)" cmd /k python webcrawler.py
timeout /t 3 /nobreak >nul

ECHO Launching Keyword Extractor on port 8001...
START "Keyword Extraction (Port 8001)" cmd /k python keywordExtraction.py
timeout /t 3 /nobreak >nul

ECHO Launching Gap Analyzer on port 8002...
START "Gap Analyzer (Port 8002)" cmd /k python CompetitorGapAnalyzerAgent.py
timeout /t 3 /nobreak >nul

ECHO Launching Content Agent on port 8003...
START "Content Agent (Port 8003)" cmd /k python content_agent.py
timeout /t 3 /nobreak >nul

REM --- Start the Main Orchestrator ---
ECHO Launching the main Orchestrator on port 8004...
START "Orchestrator (Port 8004)" cmd /k python orchestrator.py
timeout /t 3 /nobreak >nul

ECHO.
ECHO ============================================================================
ECHO All backend services have been launched in separate windows.
ECHO.
ECHO Next Step: Run the Frontend
ECHO -----------------------------
ECHO Open a new terminal and serve the index.html file.
ECHO For example, using Python's built-in web server:
ECHO   cd [directory_with_index.html]
ECHO   python -m http.server
ECHO Then open http://localhost:8000 in your browser.
ECHO ============================================================================
ECHO.

PAUSE