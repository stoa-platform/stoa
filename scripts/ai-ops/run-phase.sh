#!/usr/bin/env bash
# run-phase.sh — Lance une phase Claude Code en background
# Usage: ./run-phase.sh CAB-XXXX

set -euo pipefail

TICKET_ID="${1:-}"
SLACK_WEBHOOK="${SLACK_WEBHOOK:-}"
PHASE_DIR=".stoa-ai/phases/$TICKET_ID"

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Validation
if [ -z "$TICKET_ID" ]; then
    echo -e "${RED}Usage: ./run-phase.sh CAB-XXXX${NC}"
    exit 1
fi

if [ ! -d "$PHASE_DIR" ]; then
    echo -e "${RED}Phase directory not found: $PHASE_DIR${NC}"
    echo -e "${YELLOW}Create it first with: mkdir -p $PHASE_DIR${NC}"
    exit 1
fi

if [ ! -f "$PHASE_DIR/plan.md" ]; then
    echo -e "${RED}plan.md not found in $PHASE_DIR${NC}"
    echo -e "${YELLOW}Copy template: cp .stoa-ai/templates/PHASE-PLAN.md $PHASE_DIR/plan.md${NC}"
    exit 1
fi

echo -e "${GREEN}🚀 Starting Claude Code for $TICKET_ID${NC}"
echo "Phase dir: $PHASE_DIR"
echo "Plan file: $PHASE_DIR/plan.md"

# Notify Slack start
if [ -n "$SLACK_WEBHOOK" ]; then
    curl -s -X POST "$SLACK_WEBHOOK" \
        -H 'Content-Type: application/json' \
        -d "{\"text\":\"🚀 *$TICKET_ID* — Phase started\"}" > /dev/null
fi

# Create log directory
mkdir -p "$PHASE_DIR/logs"
LOG_FILE="$PHASE_DIR/logs/$(date +%Y%m%d-%H%M%S).log"

# Option 1: tmux session (interactive)
if command -v tmux &> /dev/null; then
    SESSION_NAME="claude-$TICKET_ID"
    
    # Kill existing session if any
    tmux kill-session -t "$SESSION_NAME" 2>/dev/null || true
    
    # Create new session
    tmux new-session -d -s "$SESSION_NAME" -c "$(pwd)"
    
    # Build the prompt
    PROMPT="Tu es Claude Code pour STOA. Lis .stoa-ai/CLAUDE.md, .stoa-ai/memory.md, et $PHASE_DIR/plan.md. Exécute le plan step by step. Code → Test → Commit. Update plan.md après chaque step. Notifie si bloqué ou terminé."
    
    # Send command to tmux
    tmux send-keys -t "$SESSION_NAME" "claude \"$PROMPT\" 2>&1 | tee $LOG_FILE" Enter
    
    echo -e "${GREEN}✅ Claude Code running in tmux session: $SESSION_NAME${NC}"
    echo -e "${YELLOW}Attach with: tmux attach -t $SESSION_NAME${NC}"
    echo -e "${YELLOW}Detach with: Ctrl+B then D${NC}"
    echo -e "${YELLOW}Log file: $LOG_FILE${NC}"
    
else
    # Option 2: Direct execution (blocking)
    echo -e "${YELLOW}tmux not found, running in foreground...${NC}"
    
    PROMPT="Tu es Claude Code pour STOA. Lis .stoa-ai/CLAUDE.md, .stoa-ai/memory.md, et $PHASE_DIR/plan.md. Exécute le plan step by step."
    
    claude "$PROMPT" 2>&1 | tee "$LOG_FILE"
fi

echo -e "${GREEN}Done.${NC}"
