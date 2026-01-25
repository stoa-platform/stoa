#!/bin/sh
# STOA Installation Script
# https://get.gostoa.dev
#
# Usage:
#   curl -sfL https://get.gostoa.dev | sh
#   curl -sfL https://get.gostoa.dev | sh -s -- --quickstart
#   curl -sfL https://get.gostoa.dev | sh -s -- --cli
#   curl -sfL https://get.gostoa.dev | sh -s -- --helm

set -e

STOA_REPO="https://github.com/gostoa/stoa.git"
STOA_VERSION="${STOA_VERSION:-latest}"
STOA_INSTALL_DIR="${STOA_INSTALL_DIR:-./stoa}"
STOA_QUICKSTART_PATH="deploy/docker-compose"
STOA_CLI_RELEASES="https://github.com/gostoa/stoactl/releases"
STOA_HELM_REPO="https://charts.gostoa.dev"

CONSOLE_PORT="${CONSOLE_PORT:-3000}"
API_PORT="${API_PORT:-8000}"
GRAFANA_PORT="${GRAFANA_PORT:-3002}"

setup_colors() {
    if [ -t 1 ] && [ -z "${STOA_NO_COLOR:-}" ]; then
        RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
        BLUE='\033[0;34m'; CYAN='\033[0;36m'; MAGENTA='\033[0;35m'
        BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'
    else
        RED=''; GREEN=''; YELLOW=''; BLUE=''; CYAN=''; MAGENTA=''; BOLD=''; DIM=''; NC=''
    fi
}

info()    { printf "${BLUE}▸${NC} %s\n" "$1"; }
success() { printf "${GREEN}✓${NC} %s\n" "$1"; }
warn()    { printf "${YELLOW}⚠${NC} %s\n" "$1"; }
error()   { printf "${RED}✗${NC} %s\n" "$1" >&2; }
fatal()   { error "$1"; exit 1; }
debug()   { [ -n "${STOA_DEBUG:-}" ] && printf "${DIM}[debug] %s${NC}\n" "$1"; }
step()    { printf "\n${BOLD}${CYAN}→ %s${NC}\n\n" "$1"; }

banner() {
    printf "${MAGENTA}"
    cat << 'EOF'

  ███████╗████████╗ ██████╗  █████╗
  ██╔════╝╚══██╔══╝██╔═══██╗██╔══██╗
  ███████╗   ██║   ██║   ██║███████║
  ╚════██║   ██║   ██║   ██║██╔══██║
  ███████║   ██║   ╚██████╔╝██║  ██║
  ╚══════╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝

EOF
    printf "${NC}"
    printf "  ${BOLD}The European Agent Gateway${NC}\n"
    printf "  ${DIM}https://gostoa.dev${NC}\n\n"
}

detect_os() {
    OS="$(uname -s)"; ARCH="$(uname -m)"
    case "$OS" in
        Linux)
            [ -f /etc/os-release ] && . /etc/os-release && OS_PRETTY="${NAME:-Linux}" || OS_PRETTY="Linux"
            grep -qi microsoft /proc/version 2>/dev/null && OS_PRETTY="WSL2 (${OS_PRETTY})" && IS_WSL=1
            ;;
        Darwin) OS_PRETTY="macOS $(sw_vers -productVersion 2>/dev/null || echo '')" ;;
        MINGW*|MSYS*|CYGWIN*) OS_PRETTY="Windows (Git Bash)"; warn "Consider using WSL2" ;;
        *) OS_PRETTY="$OS" ;;
    esac
    case "$ARCH" in
        x86_64|amd64) ARCH="amd64"; ARCH_PRETTY="x86_64" ;;
        aarch64|arm64) ARCH="arm64"; ARCH_PRETTY="ARM64" ;;
        *) ARCH_PRETTY="$ARCH" ;;
    esac
    success "OS: ${OS_PRETTY} (${ARCH_PRETTY})"
}

check_command() { command -v "$1" >/dev/null 2>&1; }

check_docker() {
    if check_command docker; then
        if ! docker info >/dev/null 2>&1; then
            warn "Docker found but daemon not running"; HAS_DOCKER=0; return 1
        fi
        DOCKER_VERSION=$(docker --version | sed 's/Docker version \([^,]*\).*/\1/')
        success "Docker: ${DOCKER_VERSION}"; HAS_DOCKER=1; return 0
    fi
    warn "Docker not found"; HAS_DOCKER=0; return 1
}

check_docker_compose() {
    if docker compose version >/dev/null 2>&1; then
        COMPOSE_VERSION=$(docker compose version --short 2>/dev/null || docker compose version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
        COMPOSE_CMD="docker compose"; success "Docker Compose: ${COMPOSE_VERSION}"; HAS_COMPOSE=1; return 0
    elif check_command docker-compose; then
        COMPOSE_VERSION=$(docker-compose --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
        COMPOSE_CMD="docker-compose"; success "Docker Compose: ${COMPOSE_VERSION} (standalone)"; HAS_COMPOSE=1; return 0
    fi
    warn "Docker Compose not found"; HAS_COMPOSE=0; return 1
}

check_git() {
    if check_command git; then
        success "Git: $(git --version | cut -d' ' -f3)"; HAS_GIT=1; return 0
    fi
    warn "Git not found"; HAS_GIT=0; return 1
}

check_kubectl() {
    check_command kubectl && HAS_KUBECTL=1 && success "kubectl: found" || HAS_KUBECTL=0
}

check_helm() {
    check_command helm && HAS_HELM=1 && success "Helm: $(helm version --short 2>/dev/null | cut -d'+' -f1)" || HAS_HELM=0
}

detect_environment() {
    step "Detecting environment"
    detect_os; check_git || true; check_docker || true; check_docker_compose || true
    check_kubectl || true; check_helm || true
}

wait_for_service() {
    URL="$1"; SERVICE_NAME="$2"; TIMEOUT="${3:-60}"; ELAPSED=0
    while [ $ELAPSED -lt $TIMEOUT ]; do
        curl -sf "$URL" >/dev/null 2>&1 && success "${SERVICE_NAME} is ready" && return 0
        sleep 2; ELAPSED=$((ELAPSED + 2)); printf "."
    done
    warn "${SERVICE_NAME} not responding after ${TIMEOUT}s"; return 0
}

install_quickstart() {
    step "Installing STOA Quick Start"
    [ "$HAS_GIT" -eq 0 ] && fatal "Git is required. Install from https://git-scm.com"
    [ "$HAS_DOCKER" -eq 0 ] && fatal "Docker is required. Install from https://docker.com"
    [ "$HAS_COMPOSE" -eq 0 ] && fatal "Docker Compose is required"

    if [ -d "$STOA_INSTALL_DIR" ]; then
        warn "Directory ${STOA_INSTALL_DIR} already exists"
        if [ -z "${STOA_YES:-}" ]; then
            printf "  Remove and reinstall? [y/N] "; read -r response
            case "$response" in [yY]*) rm -rf "$STOA_INSTALL_DIR" ;; *) info "Cancelled"; exit 0 ;; esac
        else rm -rf "$STOA_INSTALL_DIR"; fi
    fi

    info "Cloning STOA repository..."
    if [ "$STOA_VERSION" = "latest" ]; then
        git clone --depth 1 "$STOA_REPO" "$STOA_INSTALL_DIR" >/dev/null 2>&1
    else
        git clone --depth 1 --branch "$STOA_VERSION" "$STOA_REPO" "$STOA_INSTALL_DIR" >/dev/null 2>&1
    fi
    success "Repository cloned to ${STOA_INSTALL_DIR}"

    cd "${STOA_INSTALL_DIR}/${STOA_QUICKSTART_PATH}"
    [ -f .env.example ] && [ ! -f .env ] && cp .env.example .env && success "Environment file created"

    info "Pulling Docker images..."; $COMPOSE_CMD pull >/dev/null 2>&1; success "Images pulled"
    info "Starting STOA services..."; START_TIME=$(date +%s)
    $COMPOSE_CMD up -d >/dev/null 2>&1
    success "Services started ($(($(date +%s) - START_TIME))s)"

    info "Waiting for services..."
    wait_for_service "http://localhost:${API_PORT}/health" "Control Plane" 60

    printf "\n${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
    printf "${GREEN}${BOLD}  STOA is running!${NC}\n"
    printf "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n\n"
    printf "  ${BOLD}Console${NC}   http://localhost:${CONSOLE_PORT}  ${DIM}(halliday / readyplayerone)${NC}\n"
    printf "  ${BOLD}API Docs${NC}  http://localhost:${API_PORT}/docs\n"
    printf "  ${BOLD}Grafana${NC}   http://localhost:${GRAFANA_PORT}  ${DIM}(admin / admin)${NC}\n\n"
    printf "  ${BOLD}Next:${NC} cd ${STOA_INSTALL_DIR}/${STOA_QUICKSTART_PATH} && docker compose logs -f\n\n"
}

install_cli() {
    step "Installing stoactl CLI"
    INSTALL_PATH="${STOA_CLI_PATH:-/usr/local/bin}"; TMP_DIR=$(mktemp -d); trap 'rm -rf "$TMP_DIR"' EXIT
    if [ "$STOA_VERSION" = "latest" ]; then
        URL="${STOA_CLI_RELEASES}/latest/download/stoactl_${OS}_${ARCH}.tar.gz"
    else
        URL="${STOA_CLI_RELEASES}/download/${STOA_VERSION}/stoactl_${OS}_${ARCH}.tar.gz"
    fi
    info "Downloading stoactl..."; curl -fsSL "$URL" | tar -xz -C "$TMP_DIR"
    if [ -w "$INSTALL_PATH" ]; then
        mv "${TMP_DIR}/stoactl" "${INSTALL_PATH}/stoactl"
    else
        info "Requires sudo..."; sudo mv "${TMP_DIR}/stoactl" "${INSTALL_PATH}/stoactl"
    fi
    chmod +x "${INSTALL_PATH}/stoactl"; success "stoactl installed to ${INSTALL_PATH}/stoactl"
    printf "\n  ${CYAN}stoactl --help${NC}  to get started\n\n"
}

install_helm() {
    step "Installing STOA via Helm"
    [ "$HAS_KUBECTL" -eq 0 ] && fatal "kubectl required"
    [ "$HAS_HELM" -eq 0 ] && fatal "Helm required"
    kubectl cluster-info >/dev/null 2>&1 || fatal "Cannot connect to cluster"
    success "Connected to: $(kubectl config current-context 2>/dev/null)"
    info "Adding Helm repo..."; helm repo add stoa "$STOA_HELM_REPO" >/dev/null 2>&1; helm repo update >/dev/null 2>&1
    NAMESPACE="${STOA_NAMESPACE:-stoa-system}"
    kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 || kubectl create namespace "$NAMESPACE"
    info "Installing chart..."; helm install stoa stoa/stoa --namespace "$NAMESPACE" --create-namespace >/dev/null 2>&1
    success "STOA installed in namespace ${NAMESPACE}"
    printf "\n  ${CYAN}kubectl get pods -n ${NAMESPACE}${NC}  to check status\n\n"
}

show_menu() {
    printf "\n  ${BOLD}Choose installation method:${NC}\n\n"
    printf "    ${CYAN}1)${NC} Quick Start (Docker Compose) ${DIM}— recommended${NC}\n"
    printf "    ${CYAN}2)${NC} stoactl CLI only\n"
    printf "    ${CYAN}3)${NC} Kubernetes (Helm)\n"
    printf "    ${CYAN}q)${NC} Quit\n\n  ${BOLD}>${NC} "
}

interactive_install() {
    while true; do
        show_menu; read -r choice
        case "$choice" in
            1) [ "$HAS_DOCKER" -eq 0 ] || [ "$HAS_COMPOSE" -eq 0 ] && { error "Docker required"; continue; }; install_quickstart; break ;;
            2) install_cli; break ;;
            3) [ "$HAS_KUBECTL" -eq 0 ] || [ "$HAS_HELM" -eq 0 ] && { error "kubectl/Helm required"; continue; }; install_helm; break ;;
            q|Q) info "Cancelled"; exit 0 ;;
            *) warn "Invalid choice" ;;
        esac
    done
}

usage() {
    cat << EOF
STOA Installation Script

Usage:
  curl -sfL https://get.gostoa.dev | sh
  curl -sfL https://get.gostoa.dev | sh -s -- [OPTIONS]

Options:
  --quickstart    Docker Compose install
  --cli           stoactl CLI only
  --helm          Kubernetes install
  --version VER   Specific version
  --yes, -y       Skip confirmations
  --help, -h      This help

Environment:
  STOA_VERSION      Version to install (default: latest)
  STOA_INSTALL_DIR  Directory (default: ./stoa)
  STOA_NO_COLOR     Disable colors
  STOA_YES          Skip confirmations
  STOA_DEBUG        Debug output

Examples:
  curl -sfL https://get.gostoa.dev | sh -s -- --quickstart
  curl -sfL https://get.gostoa.dev | STOA_VERSION=v0.2.0 sh
EOF
}

main() {
    setup_colors; INSTALL_MODE=""
    while [ $# -gt 0 ]; do
        case "$1" in
            --quickstart) INSTALL_MODE="quickstart"; shift ;;
            --cli) INSTALL_MODE="cli"; shift ;;
            --helm) INSTALL_MODE="helm"; shift ;;
            --version) STOA_VERSION="$2"; shift 2 ;;
            --yes|-y) STOA_YES=1; shift ;;
            --help|-h) usage; exit 0 ;;
            --debug) STOA_DEBUG=1; shift ;;
            *) error "Unknown: $1"; usage; exit 1 ;;
        esac
    done
    banner; detect_environment
    if [ -n "$INSTALL_MODE" ]; then
        case "$INSTALL_MODE" in
            quickstart) install_quickstart ;;
            cli) install_cli ;;
            helm) install_helm ;;
        esac
    else
        interactive_install
    fi
}

main "$@"
