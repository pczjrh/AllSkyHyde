#!/bin/bash

################################################################################
# AllSkyHyde Diagnostic Script
#
# This script checks the current state of the installation and reports issues
#
# Usage: sudo ./diagnose.sh
################################################################################

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

INSTALL_DIR="/opt/allskyhyde"
SERVICE_USER="${SUDO_USER:-kickpi}"

echo "========================================================================"
echo "AllSkyHyde Diagnostic Report"
echo "========================================================================"
echo ""

# Check service status
echo "1. Service Status:"
if systemctl is-active --quiet allskyhyde; then
    echo -e "   ${GREEN}✓ Service is running${NC}"
else
    echo -e "   ${RED}✗ Service is NOT running${NC}"
fi
echo ""

# Check if config file exists and show its path
echo "2. Configuration File:"
if [ -f "${INSTALL_DIR}/app_config.json" ]; then
    echo -e "   ${GREEN}✓ Config file exists: ${INSTALL_DIR}/app_config.json${NC}"
    echo "   Contents:"
    cat "${INSTALL_DIR}/app_config.json" | head -20
else
    echo -e "   ${RED}✗ Config file NOT found at: ${INSTALL_DIR}/app_config.json${NC}"
fi
echo ""

# Check flask_app.py for CONFIG_FILE setting
echo "3. Flask App CONFIG_FILE Path:"
CONFIG_LINE=$(grep "^CONFIG_FILE = " "${INSTALL_DIR}/flask_app.py" 2>/dev/null || echo "NOT FOUND")
echo "   $CONFIG_LINE"
echo ""

# Check if REQUESTS_AVAILABLE is set
echo "4. Requests Module Check:"
REQUESTS_LINE=$(grep "^REQUESTS_AVAILABLE = " "${INSTALL_DIR}/flask_app.py" 2>/dev/null || echo "NOT FOUND")
echo "   $REQUESTS_LINE"
if /opt/allskyhyde/venv/bin/python3 -c "import requests" 2>/dev/null; then
    echo -e "   ${GREEN}✓ requests module is installed${NC}"
else
    echo -e "   ${RED}✗ requests module is NOT installed${NC}"
fi
echo ""

# Check background_capture_enabled variable
echo "5. Background Capture Variable:"
BG_CAPTURE_LINE=$(grep "^background_capture_enabled = " "${INSTALL_DIR}/flask_app.py" 2>/dev/null || echo "NOT FOUND")
echo "   $BG_CAPTURE_LINE"
echo ""

# Check file permissions
echo "6. File Permissions:"
echo "   ${INSTALL_DIR} ownership:"
ls -ld "${INSTALL_DIR}" | awk '{print "   User: "$3", Group: "$4", Permissions: "$1}'
if [ -f "${INSTALL_DIR}/app_config.json" ]; then
    echo "   app_config.json ownership:"
    ls -l "${INSTALL_DIR}/app_config.json" | awk '{print "   User: "$3", Group: "$4", Permissions: "$1}'
fi
echo ""

# Check recent logs
echo "7. Recent Service Logs (last 10 lines):"
journalctl -u allskyhyde -n 10 --no-pager 2>/dev/null | grep -v "^--" || echo "   No logs available"
echo ""

# Check if settings API is working
echo "8. Testing Settings API:"
RESPONSE=$(curl -s http://localhost:5000/api/settings 2>/dev/null || echo "FAILED")
if [ "$RESPONSE" != "FAILED" ]; then
    echo "   Response: $RESPONSE"
else
    echo -e "   ${RED}✗ API request failed${NC}"
fi
echo ""

echo "========================================================================"
echo "Diagnostic Complete"
echo "========================================================================"
