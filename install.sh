#!/bin/bash

################################################################################
# HydeHome-AllSky Installation Script
#
# This script installs or updates the HydeHome-AllSky application as a systemd
# service with Gunicorn WSGI server in a Python virtual environment.
#
# Features:
# - Detects existing installation and offers update option
# - Creates Python virtual environment
# - Installs all dependencies (Flask, requests, etc.)
# - Configures systemd service
# - Sets up proper permissions
#
# Usage: sudo ./install.sh
################################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Configuration variables
APP_NAME="allskyhyde"
INSTALL_DIR="/opt/allskyhyde"
SERVICE_NAME="allskyhyde"
SERVICE_USER="${SUDO_USER:-$USER}"
LOG_DIR="/var/log/allskyhyde"
IMAGE_DIR="/home/${SERVICE_USER}/allsky_images"
VENV_DIR="${INSTALL_DIR}/venv"
IS_UPDATE=false

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

check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

detect_existing_installation() {
    if [ -d "${INSTALL_DIR}" ] && [ -f "${INSTALL_DIR}/flask_app.py" ]; then
        print_warning "Existing installation detected at ${INSTALL_DIR}"
        echo ""
        echo "This appears to be an update. The script will:"
        echo "  - Preserve your existing configuration (app_config.json)"
        echo "  - Stop the service temporarily"
        echo "  - Update application files"
        echo "  - Recreate virtual environment with all dependencies"
        echo "  - Restart the service"
        echo ""
        IS_UPDATE=true
    fi
}

stop_service_if_running() {
    if systemctl is-active --quiet "${SERVICE_NAME}" 2>/dev/null; then
        print_info "Stopping ${SERVICE_NAME} service..."
        systemctl stop "${SERVICE_NAME}"
        print_success "Service stopped"
    fi
}

check_prerequisites() {
    print_header "Checking Prerequisites"

    # Check for Python 3
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is not installed"
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

    # Check for system dependencies
    print_info "Installing system dependencies..."
    apt-get update
    apt-get install -y libjpeg-dev zlib1g-dev sudo

    print_success "All prerequisites are satisfied"
}

create_directories() {
    print_header "Creating Directories"

    # Create installation directory
    print_info "Creating installation directory: ${INSTALL_DIR}"
    mkdir -p "${INSTALL_DIR}"
    chown "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"
    chmod 755 "${INSTALL_DIR}"

    # Create log directory
    print_info "Creating log directory: ${LOG_DIR}"
    mkdir -p "${LOG_DIR}"
    chown "${SERVICE_USER}:${SERVICE_USER}" "${LOG_DIR}"
    chmod 755 "${LOG_DIR}"

    # Create image storage directory
    print_info "Creating image storage directory: ${IMAGE_DIR}"
    mkdir -p "${IMAGE_DIR}"
    chown "${SERVICE_USER}:${SERVICE_USER}" "${IMAGE_DIR}"
    chmod 755 "${IMAGE_DIR}"

    print_success "Directories created successfully"
}

copy_application_files() {
    print_header "Copying Application Files"

    print_info "Copying files from ${SCRIPT_DIR} to ${INSTALL_DIR}"

    # Backup config file if updating
    if [ "$IS_UPDATE" = true ] && [ -f "${INSTALL_DIR}/app_config.json" ]; then
        print_info "Backing up existing configuration..."
        cp "${INSTALL_DIR}/app_config.json" "${INSTALL_DIR}/app_config.json.backup"
    fi

    # Copy Python files
    cp "${SCRIPT_DIR}/flask_app.py" "${INSTALL_DIR}/"
    cp "${SCRIPT_DIR}/image_capture.py" "${INSTALL_DIR}/"
    cp "${SCRIPT_DIR}/loop1.py" "${INSTALL_DIR}/"

    # Copy requirements.txt if it exists
    if [ -f "${SCRIPT_DIR}/requirements.txt" ]; then
        cp "${SCRIPT_DIR}/requirements.txt" "${INSTALL_DIR}/"
        print_success "Copied requirements.txt"
    fi

    # Copy directories
    cp -r "${SCRIPT_DIR}/templates" "${INSTALL_DIR}/"
    cp -r "${SCRIPT_DIR}/static" "${INSTALL_DIR}/"

    # Copy documentation
    if [ -f "${SCRIPT_DIR}/CLAUDE.md" ]; then
        cp "${SCRIPT_DIR}/CLAUDE.md" "${INSTALL_DIR}/"
    fi
    if [ -f "${SCRIPT_DIR}/INSTALLATION.md" ]; then
        cp "${SCRIPT_DIR}/INSTALLATION.md" "${INSTALL_DIR}/"
    fi
    if [ -f "${SCRIPT_DIR}/README.md" ]; then
        cp "${SCRIPT_DIR}/README.md" "${INSTALL_DIR}/"
    fi

    # Restore config file if it was backed up
    if [ "$IS_UPDATE" = true ] && [ -f "${INSTALL_DIR}/app_config.json.backup" ]; then
        print_info "Restoring configuration..."
        mv "${INSTALL_DIR}/app_config.json.backup" "${INSTALL_DIR}/app_config.json"
    fi

    # Set ownership (but don't overwrite venv if it exists)
    chown "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"/*.py 2>/dev/null || true
    chown "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"/*.txt 2>/dev/null || true
    chown "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"/*.json 2>/dev/null || true
    chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}/templates" 2>/dev/null || true
    chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}/static" 2>/dev/null || true

    print_success "Application files copied successfully"
}

create_virtual_environment() {
    print_header "Creating Python Virtual Environment"

    # Remove old venv if updating or if it exists with wrong permissions
    if [ -d "${VENV_DIR}" ]; then
        print_info "Removing old virtual environment..."
        rm -rf "${VENV_DIR}"
    fi

    # Ensure parent directory has correct ownership
    print_info "Setting directory permissions..."
    chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"
    chmod -R 755 "${INSTALL_DIR}"

    print_info "Creating virtual environment at ${VENV_DIR}"
    sudo -u "${SERVICE_USER}" python3 -m venv "${VENV_DIR}"

    print_info "Upgrading pip..."
    sudo -u "${SERVICE_USER}" bash -c "source ${VENV_DIR}/bin/activate && pip install --upgrade pip"

    # Check if requirements.txt exists
    if [ -f "${INSTALL_DIR}/requirements.txt" ]; then
        print_info "Installing dependencies from requirements.txt..."
        sudo -u "${SERVICE_USER}" bash -c "source ${VENV_DIR}/bin/activate && pip install -r ${INSTALL_DIR}/requirements.txt"
    else
        print_info "Installing dependencies manually..."
        sudo -u "${SERVICE_USER}" bash -c "source ${VENV_DIR}/bin/activate && pip install flask numpy pillow psutil zwoasi gunicorn requests"
    fi

    # Verify critical modules
    print_info "Verifying installation..."
    if sudo -u "${SERVICE_USER}" bash -c "source ${VENV_DIR}/bin/activate && python -c 'import flask, requests, gunicorn' 2>/dev/null"; then
        print_success "All critical modules verified (Flask, requests, gunicorn)"
    else
        print_error "Failed to verify some modules"
        exit 1
    fi

    print_success "Virtual environment created and dependencies installed"
}

configure_application() {
    print_header "Configuring Application"

    # Update paths in flask_app.py
    print_info "Updating paths in flask_app.py"

    # Use more specific sed patterns to match the exact lines
    sed -i "/^IMAGE_DIR = /c\\IMAGE_DIR = \"${IMAGE_DIR}\"" "${INSTALL_DIR}/flask_app.py"
    sed -i "/^SCRIPT_PATH = /c\\SCRIPT_PATH = \"${INSTALL_DIR}/image_capture.py\"" "${INSTALL_DIR}/flask_app.py"

    # Update paths in image_capture.py
    print_info "Updating paths in image_capture.py"
    sed -i "/^OUTPUT_DIR = /c\\OUTPUT_DIR = \"${IMAGE_DIR}\"" "${INSTALL_DIR}/image_capture.py"

    # Fix filename pattern in flask_app.py (CRITICAL FIX)
    print_info "Fixing filename pattern in flask_app.py"
    sed -i 's|image_pattern = os.path.join(IMAGE_DIR, "zwo_optimal_\*.png")|image_pattern = os.path.join(IMAGE_DIR, "*_exp*ms.png")|g' "${INSTALL_DIR}/flask_app.py"

    # Also update the comment if it exists
    sed -i 's|# Extract timestamp (format: zwo_optimal_YYYYMMDD_HHMMSS_expXXXms.png)|# Extract timestamp (format: YYYYMMDD_HHMMSS_expXXXms.png)|g' "${INSTALL_DIR}/flask_app.py"

    # Verify the changes
    print_info "Verifying configuration..."
    ACTUAL_IMAGE_DIR=$(grep "^IMAGE_DIR = " "${INSTALL_DIR}/flask_app.py" | cut -d'"' -f2)
    ACTUAL_SCRIPT_PATH=$(grep "^SCRIPT_PATH = " "${INSTALL_DIR}/flask_app.py" | cut -d'"' -f2)
    ACTUAL_OUTPUT_DIR=$(grep "^OUTPUT_DIR = " "${INSTALL_DIR}/image_capture.py" | cut -d'"' -f2)
    ACTUAL_PATTERN=$(grep "image_pattern = " "${INSTALL_DIR}/flask_app.py" | head -1)

    print_info "  IMAGE_DIR: ${ACTUAL_IMAGE_DIR}"
    print_info "  SCRIPT_PATH: ${ACTUAL_SCRIPT_PATH}"
    print_info "  OUTPUT_DIR: ${ACTUAL_OUTPUT_DIR}"
    print_info "  Filename pattern: ${ACTUAL_PATTERN}"

    # Validation
    if [ "${ACTUAL_IMAGE_DIR}" != "${IMAGE_DIR}" ]; then
        print_error "IMAGE_DIR configuration failed!"
        exit 1
    fi

    if ! echo "${ACTUAL_PATTERN}" | grep -q '\*_exp\*ms\.png'; then
        print_error "Filename pattern was not updated correctly!"
        print_error "Pattern should contain: *_exp*ms.png"
        print_error "Got: ${ACTUAL_PATTERN}"
        exit 1
    fi

    print_success "Application configured successfully"
}

configure_sudo_permissions() {
    print_header "Configuring Sudo Permissions"

    print_info "Setting up sudo permissions for system control..."

    SUDOERS_FILE="/etc/sudoers.d/${APP_NAME}"
    cat > "${SUDOERS_FILE}" << EOF
# Allow ${SERVICE_USER} to restart and shutdown without password
${SERVICE_USER} ALL=(ALL) NOPASSWD: /sbin/reboot
${SERVICE_USER} ALL=(ALL) NOPASSWD: /sbin/poweroff
${SERVICE_USER} ALL=(ALL) NOPASSWD: /usr/sbin/reboot
${SERVICE_USER} ALL=(ALL) NOPASSWD: /usr/sbin/poweroff
EOF

    chmod 0440 "${SUDOERS_FILE}"

    # Validate sudoers file
    if visudo -c -f "${SUDOERS_FILE}" &> /dev/null; then
        print_success "Sudo permissions configured successfully"
    else
        print_error "Failed to configure sudo permissions"
        rm "${SUDOERS_FILE}"
        exit 1
    fi
}

create_systemd_service() {
    print_header "Creating Systemd Service"

    SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

    print_info "Creating service file: ${SERVICE_FILE}"

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

    print_success "Systemd service file created"
}

enable_and_start_service() {
    print_header "Enabling and Starting Service"

    # Reload systemd
    print_info "Reloading systemd daemon..."
    systemctl daemon-reload

    # Enable service
    print_info "Enabling ${SERVICE_NAME} service to start on boot..."
    systemctl enable "${SERVICE_NAME}"

    # Start service
    print_info "Starting ${SERVICE_NAME} service..."
    systemctl start "${SERVICE_NAME}"

    # Wait a moment for service to start
    sleep 2

    # Check service status
    if systemctl is-active --quiet "${SERVICE_NAME}"; then
        print_success "Service ${SERVICE_NAME} is running"
    else
        print_error "Service ${SERVICE_NAME} failed to start"
        print_info "Checking service status..."
        systemctl status "${SERVICE_NAME}" --no-pager
        exit 1
    fi
}

configure_firewall() {
    print_header "Configuring Firewall (Optional)"

    if command -v ufw &> /dev/null; then
        read -p "Do you want to configure UFW firewall to allow port 5000? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            print_info "Configuring UFW firewall..."
            ufw allow 5000/tcp
            print_success "Firewall configured to allow port 5000"
        else
            print_warning "Skipping firewall configuration"
        fi
    else
        print_warning "UFW not installed, skipping firewall configuration"
    fi
}

print_installation_summary() {
    if [ "$IS_UPDATE" = true ]; then
        print_header "Update Complete!"
        echo -e "${GREEN}HydeHome-AllSky has been successfully updated!${NC}"
    else
        print_header "Installation Complete!"
        echo -e "${GREEN}HydeHome-AllSky has been successfully installed!${NC}"
    fi

    echo ""
    echo "Installation Summary:"
    echo "  - Installation directory: ${INSTALL_DIR}"
    echo "  - Virtual environment:    ${VENV_DIR}"
    echo "  - Image storage directory: ${IMAGE_DIR}"
    echo "  - Log directory: ${LOG_DIR}"
    echo "  - Service name: ${SERVICE_NAME}"
    echo "  - Service user: ${SERVICE_USER}"
    echo ""
    echo "Service Management Commands:"
    echo "  - Start service:     sudo systemctl start ${SERVICE_NAME}"
    echo "  - Stop service:      sudo systemctl stop ${SERVICE_NAME}"
    echo "  - Restart service:   sudo systemctl restart ${SERVICE_NAME}"
    echo "  - Service status:    sudo systemctl status ${SERVICE_NAME}"
    echo "  - View logs:         sudo journalctl -u ${SERVICE_NAME} -f"
    echo ""
    echo "Web Interface:"
    echo "  - Access the application at: http://$(hostname -I | awk '{print $1}'):5000"
    echo "  - Or: http://localhost:5000"
    echo ""
    echo "Configuration Files:"
    echo "  - Flask app:         ${INSTALL_DIR}/flask_app.py"
    echo "  - Image capture:     ${INSTALL_DIR}/image_capture.py"
    echo "  - Service file:      /etc/systemd/system/${SERVICE_NAME}.service"
    echo "  - App config:        ${INSTALL_DIR}/app_config.json"
    echo "  - Requirements:      ${INSTALL_DIR}/requirements.txt"
    echo ""
    echo "Python Modules Installed:"
    echo "  - Flask (web framework)"
    echo "  - requests (for weather API)"
    echo "  - gunicorn (WSGI server)"
    echo "  - numpy, Pillow, psutil, zwoasi"
    echo ""
    if [ "$IS_UPDATE" = true ]; then
        echo "What Was Updated:"
        echo "  ✓ Application files updated"
        echo "  ✓ Virtual environment recreated"
        echo "  ✓ All dependencies reinstalled (including requests)"
        echo "  ✓ Configuration preserved"
        echo "  ✓ Service restarted"
        echo ""
    else
        echo "Next Steps:"
        echo "  1. Configure location settings in the Control Panel"
        echo "  2. Add OpenWeather API key for weather information"
        echo "  3. Test manual image capture"
        echo "  4. Configure background capture interval"
        echo ""
    fi
    print_info "For more information, see: ${INSTALL_DIR}/INSTALLATION.md"
    echo ""
}

################################################################################
# Main Installation Flow
################################################################################

main() {
    clear
    print_header "HydeHome-AllSky Installation Script"

    # Check if running as root first
    check_root

    # Detect if this is an update
    detect_existing_installation

    if [ "$IS_UPDATE" = true ]; then
        echo "This script will UPDATE your existing installation."
        echo "Installation directory: ${INSTALL_DIR}"
        echo "Service user: ${SERVICE_USER}"
        echo ""
        echo "Your settings and configuration will be preserved."
        echo ""
    else
        echo "This script will INSTALL HydeHome-AllSky as a systemd service."
        echo "Installation directory: ${INSTALL_DIR}"
        echo "Service user: ${SERVICE_USER}"
        echo ""
    fi

    read -p "Do you want to continue? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_warning "Installation cancelled by user"
        exit 0
    fi

    # Stop service if running (for updates)
    stop_service_if_running

    # Run installation steps
    check_prerequisites
    create_directories
    copy_application_files
    create_virtual_environment
    configure_application

    # Only configure sudo and firewall on fresh install
    if [ "$IS_UPDATE" = false ]; then
        configure_sudo_permissions
        configure_firewall
    fi

    create_systemd_service
    enable_and_start_service

    # Print summary
    print_installation_summary

    if [ "$IS_UPDATE" = true ]; then
        print_success "Update completed successfully!"
    else
        print_success "Installation completed successfully!"
    fi
}

# Run main function
main "$@"
