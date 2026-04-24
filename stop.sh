#!/bin/bash
# Stop all FYP Marketing Platform agents
# Usage: ./stop.sh

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

echo -e "${BLUE}╔════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   FYP Marketing Platform - Stopping Agents        ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════╝${NC}"
echo ""

# Define ports to kill
PORTS=(5000 8000 8001 8002 8003 8004 8005 8006 8007 8008 8009 8010 8020)

echo -e "${YELLOW}Stopping agents on ports: ${PORTS[@]}${NC}"
echo ""

# Kill processes on specific ports
STOPPED=0
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
        echo -e "  ${RED}✗${NC} Stopping agent on port $PORT (PID: $PID)"
        kill -9 $PID 2>/dev/null || true
        STOPPED=$((STOPPED + 1))
        sleep 0.2
    fi
done

# Also kill by PID files if they exist
if [ -d "logs" ]; then
    echo ""
    echo -e "${YELLOW}Cleaning up PID files...${NC}"
    for PIDFILE in logs/*.pid; do
        if [ -f "$PIDFILE" ]; then
            PID=$(cat "$PIDFILE" 2>/dev/null || true)
            if [ -n "$PID" ]; then
                kill -9 $PID 2>/dev/null || true
            fi
            rm -f "$PIDFILE"
        fi
    done
fi

echo ""
if [ $STOPPED -gt 0 ]; then
    echo -e "${GREEN}╔════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║   Stopped $STOPPED agent(s) successfully              ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════╝${NC}"
else
    echo -e "${YELLOW}╔════════════════════════════════════════════════════╗${NC}"
    echo -e "${YELLOW}║   No agents were running                          ║${NC}"
    echo -e "${YELLOW}╚════════════════════════════════════════════════════╝${NC}"
fi
echo ""

