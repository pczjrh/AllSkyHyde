#!/bin/bash

#############################################################################
# AllSkyHyde Production Uninstallation Script
#
# This script safely removes the AllSkyHyde service and optionally cleans
# up configuration files.
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
    echo -e "${BLUE}║       ${RED}AllSkyHyde Production Uninstallation${BLUE}         ║${NC}"
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

# Confirm uninstallation
confirm_uninstall() {
    echo ""
    log_warning "This will remove the AllSkyHyde service from your system."
    echo ""
    read -p "Are you sure you want to uninstall? (y/n): " -n 1 -r
    echo ""

    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Uninstallation cancelled."
        exit 0
    fi
}

# Stop and disable service
stop_service() {
    log_info "Stopping ${SERVICE_NAME} service..."

    if systemctl is-active --quiet ${SERVICE_NAME}.service; then
        sudo systemctl stop ${SERVICE_NAME}.service
        log_success "Service stopped."
    else
        log_info "Service is not running."
    fi

    if systemctl is-enabled --quiet ${SERVICE_NAME}.service 2>/dev/null; then
        log_info "Disabling ${SERVICE_NAME} service..."
        sudo systemctl disable ${SERVICE_NAME}.service
        log_success "Service disabled."
    else
        log_info "Service is not enabled."
    fi
}

# Remove service file
remove_service_file() {
    local service_file="/etc/systemd/system/${SERVICE_NAME}.service"

    if [ -f "$service_file" ]; then
        log_info "Removing service file..."
        sudo rm -f "$service_file"
        log_success "Service file removed."
    else
        log_info "Service file does not exist."
    fi

    log_info "Reloading systemd daemon..."
    sudo systemctl daemon-reload
}

# Remove sudoers configuration
remove_sudoers() {
    local sudoers_file="/etc/sudoers.d/${SERVICE_NAME}"

    if [ -f "$sudoers_file" ]; then
        echo ""
        read -p "Remove sudo configuration? (y/n): " -n 1 -r
        echo ""

        if [[ $REPLY =~ ^[Yy]$ ]]; then
            log_info "Removing sudoers configuration..."
            sudo rm -f "$sudoers_file"
            log_success "Sudoers configuration removed."
        fi
    fi
}

# Optionally remove configuration and logs
cleanup_files() {
    local app_dir="$(pwd)"

    echo ""
    log_info "The following files can be removed:"
    echo ""

    # List files that can be removed
    local files_to_check=(
        "app_config.json"
        "gunicorn-access.log"
        "gunicorn-error.log"
    )

    local found_files=()

    for file in "${files_to_check[@]}"; do
        if [ -f "${app_dir}/${file}" ]; then
            echo "  - ${file}"
            found_files+=("${app_dir}/${file}")
        fi
    done

    if [ ${#found_files[@]} -gt 0 ]; then
        echo ""
        read -p "Do you want to remove these configuration and log files? (y/n): " -n 1 -r
        echo ""

        if [[ $REPLY =~ ^[Yy]$ ]]; then
            for file in "${found_files[@]}"; do
                log_info "Removing ${file}..."
                rm -f "$file"
            done
            log_success "Files removed."
        else
            log_info "Configuration and log files preserved."
        fi
    fi

    # Ask about virtual environment
    if [ -d "${app_dir}/venv" ]; then
        echo ""
        read -p "Do you want to remove the Python virtual environment? (y/n): " -n 1 -r
        echo ""

        if [[ $REPLY =~ ^[Yy]$ ]]; then
            log_info "Removing virtual environment..."
            rm -rf "${app_dir}/venv"
            log_success "Virtual environment removed."
        else
            log_info "Virtual environment preserved."
        fi
    fi
}

# Display completion message
display_completion() {
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║                                                        ║${NC}"
    echo -e "${GREEN}║            Uninstallation Complete!                    ║${NC}"
    echo -e "${GREEN}║                                                        ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════╝${NC}"
    echo ""

    log_success "AllSkyHyde service has been removed from your system."
    echo ""

    log_info "Note: Image files in ~/allsky_images were not removed."
    log_info "You can manually delete them if desired."
    echo ""
}

# Main uninstallation function
main() {
    print_banner
    check_root
    confirm_uninstall

    echo ""
    log_info "Starting uninstallation..."
    echo ""

    stop_service
    remove_service_file
    remove_sudoers
    cleanup_files

    display_completion
}

# Run main function
main
