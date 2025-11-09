#!/bin/bash

################################################################################
# Quick Permission Fix Script
#
# Run this if you get permission errors during installation
# Usage: sudo ./fix_permissions.sh
################################################################################

# Configuration
INSTALL_DIR="/opt/allskyhyde"
SERVICE_USER="${SUDO_USER:-kickpi}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

echo "========================================================================"
echo "Fixing Permissions for AllSkyHyde"
echo "========================================================================"
echo ""

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}ERROR: This script must be run as root (use sudo)${NC}"
    exit 1
fi

echo "Installation directory: ${INSTALL_DIR}"
echo "Service user: ${SERVICE_USER}"
echo ""

# Stop service if running
if systemctl is-active --quiet allskyhyde 2>/dev/null; then
    echo "Stopping allskyhyde service..."
    systemctl stop allskyhyde
fi

# Fix ownership and permissions
echo "Fixing ownership of ${INSTALL_DIR}..."
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"

echo "Setting directory permissions..."
find "${INSTALL_DIR}" -type d -exec chmod 755 {} \;

echo "Setting file permissions..."
find "${INSTALL_DIR}" -type f -exec chmod 644 {} \;

# Make scripts executable
if [ -f "${INSTALL_DIR}/image_capture.py" ]; then
    chmod 755 "${INSTALL_DIR}/image_capture.py"
fi
if [ -f "${INSTALL_DIR}/loop1.py" ]; then
    chmod 755 "${INSTALL_DIR}/loop1.py"
fi

# Remove venv if it exists
if [ -d "${INSTALL_DIR}/venv" ]; then
    echo "Removing old virtual environment..."
    rm -rf "${INSTALL_DIR}/venv"
fi

# Fix log directory
if [ -d "/var/log/allskyhyde" ]; then
    echo "Fixing log directory permissions..."
    chown -R "${SERVICE_USER}:${SERVICE_USER}" "/var/log/allskyhyde"
    chmod 755 "/var/log/allskyhyde"
fi

echo ""
echo -e "${GREEN}✓ Permissions fixed successfully!${NC}"
echo ""
echo "You can now run: sudo ./install.sh"
echo ""
