#!/bin/bash
# Check status of all FYP Marketing Platform agents
# Usage: ./status.sh

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   FYP Marketing Platform - Agent Status           ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════╝${NC}"
echo ""

# Define agents with their ports
declare -A AGENTS=(
    ["Orchestrator"]="8004"
    ["Webcrawler"]="8000"
    ["Keywords"]="8001"
    ["GapAnalyzer"]="8002"
    ["Content"]="8003"
    ["Image"]="8005"
    ["Brand"]="8006"
    ["Critic"]="8007"
    ["Campaign"]="8008"
    ["Research"]="8009"
    ["SEO"]="5000"
    ["Reddit"]="8010"
    ["DemoRunner"]="8020"
)

# Function to check if port is listening
check_port() {
    local PORT=$1
    if command -v lsof &> /dev/null; then
        lsof -i:$PORT -sTCP:LISTEN -t >/dev/null 2>&1
    elif command -v netstat &> /dev/null; then
        netstat -ln 2>/dev/null | grep -q ":$PORT "
    else
        # Fallback: try curl
        curl -s --connect-timeout 1 http://localhost:$PORT >/dev/null 2>&1
    fi
}

# Function to get HTTP status
get_http_status() {
    local PORT=$1
    local STATUS=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 http://localhost:$PORT 2>/dev/null || echo "000")
    echo "$STATUS"
}

RUNNING=0
STOPPED=0

echo -e "${CYAN}┌────────────────┬──────┬──────────┬─────────────┐${NC}"
echo -e "${CYAN}│ Agent          │ Port │ Status   │ HTTP Code   │${NC}"
echo -e "${CYAN}├────────────────┼──────┼──────────┼─────────────┤${NC}"

# Sort agents by port
for AGENT in $(echo "${!AGENTS[@]}" | tr ' ' '\n' | sort); do
    PORT="${AGENTS[$AGENT]}"
    
    # Pad agent name to 14 chars
    AGENT_PADDED=$(printf "%-14s" "$AGENT")
    PORT_PADDED=$(printf "%-4s" "$PORT")
    
    if check_port $PORT; then
        STATUS=$(get_http_status $PORT)
        if [ "$STATUS" = "000" ]; then
            STATUS_TEXT="UNKNOWN"
            STATUS_COLOR=$YELLOW
        elif [ "$STATUS" = "404" ] || [ "$STATUS" = "200" ]; then
            STATUS_TEXT="RUNNING"
            STATUS_COLOR=$GREEN
            RUNNING=$((RUNNING + 1))
        else
            STATUS_TEXT="ERROR"
            STATUS_COLOR=$RED
        fi
        echo -e "${CYAN}│${NC} ${AGENT_PADDED} ${CYAN}│${NC} ${PORT_PADDED} ${CYAN}│${NC} ${STATUS_COLOR}✓ ${STATUS_TEXT}${NC} ${CYAN}│${NC} ${STATUS}         ${CYAN}│${NC}"
    else
        echo -e "${CYAN}│${NC} ${AGENT_PADDED} ${CYAN}│${NC} ${PORT_PADDED} ${CYAN}│${NC} ${RED}✗ STOPPED${NC} ${CYAN}│${NC} -           ${CYAN}│${NC}"
        STOPPED=$((STOPPED + 1))
    fi
done

echo -e "${CYAN}└────────────────┴──────┴──────────┴─────────────┘${NC}"
echo ""

# Summary
TOTAL=$((RUNNING + STOPPED))
echo -e "${BLUE}Summary:${NC}"
echo -e "  ${GREEN}●${NC} Running: $RUNNING/$TOTAL"
echo -e "  ${RED}●${NC} Stopped: $STOPPED/$TOTAL"
echo ""

# Check MCP/A2A status if orchestrator is running
if check_port 8004; then
    echo -e "${BLUE}Protocol Status:${NC}"
    
    # Try to get protocol info from orchestrator
    PROTOCOLS=$(curl -s http://localhost:8004/ 2>/dev/null | grep -o '"mcp_enabled":[^,]*' || echo "")
    
    if [[ $PROTOCOLS == *"true"* ]]; then
        echo -e "  ${GREEN}✓${NC} MCP Protocol: Enabled"
    else
        echo -e "  ${YELLOW}✗${NC} MCP Protocol: Disabled"
    fi
    
    A2A=$(curl -s http://localhost:8004/ 2>/dev/null | grep -o '"a2a_enabled":[^,]*' || echo "")
    if [[ $A2A == *"true"* ]]; then
        echo -e "  ${GREEN}✓${NC} A2A Protocol: Enabled"
    else
        echo -e "  ${YELLOW}✗${NC} A2A Protocol: Disabled"
    fi
    echo ""
    
    echo -e "${BLUE}Quick Links:${NC}"
    echo -e "  • Orchestrator API: ${CYAN}http://localhost:8004${NC}"
    echo -e "  • API Docs:         ${CYAN}http://localhost:8004/docs${NC}"
    echo -e "  • A2A AgentCard:    ${CYAN}http://localhost:8004/.well-known/agent.json${NC}"
    echo -e "  • Health Check:     ${CYAN}http://localhost:8004/health${NC}"
    echo ""
fi

# Show log files
if [ -d "logs" ]; then
    LOG_COUNT=$(ls -1 logs/*.log 2>/dev/null | wc -l | tr -d ' ')
    if [ "$LOG_COUNT" -gt 0 ]; then
        echo -e "${BLUE}Recent Logs:${NC}"
        echo -e "  View all: ${YELLOW}tail -f logs/*.log${NC}"
        echo -e "  Orchestrator: ${YELLOW}tail -f logs/Orchestrator.log${NC}"
        echo ""
    fi
fi

# Show helpful commands
echo -e "${BLUE}Commands:${NC}"
echo -e "  Start agents:  ${YELLOW}./start.sh${NC}"
echo -e "  Stop agents:   ${YELLOW}./stop.sh${NC}"
echo -e "  Watch status:  ${YELLOW}watch -n 2 ./status.sh${NC}"
echo ""

