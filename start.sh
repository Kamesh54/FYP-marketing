#!/bin/bash
# Start all FYP Marketing Platform agents
# Usage: ./start.sh

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Python command (prefer python3)
if command -v python3 &> /dev/null; then
    PY="python3"
elif command -v python &> /dev/null; then
    PY="python"
else
    echo -e "${RED}Error: Python not found${NC}"
    exit 1
fi

echo -e "${BLUE}╔════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   FYP Marketing Platform - Agent Launcher         ║${NC}"
echo -e "${BLUE}║   MCP & A2A Enabled                                ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════╝${NC}"
echo ""

# Define ports to check/kill
PORTS=(5000 8000 8001 8002 8003 8004 8005 8006 8007 8008 8009 8010 8020)

echo -e "${YELLOW}[1/3] Killing old processes on ports: ${PORTS[@]}${NC}"

# Kill processes on specific ports
for PORT in "${PORTS[@]}"; do
    # Find PID listening on port
    if command -v lsof &> /dev/null; then
        # Use lsof (macOS/Linux)
        PID=$(lsof -ti:$PORT 2>/dev/null || true)
    elif command -v netstat &> /dev/null; then
        # Fallback to netstat (Linux)
        PID=$(netstat -nlp 2>/dev/null | grep ":$PORT " | awk '{print $7}' | cut -d'/' -f1 || true)
    else
        PID=""
    fi
    
    if [ -n "$PID" ]; then
        echo "  Killing process on port $PORT (PID: $PID)"
        kill -9 $PID 2>/dev/null || true
        sleep 0.2
    fi
done

echo ""
echo -e "${YELLOW}[2/3] Creating log directory${NC}"
mkdir -p logs

echo ""
echo -e "${YELLOW}[3/3] Starting agents...${NC}"

# Function to start an agent
start_agent() {
    local NAME=$1
    local PORT=$2
    local SCRIPT=$3
    local LOG="logs/${NAME}.log"
    
    echo -e "  ${GREEN}✓${NC} Starting ${NAME} on port ${PORT}"
    nohup $PY "$SCRIPT" > "$LOG" 2>&1 &
    echo $! > "logs/${NAME}.pid"
    sleep 0.5
}

# Start all agents
start_agent "Webcrawler" "8000" "webcrawler.py"
start_agent "Keywords" "8001" "keywordExtraction.py"
start_agent "GapAnalyzer" "8002" "CompetitorGapAnalyzerAgent.py"
start_agent "Content" "8003" "content_agent.py"
start_agent "Image" "8005" "image_agent.py"
start_agent "Brand" "8006" "brand_agent.py"
start_agent "Critic" "8007" "critic_agent.py"
start_agent "Campaign" "8008" "campaign_agent.py"
start_agent "Research" "8009" "research_agent.py"
start_agent "SEO" "5000" "seo_agent.py"
start_agent "Reddit" "8010" "reddit_agent.py"
start_agent "Orchestrator" "8004" "orchestrator.py"
start_agent "DemoRunner" "8020" "demo_runner.py"

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   All 13 agents launched successfully!             ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}Services running:${NC}"
echo "  • Orchestrator (MCP & A2A): http://localhost:8004"
echo "  • Webcrawler:               http://localhost:8000"
echo "  • Keywords:                 http://localhost:8001"
echo "  • Gap Analyzer:             http://localhost:8002"
echo "  • Content Agent:            http://localhost:8003"
echo "  • Image Agent:              http://localhost:8005"
echo "  • Brand Agent:              http://localhost:8006"
echo "  • Critic Agent:             http://localhost:8007"
echo "  • Campaign Agent:           http://localhost:8008"
echo "  • Research Agent:           http://localhost:8009"
echo "  • SEO Agent:                http://localhost:5000"
echo "  • Reddit Agent:             http://localhost:8010"
echo "  • Demo Runner:              http://localhost:8020"
echo ""
echo -e "${YELLOW}Logs:${NC} ./logs/*.log"
echo -e "${YELLOW}PIDs:${NC} ./logs/*.pid"
echo ""
echo -e "${BLUE}Commands:${NC}"
echo "  • View logs:     tail -f logs/Orchestrator.log"
echo "  • Stop all:      ./stop.sh"
echo "  • Check status:  ./status.sh"
echo ""

