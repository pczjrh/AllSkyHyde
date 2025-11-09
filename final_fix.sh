#!/bin/bash

################################################################################
# AllSkyHyde Final Fix Script
#
# This script ensures all fixes are properly applied:
# - Updates flask_app.py with all fixes
# - Ensures config file path is correct
# - Verifies requests module
# - Restarts service
# - Tests that settings work
#
# Usage: sudo ./final_fix.sh
################################################################################

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

INSTALL_DIR="/opt/allskyhyde"
SERVICE_USER="${SUDO_USER:-kickpi}"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "========================================================================"
echo "AllSkyHyde Final Fix"
echo "========================================================================"
echo ""

# Check root
if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}ERROR: Must run as root (use sudo)${NC}"
    exit 1
fi

# Stop service
echo -e "${BLUE}[1/7]${NC} Stopping service..."
systemctl stop allskyhyde 2>/dev/null || true

# Copy updated flask_app.py
echo -e "${BLUE}[2/7]${NC} Updating flask_app.py..."
if [ -f "${SCRIPT_DIR}/flask_app.py" ]; then
    cp "${SCRIPT_DIR}/flask_app.py" "${INSTALL_DIR}/"
    chown "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}/flask_app.py"
    echo -e "${GREEN}✓ flask_app.py updated${NC}"
else
    echo -e "${RED}✗ flask_app.py not found in ${SCRIPT_DIR}${NC}"
    exit 1
fi

# Verify critical settings in flask_app.py
echo -e "${BLUE}[3/7]${NC} Verifying flask_app.py settings..."

# Check CONFIG_FILE
if grep -q "CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), \"app_config.json\")" "${INSTALL_DIR}/flask_app.py"; then
    echo -e "${GREEN}✓ CONFIG_FILE uses absolute path${NC}"
else
    echo -e "${RED}✗ CONFIG_FILE setting incorrect${NC}"
    exit 1
fi

# Check background_capture_enabled
if grep -q "background_capture_enabled = False" "${INSTALL_DIR}/flask_app.py"; then
    echo -e "${GREEN}✓ background_capture_enabled variable present${NC}"
else
    echo -e "${RED}✗ background_capture_enabled variable missing${NC}"
    exit 1
fi

# Check REQUESTS_AVAILABLE
if grep -q "REQUESTS_AVAILABLE = True" "${INSTALL_DIR}/flask_app.py"; then
    echo -e "${GREEN}✓ REQUESTS_AVAILABLE variable present${NC}"
else
    echo -e "${RED}✗ REQUESTS_AVAILABLE variable missing${NC}"
    exit 1
fi

# Verify requests module is installed
echo -e "${BLUE}[4/7]${NC} Verifying requests module..."
if sudo -u "${SERVICE_USER}" bash -c "source ${INSTALL_DIR}/venv/bin/activate && python -c 'import requests' 2>/dev/null"; then
    echo -e "${GREEN}✓ requests module installed${NC}"
else
    echo -e "${RED}✗ requests module NOT installed - installing now...${NC}"
    sudo -u "${SERVICE_USER}" bash -c "source ${INSTALL_DIR}/venv/bin/activate && pip install requests"
fi

# Ensure config directory is writable
echo -e "${BLUE}[5/7]${NC} Checking permissions..."
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"
chmod 755 "${INSTALL_DIR}"
if [ -f "${INSTALL_DIR}/app_config.json" ]; then
    chown "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}/app_config.json"
    chmod 644 "${INSTALL_DIR}/app_config.json"
    echo -e "${GREEN}✓ Permissions set${NC}"
    echo "   Current config:"
    cat "${INSTALL_DIR}/app_config.json"
else
    echo "   No existing config file (will be created on first save)"
fi

# Start service
echo -e "${BLUE}[6/7]${NC} Starting service..."
systemctl daemon-reload
systemctl start allskyhyde

sleep 3

if systemctl is-active --quiet allskyhyde; then
    echo -e "${GREEN}✓ Service started${NC}"
else
    echo -e "${RED}✗ Service failed to start${NC}"
    echo "Recent logs:"
    journalctl -u allskyhyde -n 20 --no-pager
    exit 1
fi

# Test the API
echo -e "${BLUE}[7/7]${NC} Testing settings API..."
sleep 2

RESPONSE=$(curl -s http://localhost:5000/api/settings 2>/dev/null || echo "FAILED")
if [ "$RESPONSE" != "FAILED" ]; then
    echo -e "${GREEN}✓ API is responding${NC}"
    echo "   Settings API response:"
    echo "   $RESPONSE" | python3 -m json.tool 2>/dev/null || echo "   $RESPONSE"
else
    echo -e "${RED}✗ API not responding${NC}"
fi

echo ""
echo "========================================================================"
echo -e "${GREEN}Fix Complete!${NC}"
echo "========================================================================"
echo ""
echo "Next steps:"
echo "  1. Open http://$(hostname -I | awk '{print $1}'):5000"
echo "  2. Go to Control Panel"
echo "  3. Enter settings and click Save"
echo "  4. Settings should now persist!"
echo ""
echo "To verify:"
echo "  • Check config: cat ${INSTALL_DIR}/app_config.json"
echo "  • View logs:    sudo journalctl -u allskyhyde -f"
echo ""
