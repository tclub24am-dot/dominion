#!/bin/bash

#===============================================================================
# S-GLOBAL DOMINION Empire
# Xray & X-UI Maintenance Script
# Protocol: VERSHINA v200.11
# 
# Description:
#   - Clears Xray logs weekly
#   - Checks x-ui service status
#   - Restarts x-ui if service is down
#
# Installation:
#   chmod +x /root/dominion/scripts/xray_maintenance.sh
#   crontab -e
#   Add: 0 3 * * 0 /root/dominion/scripts/xray_maintenance.sh >> /var/log/xray_maintenance.log 2>&1
#
# Author: Master Spartak AI Architect
#===============================================================================

set -e

# Configuration
LOG_FILE="/var/log/xray_maintenance.log"
XRAY_LOG_DIR="/var/log/xray"
XRAY_ACCESS_LOG="${XRAY_LOG_DIR}/access.log"
XRAY_ERROR_LOG="${XRAY_LOG_DIR}/error.log"
X_UI_SERVICE="x-ui"
MAX_LOG_SIZE_MB=100
RETENTION_DAYS=7

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

#-------------------------------------------------------------------------------
# Logging function
#-------------------------------------------------------------------------------
log() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[${timestamp}] [${level}] ${message}" | tee -a "$LOG_FILE"
}

#-------------------------------------------------------------------------------
# Create log directory if not exists
#-------------------------------------------------------------------------------
ensure_log_dir() {
    if [ ! -d "$(dirname "$LOG_FILE")" ]; then
        mkdir -p "$(dirname "$LOG_FILE")"
    fi
}

#-------------------------------------------------------------------------------
# Clear Xray logs
#-------------------------------------------------------------------------------
clear_xray_logs() {
    log "INFO" "Starting Xray log cleanup..."
    
    # Check if Xray log directory exists
    if [ ! -d "$XRAY_LOG_DIR" ]; then
        log "WARN" "Xray log directory not found: ${XRAY_LOG_DIR}"
        return 0
    fi
    
    local cleared_files=0
    local freed_space=0
    
    # Find and clear old log files
    for log_file in "$XRAY_LOG_DIR"/*.log; do
        if [ -f "$log_file" ]; then
            local file_size=$(stat -c%s "$log_file" 2>/dev/null || echo 0)
            local file_size_mb=$((file_size / 1024 / 1024))
            
            # Truncate log file (keep structure, remove content)
            > "$log_file"
            
            cleared_files=$((cleared_files + 1))
            freed_space=$((freed_space + file_size_mb))
            
            log "INFO" "Cleared: ${log_file} (${file_size_mb}MB)"
        fi
    done
    
    # Remove archived/rotated logs older than retention period
    if [ -d "${XRAY_LOG_DIR}" ]; then
        local old_files=$(find "${XRAY_LOG_DIR}" -name "*.log.*" -mtime +${RETENTION_DAYS} 2>/dev/null | wc -l)
        if [ "$old_files" -gt 0 ]; then
            find "${XRAY_LOG_DIR}" -name "*.log.*" -mtime +${RETENTION_DAYS} -delete 2>/dev/null
            log "INFO" "Removed ${old_files} old archived log files"
        fi
    fi
    
    # Also check common Xray log locations
    for alt_log in "/var/log/xray.log" "/var/log/xray-access.log" "/var/log/xray-error.log"; do
        if [ -f "$alt_log" ]; then
            > "$alt_log"
            log "INFO" "Cleared alternative log: ${alt_log}"
        fi
    done
    
    log "SUCCESS" "Xray logs cleared: ${cleared_files} files, ~${freed_space}MB freed"
}

#-------------------------------------------------------------------------------
# Check and restart x-ui service
#-------------------------------------------------------------------------------
check_xui_service() {
    log "INFO" "Checking x-ui service status..."
    
    # Check if systemd is available
    if ! command -v systemctl &> /dev/null; then
        log "ERROR" "systemctl not found - cannot manage services"
        return 1
    fi
    
    # Check if x-ui service exists
    if ! systemctl list-unit-files "${X_UI_SERVICE}.service" &> /dev/null; then
        # Try alternative service names
        for alt_service in "x-ui" "xui" "xray-ui"; do
            if systemctl list-unit-files "${alt_service}.service" &> /dev/null 2>&1; then
                X_UI_SERVICE="$alt_service"
                log "INFO" "Found alternative service name: ${alt_service}"
                break
            fi
        done
    fi
    
    # Get service status
    local is_active=false
    if systemctl is-active --quiet "${X_UI_SERVICE}" 2>/dev/null; then
        is_active=true
    fi
    
    if [ "$is_active" = true ]; then
        log "SUCCESS" "x-ui service is running"
        
        # Additional health check - verify service is responding
        local service_pid=$(systemctl show --property MainPID --value "${X_UI_SERVICE}" 2>/dev/null)
        if [ -n "$service_pid" ] && [ "$service_pid" -gt 0 ]; then
            log "INFO" "x-ui PID: ${service_pid}"
        fi
    else
        log "WARN" "x-ui service is NOT running! Attempting restart..."
        
        # Try to restart the service
        systemctl restart "${X_UI_SERVICE}" 2>&1 | tee -a "$LOG_FILE"
        local restart_status=$?
        
        sleep 3  # Wait for service to start
        
        if systemctl is-active --quiet "${X_UI_SERVICE}" 2>/dev/null; then
            log "SUCCESS" "x-ui service restarted successfully!"
            
            # Optional: Send notification (can be configured)
            # send_notification "x-ui Restarted" "Service was down and has been restarted."
        else
            log "ERROR" "Failed to restart x-ui service! Exit code: ${restart_status}"
            
            # Try to get more details
            log "INFO" "Service status details:"
            systemctl status "${X_UI_SERVICE}" --no-pager 2>&1 | tee -a "$LOG_FILE"
            
            # Check for common issues
            if systemctl is-enabled --quiet "${X_UI_SERVICE}" 2>/dev/null; then
                log "INFO" "Service is enabled for auto-start"
            else
                log "WARN" "Service is NOT enabled for auto-start"
            fi
            
            return 1
        fi
    fi
    
    return 0
}

#-------------------------------------------------------------------------------
# Check system resources
#-------------------------------------------------------------------------------
check_system_resources() {
    log "INFO" "Checking system resources..."
    
    # Disk usage for log partition
    local log_disk_usage=$(df -h /var/log 2>/dev/null | awk 'NR==2 {print $5}' | tr -d '%')
    if [ -n "$log_disk_usage" ] && [ "$log_disk_usage" -gt 80 ]; then
        log "WARN" "High disk usage on /var/log: ${log_disk_usage}%"
    fi
    
    # Memory usage
    local mem_usage=$(free | awk '/Mem:/ {printf "%.0f", $3/$2 * 100}')
    if [ "$mem_usage" -gt 90 ]; then
        log "WARN" "High memory usage: ${mem_usage}%"
    fi
    
    # Xray process check
    if pgrep -x "xray" > /dev/null; then
        local xray_count=$(pgrep -x "xray" | wc -l)
        log "INFO" "Xray processes running: ${xray_count}"
    else
        log "WARN" "No Xray process found running"
    fi
}

#-------------------------------------------------------------------------------
# Optional: Send notification (Telegram/Email)
#-------------------------------------------------------------------------------
send_notification() {
    local title="$1"
    local message="$2"
    
    # Placeholder for notification system
    # Can be integrated with Telegram bot or email
    
    # Example Telegram notification (uncomment and configure):
    # local BOT_TOKEN="YOUR_BOT_TOKEN"
    # local CHAT_ID="YOUR_CHAT_ID"
    # curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
    #     -d chat_id="${CHAT_ID}" \
    #     -d text="<b>${title}</b>%0A${message}" \
    #     -d parse_mode="HTML" > /dev/null
    
    log "INFO" "Notification: ${title} - ${message}"
}

#-------------------------------------------------------------------------------
# Main execution
#-------------------------------------------------------------------------------
main() {
    ensure_log_dir
    
    log "INFO" "========================================"
    log "INFO" "S-GLOBAL DOMINION - Xray Maintenance"
    log "INFO" "Protocol: VERSHINA v200.11"
    log "INFO" "========================================"
    
    # Step 1: Clear Xray logs
    clear_xray_logs
    echo ""
    
    # Step 2: Check system resources
    check_system_resources
    echo ""
    
    # Step 3: Check and restart x-ui if needed
    check_xui_service
    local service_status=$?
    echo ""
    
    # Summary
    log "INFO" "========================================"
    log "INFO" "Maintenance completed"
    if [ $service_status -eq 0 ]; then
        log "SUCCESS" "All systems operational"
    else
        log "WARN" "Some issues detected - check logs above"
    fi
    log "INFO" "========================================"
    
    return $service_status
}

# Run main function
main "$@"