#!/bin/bash

#############################################################################
# AllSkyHyde Production Installation Script
#
# This script installs the AllSkyHyde Flask application as a systemd service
# running with Gunicorn as the production WSGI server.
#
# The script will:
# 1. Detect and remove any previous installations
# 2. Interactively confirm installation directory
# 3. Install required dependencies
# 4. Create systemd service for auto-start on boot
# 5. Start the service
#############################################################################

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Service name
SERVICE_NAME="allskyhyde"

# Logging functions
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

# Print banner
print_banner() {
    echo ""
    echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║                                                        ║${NC}"
    echo -e "${BLUE}║        ${GREEN}AllSkyHyde Production Installation${BLUE}          ║${NC}"
    echo -e "${BLUE}║                                                        ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

# Check if running as root
check_root() {
    if [[ $EUID -eq 0 ]]; then
        log_error "This script should NOT be run as root!"
        log_error "Run it as your normal user. It will ask for sudo when needed."
        exit 1
    fi
}

# Check for previous installations
check_previous_installation() {
    log_info "Checking for previous installations..."

    local found_services=()

    # Check for the main service
    if systemctl list-unit-files | grep -q "^${SERVICE_NAME}.service"; then
        found_services+=("${SERVICE_NAME}.service")
    fi

    # Check for any variations
    for service in allsky allsky-capture allskyhyde-web; do
        if systemctl list-unit-files | grep -q "^${service}.service"; then
            found_services+=("${service}.service")
        fi
    done

    if [ ${#found_services[@]} -gt 0 ]; then
        log_warning "Found previous installation(s):"
        for service in "${found_services[@]}"; do
            echo "  - $service"
        done
        echo ""
        read -p "Do you want to remove these services and reinstall? (y/n): " -n 1 -r
        echo ""
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            remove_previous_installation "${found_services[@]}"
        else
            log_error "Installation cancelled by user."
            exit 1
        fi
    else
        log_success "No previous installations found."
    fi
}

# Remove previous installation
remove_previous_installation() {
    local services=("$@")

    log_info "Removing previous installations..."

    for service in "${services[@]}"; do
        log_info "Stopping and disabling ${service}..."
        sudo systemctl stop "$service" 2>/dev/null || true
        sudo systemctl disable "$service" 2>/dev/null || true

        # Remove service file
        local service_path="/etc/systemd/system/$service"
        if [ -f "$service_path" ]; then
            log_info "Removing service file: $service_path"
            sudo rm -f "$service_path"
        fi
    done

    # Reload systemd daemon
    log_info "Reloading systemd daemon..."
    sudo systemctl daemon-reload

    log_success "Previous installations removed."
}

# Confirm installation directory
confirm_directory() {
    local current_dir="$(pwd)"

    echo ""
    log_info "Current directory: ${GREEN}${current_dir}${NC}"
    echo ""

    # Check if flask_app.py exists
    if [ ! -f "${current_dir}/flask_app.py" ]; then
        log_error "flask_app.py not found in current directory!"
        log_error "Please run this script from the AllSkyHyde directory."
        exit 1
    fi

    # Verify it's in a home directory (not /opt or /usr/local)
    if [[ ! "$current_dir" =~ ^/home/.*$ ]] && [[ ! "$current_dir" =~ ^/mnt/c/Users/.*$ ]]; then
        log_warning "Installation directory is not in a user's home directory."
        log_warning "This script is designed to work from /home/<user>/ directories."
        echo ""
        read -p "Do you want to continue anyway? (y/n): " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_error "Installation cancelled by user."
            exit 1
        fi
    fi

    echo ""
    log_info "The application will be installed from: ${GREEN}${current_dir}${NC}"
    echo ""
    read -p "Is this the correct directory? (y/n): " -n 1 -r
    echo ""

    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_error "Installation cancelled by user."
        exit 1
    fi

    APP_DIR="$current_dir"
}

# Get current user information
get_user_info() {
    CURRENT_USER="$(whoami)"
    USER_GROUP="$(id -gn)"

    log_info "Installation user: ${GREEN}${CURRENT_USER}${NC}"
    log_info "User group: ${GREEN}${USER_GROUP}${NC}"
}

# Check and install dependencies
install_dependencies() {
    log_info "Checking system dependencies..."

    # Check for Python3
    if ! command -v python3 &> /dev/null; then
        log_error "Python3 is not installed!"
        log_info "Installing Python3..."
        sudo apt-get update
        sudo apt-get install -y python3 python3-pip python3-venv
    else
        log_success "Python3 is already installed: $(python3 --version)"
    fi

    # Check for pip
    if ! command -v pip3 &> /dev/null; then
        log_info "Installing pip3..."
        sudo apt-get install -y python3-pip
    fi

    # Ensure python3-venv is installed
    log_info "Ensuring python3-venv is installed..."
    if ! dpkg -l | grep -q python3-venv; then
        sudo apt-get update
        sudo apt-get install -y python3-venv
    fi

    # Check if virtual environment exists and is valid for Linux
    local needs_recreate=false

    if [ ! -d "${APP_DIR}/venv" ]; then
        log_info "Creating Python virtual environment..."
        needs_recreate=true
    elif [ ! -f "${APP_DIR}/venv/bin/activate" ]; then
        # Check if it's a Windows venv (has Scripts/ instead of bin/)
        if [ -d "${APP_DIR}/venv/Scripts" ]; then
            log_warning "Detected Windows-style virtual environment."
            log_info "Recreating virtual environment for Linux..."
            rm -rf "${APP_DIR}/venv"
            needs_recreate=true
        else
            log_error "Virtual environment exists but is invalid!"
            log_info "Recreating virtual environment..."
            rm -rf "${APP_DIR}/venv"
            needs_recreate=true
        fi
    else
        log_success "Virtual environment already exists."
    fi

    # Create venv if needed
    if [ "$needs_recreate" = true ]; then
        python3 -m venv "${APP_DIR}/venv"

        # Verify creation was successful
        if [ ! -f "${APP_DIR}/venv/bin/activate" ]; then
            log_error "Failed to create virtual environment!"
            log_error "Please ensure python3-venv is installed: sudo apt-get install python3-venv"
            exit 1
        fi

        log_success "Virtual environment created successfully."
    fi

    # Install Python dependencies
    log_info "Installing Python dependencies..."
    "${APP_DIR}/venv/bin/pip" install --upgrade pip

    if [ -f "${APP_DIR}/requirements.txt" ]; then
        log_info "Installing from requirements.txt..."
        "${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt"
        log_success "Python dependencies installed."
    else
        log_warning "requirements.txt not found. Installing basic dependencies..."
        "${APP_DIR}/venv/bin/pip" install Flask gunicorn psutil requests
    fi
}

# Verify gunicorn installation
verify_gunicorn() {
    log_info "Verifying Gunicorn installation..."

    if [ ! -f "${APP_DIR}/venv/bin/gunicorn" ]; then
        log_error "Gunicorn not found in virtual environment!"
        log_info "Installing Gunicorn..."
        "${APP_DIR}/venv/bin/pip" install gunicorn
    fi

    log_success "Gunicorn is installed: $(${APP_DIR}/venv/bin/gunicorn --version)"
}

# Create image directory if it doesn't exist
setup_image_directory() {
    local image_dir="${HOME}/allsky_images"

    if [ ! -d "$image_dir" ]; then
        log_info "Creating image directory: $image_dir"
        mkdir -p "$image_dir"
        log_success "Image directory created."
    else
        log_success "Image directory already exists."
    fi
}

# Update or create app_config.json with correct paths
update_app_config() {
    log_info "Updating application configuration..."

    local config_file="${APP_DIR}/app_config.json"
    local image_dir="${HOME}/allsky_images"
    local script_path="${APP_DIR}/image_capture.py"

    # If config exists, update paths; otherwise create new config
    if [ -f "$config_file" ]; then
        log_info "Updating existing configuration file..."

        # Backup existing config
        cp "$config_file" "${config_file}.backup"

        # Use Python to update the JSON file while preserving other settings
        python3 -c "
import json
import sys

config_file = '${config_file}'
try:
    with open(config_file, 'r') as f:
        config = json.load(f)

    # Update paths
    config['image_dir'] = '${image_dir}'
    config['script_path'] = '${script_path}'

    with open(config_file, 'w') as f:
        json.dump(config, f, indent=4)

    print('Configuration updated successfully')
except Exception as e:
    print(f'Error updating config: {e}', file=sys.stderr)
    sys.exit(1)
"
        if [ $? -eq 0 ]; then
            log_success "Configuration file updated."
            log_info "Backup saved to: ${config_file}.backup"
        else
            log_warning "Failed to update config file. Restoring backup..."
            mv "${config_file}.backup" "$config_file"
        fi
    else
        log_info "Creating new configuration file..."
        cat > "$config_file" <<EOF
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
    "image_dir": "${image_dir}",
    "script_path": "${script_path}",
    "last_updated": "$(date '+%Y-%m-%d %H:%M:%S')"
}
EOF
        log_success "Configuration file created."
    fi

    log_info "Configured paths:"
    echo "  Image directory: ${GREEN}${image_dir}${NC}"
    echo "  Script path:     ${GREEN}${script_path}${NC}"
}

# Create systemd service file
create_service_file() {
    log_info "Creating systemd service file..."

    local service_file="/etc/systemd/system/${SERVICE_NAME}.service"

    # Create temporary service file
    cat > /tmp/${SERVICE_NAME}.service <<EOF
[Unit]
Description=AllSkyHyde Web Application
After=network.target

[Service]
Type=notify
User=${CURRENT_USER}
Group=${USER_GROUP}
WorkingDirectory=${APP_DIR}
Environment="PATH=${APP_DIR}/venv/bin"

# Gunicorn configuration
ExecStart=${APP_DIR}/venv/bin/gunicorn \\
    --bind 0.0.0.0:5000 \\
    --workers 2 \\
    --threads 4 \\
    --timeout 120 \\
    --access-logfile ${APP_DIR}/gunicorn-access.log \\
    --error-logfile ${APP_DIR}/gunicorn-error.log \\
    --log-level info \\
    flask_app:app

# Restart configuration
Restart=always
RestartSec=10

# Security settings
NoNewPrivileges=true
PrivateTmp=true

# Allow shutdown/restart commands (requires sudo configuration)
AmbientCapabilities=

[Install]
WantedBy=multi-user.target
EOF

    # Move to system directory
    sudo mv /tmp/${SERVICE_NAME}.service "$service_file"
    sudo chmod 644 "$service_file"

    log_success "Service file created: $service_file"
}

# Configure sudo for shutdown/restart
configure_sudo() {
    log_info "Checking sudo configuration for system power management..."

    local sudoers_file="/etc/sudoers.d/${SERVICE_NAME}"

    if [ ! -f "$sudoers_file" ]; then
        echo ""
        log_info "To allow the web interface to restart/shutdown the system,"
        log_info "we need to configure sudo permissions."
        echo ""
        read -p "Do you want to enable shutdown/restart from web interface? (y/n): " -n 1 -r
        echo ""

        if [[ $REPLY =~ ^[Yy]$ ]]; then
            log_info "Creating sudoers configuration..."

            # Create temporary sudoers file
            cat > /tmp/${SERVICE_NAME}-sudoers <<EOF
# Allow ${CURRENT_USER} to run shutdown/reboot without password
${CURRENT_USER} ALL=(ALL) NOPASSWD: /sbin/reboot, /sbin/poweroff, /usr/bin/systemctl restart ${SERVICE_NAME}, /usr/bin/systemctl stop ${SERVICE_NAME}, /usr/bin/systemctl start ${SERVICE_NAME}
EOF

            # Validate and install sudoers file
            if sudo visudo -c -f /tmp/${SERVICE_NAME}-sudoers; then
                sudo mv /tmp/${SERVICE_NAME}-sudoers "$sudoers_file"
                sudo chmod 440 "$sudoers_file"
                log_success "Sudo configuration completed."
            else
                log_error "Failed to validate sudoers file. Skipping."
                rm -f /tmp/${SERVICE_NAME}-sudoers
            fi
        else
            log_info "Skipping sudo configuration. Shutdown/restart will require manual intervention."
        fi
    else
        log_success "Sudo configuration already exists."
    fi
}

# Enable and start service
enable_service() {
    log_info "Reloading systemd daemon..."
    sudo systemctl daemon-reload

    log_info "Enabling ${SERVICE_NAME} service..."
    sudo systemctl enable ${SERVICE_NAME}.service

    log_info "Starting ${SERVICE_NAME} service..."
    sudo systemctl start ${SERVICE_NAME}.service

    # Wait a moment for service to start
    sleep 2

    # Check service status
    if sudo systemctl is-active --quiet ${SERVICE_NAME}.service; then
        log_success "Service started successfully!"
    else
        log_error "Service failed to start. Checking status..."
        sudo systemctl status ${SERVICE_NAME}.service --no-pager
        exit 1
    fi
}

# Display service information
display_service_info() {
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║                                                        ║${NC}"
    echo -e "${GREEN}║              Installation Complete!                    ║${NC}"
    echo -e "${GREEN}║                                                        ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════╝${NC}"
    echo ""

    log_info "Service Name: ${GREEN}${SERVICE_NAME}${NC}"
    log_info "Installation Directory: ${GREEN}${APP_DIR}${NC}"
    log_info "Web Interface: ${GREEN}http://$(hostname -I | awk '{print $1}'):5000${NC}"
    echo ""

    log_info "Useful commands:"
    echo "  View service status:  ${GREEN}sudo systemctl status ${SERVICE_NAME}${NC}"
    echo "  Stop service:         ${GREEN}sudo systemctl stop ${SERVICE_NAME}${NC}"
    echo "  Start service:        ${GREEN}sudo systemctl start ${SERVICE_NAME}${NC}"
    echo "  Restart service:      ${GREEN}sudo systemctl restart ${SERVICE_NAME}${NC}"
    echo "  View logs:            ${GREEN}sudo journalctl -u ${SERVICE_NAME} -f${NC}"
    echo "  Disable auto-start:   ${GREEN}sudo systemctl disable ${SERVICE_NAME}${NC}"
    echo ""

    log_info "Log files:"
    echo "  Access log:  ${GREEN}${APP_DIR}/gunicorn-access.log${NC}"
    echo "  Error log:   ${GREEN}${APP_DIR}/gunicorn-error.log${NC}"
    echo ""

    # Display current status
    log_info "Current service status:"
    sudo systemctl status ${SERVICE_NAME}.service --no-pager | head -n 10
    echo ""
}

# Main installation function
main() {
    print_banner

    # Run checks
    check_root
    check_previous_installation
    confirm_directory
    get_user_info

    echo ""
    log_info "Starting installation..."
    echo ""

    # Installation steps
    install_dependencies
    verify_gunicorn
    setup_image_directory
    update_app_config
    create_service_file
    configure_sudo
    enable_service

    # Display completion info
    display_service_info

    log_success "Installation complete! Your AllSkyHyde application is now running."
    log_info "Visit ${GREEN}http://$(hostname -I | awk '{print $1}'):5000${NC} to access the web interface."
}

# Run main function
main
