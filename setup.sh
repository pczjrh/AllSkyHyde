#!/bin/bash

################################################################################
# AllSkyHyde Master Setup Script
#
# This single script does EVERYTHING:
# - Fixes any permission issues
# - Detects fresh install vs update
# - Installs/updates the application
# - Sets up virtual environment
# - Configures and starts the service
#
# Just run: sudo ./setup.sh
#
# That's it!
################################################################################

set -e  # Exit on error

################################################################################
# Configuration
################################################################################

APP_NAME="allskyhyde"
INSTALL_DIR="/opt/allskyhyde"
SERVICE_NAME="allskyhyde"
SERVICE_USER="${SUDO_USER:-$USER}"
LOG_DIR="/var/log/allskyhyde"
IMAGE_DIR="/home/${SERVICE_USER}/allsky_images"
VENV_DIR="${INSTALL_DIR}/venv"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
IS_UPDATE=false

################################################################################
# Colors
################################################################################

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

################################################################################
# Helper Functions
################################################################################

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo ""
    echo "========================================================================"
    echo -e "${GREEN}$1${NC}"
    echo "========================================================================"
    echo ""
}

################################################################################
# Step 0: Pre-Flight Checks and Fixes
################################################################################

preflight_checks() {
    print_header "Step 0: Pre-Flight Checks"

    # Check if running as root
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root (use sudo)"
        exit 1
    fi

    # Detect update vs fresh install
    if [ -d "${INSTALL_DIR}" ] && [ -f "${INSTALL_DIR}/flask_app.py" ]; then
        print_warning "Existing installation detected"
        IS_UPDATE=true
    else
        print_info "Fresh installation"
        IS_UPDATE=false
    fi

    # Stop service if running
    if systemctl is-active --quiet "${SERVICE_NAME}" 2>/dev/null; then
        print_info "Stopping ${SERVICE_NAME} service..."
        systemctl stop "${SERVICE_NAME}"
    fi

    # Fix permissions if directory exists
    if [ -d "${INSTALL_DIR}" ]; then
        print_info "Fixing permissions on ${INSTALL_DIR}..."
        chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}" || true
        chmod -R 755 "${INSTALL_DIR}" || true

        # Remove old venv completely
        if [ -d "${VENV_DIR}" ]; then
            print_info "Removing old virtual environment..."
            rm -rf "${VENV_DIR}"
        fi
    fi

    # Fix log directory permissions
    if [ -d "${LOG_DIR}" ]; then
        chown -R "${SERVICE_USER}:${SERVICE_USER}" "${LOG_DIR}" || true
        chmod 755 "${LOG_DIR}" || true
    fi

    print_success "Pre-flight checks complete"
}

################################################################################
# Step 1: Install Prerequisites
################################################################################

install_prerequisites() {
    print_header "Step 1: Installing Prerequisites"

    # Check for Python 3
    if ! command -v python3 &> /dev/null; then
        print_info "Installing Python 3..."
        apt-get update
        apt-get install -y python3 python3-pip python3-venv
    else
        print_success "Python 3 is installed: $(python3 --version)"
    fi

    # Check for pip
    if ! command -v pip3 &> /dev/null; then
        print_info "Installing pip..."
        apt-get install -y python3-pip
    fi

    # Install system dependencies
    print_info "Installing system dependencies..."
    apt-get update -qq
    apt-get install -y libjpeg-dev zlib1g-dev sudo -qq

    print_success "Prerequisites installed"
}

################################################################################
# Step 2: Create Directories
################################################################################

create_directories() {
    print_header "Step 2: Creating Directories"

    # Create and set ownership/permissions in one go
    for dir in "${INSTALL_DIR}" "${LOG_DIR}" "${IMAGE_DIR}"; do
        if [ ! -d "$dir" ]; then
            print_info "Creating $dir"
            mkdir -p "$dir"
        fi
        chown "${SERVICE_USER}:${SERVICE_USER}" "$dir"
        chmod 755 "$dir"
    done

    print_success "Directories ready"
}

################################################################################
# Step 3: Copy Application Files
################################################################################

copy_files() {
    print_header "Step 3: Copying Application Files"

    # Backup config if updating
    if [ "$IS_UPDATE" = true ] && [ -f "${INSTALL_DIR}/app_config.json" ]; then
        print_info "Backing up configuration..."
        cp "${INSTALL_DIR}/app_config.json" "/tmp/app_config.json.backup"
    fi

    # Copy files
    print_info "Copying files from ${SCRIPT_DIR}..."
    cp "${SCRIPT_DIR}"/flask_app.py "${INSTALL_DIR}/" 2>/dev/null || true
    cp "${SCRIPT_DIR}"/image_capture.py "${INSTALL_DIR}/" 2>/dev/null || true
    cp "${SCRIPT_DIR}"/loop1.py "${INSTALL_DIR}/" 2>/dev/null || true
    cp "${SCRIPT_DIR}"/requirements.txt "${INSTALL_DIR}/" 2>/dev/null || true

    # Copy directories
    if [ -d "${SCRIPT_DIR}/templates" ]; then
        cp -r "${SCRIPT_DIR}/templates" "${INSTALL_DIR}/"
    fi
    if [ -d "${SCRIPT_DIR}/static" ]; then
        cp -r "${SCRIPT_DIR}/static" "${INSTALL_DIR}/"
    fi

    # Restore config
    if [ "$IS_UPDATE" = true ] && [ -f "/tmp/app_config.json.backup" ]; then
        print_info "Restoring configuration..."
        mv "/tmp/app_config.json.backup" "${INSTALL_DIR}/app_config.json"
    fi

    # Fix ownership
    chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"

    print_success "Files copied"
}

################################################################################
# Step 4: Create Virtual Environment
################################################################################

create_venv() {
    print_header "Step 4: Creating Virtual Environment"

    # Ensure directory ownership is correct
    chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"

    print_info "Creating virtual environment..."
    sudo -u "${SERVICE_USER}" python3 -m venv "${VENV_DIR}"

    print_info "Upgrading pip..."
    sudo -u "${SERVICE_USER}" bash -c "source ${VENV_DIR}/bin/activate && pip install --upgrade pip -q"

    print_info "Installing dependencies..."
    if [ -f "${INSTALL_DIR}/requirements.txt" ]; then
        sudo -u "${SERVICE_USER}" bash -c "source ${VENV_DIR}/bin/activate && pip install -r ${INSTALL_DIR}/requirements.txt -q"
    else
        sudo -u "${SERVICE_USER}" bash -c "source ${VENV_DIR}/bin/activate && pip install flask numpy pillow psutil zwoasi gunicorn requests -q"
    fi

    # Verify
    if sudo -u "${SERVICE_USER}" bash -c "source ${VENV_DIR}/bin/activate && python -c 'import flask, requests, gunicorn' 2>/dev/null"; then
        print_success "Virtual environment ready (Flask, requests, gunicorn verified)"
    else
        print_error "Failed to verify modules"
        exit 1
    fi
}

################################################################################
# Step 5: Configure Application
################################################################################

configure_app() {
    print_header "Step 5: Configuring Application"

    # Update paths in flask_app.py
    sed -i "/^IMAGE_DIR = /c\\IMAGE_DIR = \"${IMAGE_DIR}\"" "${INSTALL_DIR}/flask_app.py" 2>/dev/null || true
    sed -i "/^SCRIPT_PATH = /c\\SCRIPT_PATH = \"${INSTALL_DIR}/image_capture.py\"" "${INSTALL_DIR}/flask_app.py" 2>/dev/null || true

    # Update paths in image_capture.py
    sed -i "/^OUTPUT_DIR = /c\\OUTPUT_DIR = \"${IMAGE_DIR}\"" "${INSTALL_DIR}/image_capture.py" 2>/dev/null || true

    # Fix filename pattern
    sed -i 's|image_pattern = os.path.join(IMAGE_DIR, "zwo_optimal_\*.png")|image_pattern = os.path.join(IMAGE_DIR, "*_exp*ms.png")|g' "${INSTALL_DIR}/flask_app.py" 2>/dev/null || true

    print_success "Application configured"
}

################################################################################
# Step 6: Configure Sudo Permissions (Fresh Install Only)
################################################################################

configure_sudo() {
    if [ "$IS_UPDATE" = true ]; then
        return
    fi

    print_header "Step 6: Configuring Sudo Permissions"

    SUDOERS_FILE="/etc/sudoers.d/${APP_NAME}"
    cat > "${SUDOERS_FILE}" << EOF
# Allow ${SERVICE_USER} to restart and shutdown without password
${SERVICE_USER} ALL=(ALL) NOPASSWD: /sbin/reboot
${SERVICE_USER} ALL=(ALL) NOPASSWD: /sbin/poweroff
${SERVICE_USER} ALL=(ALL) NOPASSWD: /usr/sbin/reboot
${SERVICE_USER} ALL=(ALL) NOPASSWD: /usr/sbin/poweroff
EOF

    chmod 0440 "${SUDOERS_FILE}"

    if visudo -c -f "${SUDOERS_FILE}" &> /dev/null; then
        print_success "Sudo permissions configured"
    else
        print_warning "Sudo configuration failed (non-critical)"
        rm "${SUDOERS_FILE}" 2>/dev/null || true
    fi
}

################################################################################
# Step 7: Create Systemd Service
################################################################################

create_service() {
    print_header "Step 7: Creating Systemd Service"

    SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

    cat > "${SERVICE_FILE}" << EOF
[Unit]
Description=HydeHome-AllSky Camera Web Application
After=network.target

[Service]
Type=notify
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
Environment="PATH=${VENV_DIR}/bin"
ExecStart=${VENV_DIR}/bin/gunicorn \\
    --bind 0.0.0.0:5000 \\
    --workers 2 \\
    --timeout 120 \\
    --access-logfile ${LOG_DIR}/access.log \\
    --error-logfile ${LOG_DIR}/error.log \\
    flask_app:app

Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    print_success "Service file created"
}

################################################################################
# Step 8: Start Service
################################################################################

start_service() {
    print_header "Step 8: Starting Service"

    systemctl daemon-reload
    systemctl enable "${SERVICE_NAME}"
    systemctl start "${SERVICE_NAME}"

    sleep 3

    if systemctl is-active --quiet "${SERVICE_NAME}"; then
        print_success "Service started successfully"
    else
        print_error "Service failed to start"
        journalctl -u "${SERVICE_NAME}" -n 30 --no-pager
        exit 1
    fi
}

################################################################################
# Step 9: Summary
################################################################################

print_summary() {
    print_header "Installation Complete!"

    if [ "$IS_UPDATE" = true ]; then
        echo -e "${GREEN}✓ AllSkyHyde has been successfully UPDATED!${NC}"
    else
        echo -e "${GREEN}✓ AllSkyHyde has been successfully INSTALLED!${NC}"
    fi

    echo ""
    echo "Installation Summary:"
    echo "  • Directory:    ${INSTALL_DIR}"
    echo "  • Virtual Env:  ${VENV_DIR}"
    echo "  • Images:       ${IMAGE_DIR}"
    echo "  • Logs:         ${LOG_DIR}"
    echo "  • Service:      ${SERVICE_NAME}"
    echo "  • User:         ${SERVICE_USER}"
    echo ""
    echo "Web Interface:"
    echo "  → http://$(hostname -I | awk '{print $1}'):5000"
    echo ""
    echo "Useful Commands:"
    echo "  • Status:   sudo systemctl status ${SERVICE_NAME}"
    echo "  • Logs:     sudo journalctl -u ${SERVICE_NAME} -f"
    echo "  • Restart:  sudo systemctl restart ${SERVICE_NAME}"
    echo ""

    if [ "$IS_UPDATE" = false ]; then
        echo "Next Steps:"
        echo "  1. Open web interface in browser"
        echo "  2. Go to Control Panel"
        echo "  3. Configure location (latitude, longitude, timezone)"
        echo "  4. Add OpenWeather API key"
        echo "  5. Save settings"
        echo ""
    fi
}

################################################################################
# Main Execution
################################################################################

main() {
    clear
    print_header "AllSkyHyde Master Setup Script"

    echo "This script will handle everything automatically:"
    echo "  ✓ Fix any permission issues"
    echo "  ✓ Install prerequisites"
    echo "  ✓ Create virtual environment"
    echo "  ✓ Install all dependencies (Flask, requests, etc.)"
    echo "  ✓ Configure and start the service"
    echo ""
    echo "Installation directory: ${INSTALL_DIR}"
    echo "Service user: ${SERVICE_USER}"
    echo ""

    read -p "Press ENTER to continue or Ctrl+C to cancel..."
    echo ""

    # Run all steps
    preflight_checks
    install_prerequisites
    create_directories
    copy_files
    create_venv
    configure_app
    configure_sudo
    create_service
    start_service
    print_summary

    echo -e "${GREEN}✓ All done!${NC}"
    echo ""
}

# Run main
main "$@"
