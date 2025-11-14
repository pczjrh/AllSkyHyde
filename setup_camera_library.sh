#!/bin/bash

################################################################################
# Setup ZWO Camera Library
#
# This script automatically finds and symlinks the ZWO ASI camera library
# to the expected location (/usr/local/lib/libASICamera2.so)
#
# Usage: sudo ./setup_camera_library.sh
################################################################################

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SERVICE_USER="${SUDO_USER:-kickpi}"

echo "========================================================================"
echo "ZWO Camera Library Setup"
echo "========================================================================"
echo ""

# Check root
if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}ERROR: Must run as root (use sudo)${NC}"
    exit 1
fi

# Search for library
echo -e "${BLUE}Searching for libASICamera2.so...${NC}"
echo ""

LIBRARY_FOUND=""

# Check common locations first
echo "Checking common locations..."
for path in \
    "/usr/local/lib/libASICamera2.so" \
    "/usr/lib/libASICamera2.so" \
    "/usr/lib/x86_64-linux-gnu/libASICamera2.so" \
    "/usr/lib/arm-linux-gnueabihf/libASICamera2.so" \
    "/usr/lib/aarch64-linux-gnu/libASICamera2.so" \
    "/opt/zwo/lib/libASICamera2.so" \
    "/home/${SERVICE_USER}/libASICamera2.so"; do
    echo "  Checking: $path"
    if [ -f "$path" ]; then
        LIBRARY_FOUND="$path"
        echo -e "  ${GREEN}✓ Found!${NC}"
        break
    fi
done

# Search user home directory
if [ -z "$LIBRARY_FOUND" ]; then
    echo ""
    echo "Searching home directory (this may take a moment)..."
    LIBRARY_FOUND=$(find /home/${SERVICE_USER} -name "libASICamera2.so" 2>/dev/null | head -1)
fi

# Results
echo ""
echo "========================================================================"
if [ -n "$LIBRARY_FOUND" ]; then
    echo -e "${GREEN}✓ Library Found!${NC}"
    echo ""
    echo "Location: $LIBRARY_FOUND"
    echo ""

    # Check if already in correct location
    if [ "$LIBRARY_FOUND" = "/usr/local/lib/libASICamera2.so" ]; then
        echo -e "${GREEN}✓ Already in correct location${NC}"
    else
        echo "Creating symlink at /usr/local/lib/libASICamera2.so"
        ln -sf "$LIBRARY_FOUND" /usr/local/lib/libASICamera2.so

        # Update library cache
        echo "Updating library cache..."
        ldconfig 2>/dev/null || true

        echo -e "${GREEN}✓ Symlink created successfully${NC}"
    fi

    echo ""
    echo "Verification:"
    ls -l /usr/local/lib/libASICamera2.so
    echo ""

    # Test if it loads
    if python3 -c "import ctypes; ctypes.CDLL('/usr/local/lib/libASICamera2.so')" 2>/dev/null; then
        echo -e "${GREEN}✓ Library loads successfully in Python${NC}"
    else
        echo -e "${YELLOW}⚠ Library found but may have issues loading${NC}"
    fi

else
    echo -e "${RED}✗ Library Not Found${NC}"
    echo ""
    echo "The ZWO camera library (libASICamera2.so) was not found."
    echo ""
    echo "To install it:"
    echo "  1. Download the ZWO ASI SDK from:"
    echo "     https://astronomy-imaging-camera.com/software-drivers"
    echo ""
    echo "  2. Extract the SDK:"
    echo "     tar -xjf ASI_linux_mac_SDK_*.tar.bz2"
    echo ""
    echo "  3. Copy the library (choose your architecture):"
    echo "     For ARM (Raspberry Pi):"
    echo "       sudo cp ASI_linux_mac_SDK_*/lib/armv7/libASICamera2.so /usr/local/lib/"
    echo "     For x86_64:"
    echo "       sudo cp ASI_linux_mac_SDK_*/lib/x64/libASICamera2.so /usr/local/lib/"
    echo ""
    echo "  4. Run this script again"
    echo ""
fi

echo "========================================================================"
