#!/bin/bash

#############################################################################
# Fix Hardcoded Paths Script
#
# This script updates app_config.json to use correct paths based on the
# current installation directory.
#############################################################################

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

echo ""
log_info "Fix Hardcoded Paths Script"
echo ""

# Get current directory
APP_DIR="$(pwd)"
CONFIG_FILE="${APP_DIR}/app_config.json"
IMAGE_DIR="${HOME}/allsky_images"
SCRIPT_PATH="${APP_DIR}/image_capture.py"

log_info "Current directory: ${APP_DIR}"

# Check if flask_app.py exists
if [ ! -f "${APP_DIR}/flask_app.py" ]; then
    log_error "flask_app.py not found in current directory!"
    log_error "Please run this script from the AllSkyHyde directory."
    exit 1
fi

# Check if config file exists
if [ ! -f "$CONFIG_FILE" ]; then
    log_warning "Configuration file not found: $CONFIG_FILE"
    log_info "Creating new configuration file..."

    cat > "$CONFIG_FILE" <<EOF
{
    "settings": {
        "latitude": null,
        "longitude": null,
        "timezone": null,
        "dst_enabled": false,
        "openweather_api_key": null
    },
    "capture_interval": 300,
    "background_capture_enabled": false,
    "image_dir": "${IMAGE_DIR}",
    "script_path": "${SCRIPT_PATH}",
    "last_updated": "$(date '+%Y-%m-%d %H:%M:%S')"
}
EOF
    log_success "Configuration file created."
    exit 0
fi

# Show current paths in config
log_info "Reading current configuration..."

CURRENT_IMAGE_DIR=$(python3 -c "import json; f=open('${CONFIG_FILE}'); c=json.load(f); print(c.get('image_dir', 'Not set'))")
CURRENT_SCRIPT_PATH=$(python3 -c "import json; f=open('${CONFIG_FILE}'); c=json.load(f); print(c.get('script_path', 'Not set'))")

echo ""
log_info "Current paths in configuration:"
echo "  Image directory: ${YELLOW}${CURRENT_IMAGE_DIR}${NC}"
echo "  Script path:     ${YELLOW}${CURRENT_SCRIPT_PATH}${NC}"
echo ""

log_info "New paths will be:"
echo "  Image directory: ${GREEN}${IMAGE_DIR}${NC}"
echo "  Script path:     ${GREEN}${SCRIPT_PATH}${NC}"
echo ""

# Ask for confirmation
read -p "Update configuration file with these paths? (y/n): " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log_info "Operation cancelled."
    exit 0
fi

# Backup existing config
log_info "Creating backup..."
cp "$CONFIG_FILE" "${CONFIG_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
log_success "Backup created: ${CONFIG_FILE}.backup.$(date +%Y%m%d_%H%M%S)"

# Update the configuration
log_info "Updating configuration file..."

python3 -c "
import json
import sys

config_file = '${CONFIG_FILE}'
try:
    with open(config_file, 'r') as f:
        config = json.load(f)

    # Update paths
    config['image_dir'] = '${IMAGE_DIR}'
    config['script_path'] = '${SCRIPT_PATH}'
    config['last_updated'] = '$(date '+%Y-%m-%d %H:%M:%S')'

    with open(config_file, 'w') as f:
        json.dump(config, f, indent=4)

    print('Configuration updated successfully')
except Exception as e:
    print(f'Error updating config: {e}', file=sys.stderr)
    sys.exit(1)
"

if [ $? -eq 0 ]; then
    log_success "Configuration file updated successfully!"
    echo ""
    log_info "Updated paths:"
    echo "  Image directory: ${GREEN}${IMAGE_DIR}${NC}"
    echo "  Script path:     ${GREEN}${SCRIPT_PATH}${NC}"
    echo ""

    # Create image directory if it doesn't exist
    if [ ! -d "$IMAGE_DIR" ]; then
        log_info "Creating image directory: $IMAGE_DIR"
        mkdir -p "$IMAGE_DIR"
        log_success "Image directory created."
    fi

    # Check if service is running
    if systemctl list-unit-files | grep -q "^allskyhyde.service"; then
        echo ""
        log_info "AllSkyHyde service detected. You should restart it:"
        echo "  ${GREEN}sudo systemctl restart allskyhyde${NC}"
        echo ""
    fi
else
    log_error "Failed to update configuration file!"
    log_info "Restoring from backup..."
    cp "${CONFIG_FILE}.backup.$(date +%Y%m%d_%H%M%S)" "$CONFIG_FILE" 2>/dev/null || true
    exit 1
fi
