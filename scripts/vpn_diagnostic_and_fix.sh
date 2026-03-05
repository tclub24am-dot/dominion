#!/bin/bash

#===============================================================================
# S-GLOBAL DOMINION Empire
# VPN Diagnostic & Fix Script (X-UI + Xray + VLESS-Reality)
# Protocol: VERSHINA v200.11
#
# Usage: 
#   chmod +x scripts/vpn_diagnostic_and_fix.sh
#   ./scripts/vpn_diagnostic_and_fix.sh [diagnose|fix|full]
#
#===============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Paths
XRAY_CONFIG="/usr/local/x-ui/bin/config.json"
XRAY_CONFIG_BACKUP="/usr/local/x-ui/bin/config.json.backup.$(date +%Y%m%d_%H%M%S)"
LOG_FILE="/var/log/vpn_diagnostic.log"

log() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

#-------------------------------------------------------------------------------
# Phase 1: DIAGNOSTICS
#-------------------------------------------------------------------------------
diagnose() {
    log "${BLUE}=== PHASE 1: DIAGNOSTICS ===${NC}"
    
    echo "=== System Info ==="
    echo "Server IP: $(hostname -I | awk '{print $1}')"
    echo "External IP: $(curl -s ifconfig.me 2>/dev/null || echo 'unknown')"
    echo "Xray Version: $(/usr/local/x-ui/bin/xray-linux-amd64 version 2>/dev/null | head -1)"
    
    echo ""
    echo "=== Service Status ==="
    systemctl status x-ui --no-pager | head -10
    
    echo ""
    echo "=== Listening Ports ==="
    ss -tlnp | grep -E '(8443|2083|4444|443)'
    
    echo ""
    echo "=== Firewall Status (UFW) ==="
    ufw status | grep -E '(8443|2083|Status)'
    
    echo ""
    echo "=== MSS Clamping ==="
    iptables -t mangle -L -n | grep MSS || echo "No MSS rules found"
    
    echo ""
    echo "=== Time Sync ==="
    timedatectl status | grep -E '(System clock|NTP service)'
    
    echo ""
    echo "=== Recent Xray Logs (Errors) ==="
    journalctl -u x-ui --no-pager -n 20 2>/dev/null | grep -iE '(error|warning|fail|tls)'
    
    echo ""
    echo "=== TLS Test to SNI Targets ==="
    timeout 3 openssl s_client -connect www.microsoft.com:443 -servername www.microsoft.com 2>&1 | grep -E 'CONNECTED|verify return' || echo "FAILED"
    timeout 3 openssl s_client -connect www.apple.com:443 -servername www.apple.com 2>&1 | grep -E 'CONNECTED|verify return' || echo "FAILED"
}

#-------------------------------------------------------------------------------
# Phase 2: FIX CONFIGURATION
#-------------------------------------------------------------------------------
fix_config() {
    log "${YELLOW}=== PHASE 2: FIXING CONFIGURATION ===${NC}"
    
    # Backup current config
    log "Backing up current config to: $XRAY_CONFIG_BACKUP"
    cp "$XRAY_CONFIG" "$XRAY_CONFIG_BACKUP"
    
    # Apply fixed config with flow: xtls-rprx-vision
    # This script replaces empty flow with proper flow for Xray 26.x compatibility
    
    # Fix port 8443
    log "Fixing VLESS flow for port 8443..."
    sed -i 's/"flow": ""/"flow": "xtls-rprx-vision"/g' "$XRAY_CONFIG"
    
    # Fix port 2083  
    log "Fixing VLESS flow for port 2083..."
    # Already fixed by sed above
    
    log "Config updated successfully!"
}

#-------------------------------------------------------------------------------
# Phase 3: RESTART SERVICES
#-------------------------------------------------------------------------------
restart_services() {
    log "${YELLOW}=== PHASE 3: RESTARTING SERVICES ===${NC}"
    
    # Restart X-UI (which will restart Xray)
    log "Restarting x-ui service..."
    systemctl restart x-ui
    sleep 3
    
    # Verify service is running
    if systemctl is-active --quiet x-ui; then
        log "${GREEN}x-ui service restarted successfully!${NC}"
    else
        log "${RED}Failed to restart x-ui service!${NC}"
        return 1
    fi
    
    # Verify ports are listening
    sleep 2
    if ss -tln | grep -q ':8443' && ss -tln | grep -q ':2083'; then
        log "${GREEN}Ports 8443 and 2083 are listening!${NC}"
    else
        log "${RED}Warning: Ports may not be listening properly!${NC}"
    fi
}

#-------------------------------------------------------------------------------
# Phase 4: GENERATE CLIENT CONFIGS
#-------------------------------------------------------------------------------
generate_client_configs() {
    log "${BLUE}=== PHASE 4: CLIENT CONFIG GENERATION ===${NC}"
    
    # Generate share links for each user
    echo ""
    echo "=========================================="
    echo "CLIENT CONFIGS (update your clients)"
    echo "=========================================="
    
    # Port 8443 (Microsoft SNI)
    echo ""
    echo "--- Port 8443 (www.microsoft.com) ---"
    echo "VLESS UUIDs:"
    echo "  Dominion: 2980d700-714c-448c-bf77-4f498fc285bb"
    echo "  Galaxe S25: deffca90-7399-428a-8ff0-6dcdb96bf54a"
    echo "  ОФИС: 4a272fdf-abf0-4994-a13c-b9720fb401a2"
    
    # Port 2083 (Apple SNI)  
    echo ""
    echo "--- Port 2083 (www.apple.com) ---"
    echo "VLESS UUIDs:"
    echo "  NeMuBi: e23dfad7-f685-437c-9a7f-95e38c7e042c"
    echo "  Svetlana: 14f48123-7469-4950-b251-9923534c1678"
    echo "  Света: ec88e4ed-0405-43dd-aab9-030270f36741"
    echo "  СВЕТА планшет: e7ab22bb-2aa3-456e-8114-d3363733d77b"
    echo "  Afunts: 3d66bca5-f145-4cf1-9667-55e5e59ad464"
    echo "  Mixa: a675e293-df2c-4f24-b4cb-f9dbde0b4ee4"
    
    echo ""
    echo "=========================================="
    echo "IMPORTANT: Update client apps with new flow"
    echo "Set 'flow' = 'xtls-rprx-vision'"
    echo "=========================================="
}

#-------------------------------------------------------------------------------
# Main
#-------------------------------------------------------------------------------
main() {
    local mode="${1:-diagnose}"
    
    echo "=========================================="
    echo "S-GLOBAL DOMINION - VPN Diagnostic Tool"
    echo "Protocol: VERSHINA v200.11"
    echo "Mode: $mode"
    echo "=========================================="
    
    case "$mode" in
        diagnose)
            diagnose
            ;;
        fix)
            fix_config
            restart_services
            generate_client_configs
            ;;
        full)
            diagnose
            fix_config
            restart_services
            generate_client_configs
            ;;
        *)
            echo "Usage: $0 [diagnose|fix|full]"
            echo "  diagnose - Run diagnostics only"
            echo "  fix      - Apply fixes and restart"
            echo "  full     - Full diagnostic and fix"
            exit 1
            ;;
    esac
    
    log "${GREEN}Done!${NC}"
}

main "$@"
