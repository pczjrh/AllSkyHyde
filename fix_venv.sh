#!/bin/bash

#############################################################################
# Fix Virtual Environment Script
#
# This script recreates the Python virtual environment for Linux.
# Use this if you're getting errors about missing venv/bin/pip or
# if you're on WSL and had a Windows-style virtual environment.
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
log_info "Virtual Environment Fix Script"
echo ""

# Get current directory
APP_DIR="$(pwd)"

log_info "Current directory: ${APP_DIR}"

# Check if flask_app.py exists
if [ ! -f "${APP_DIR}/flask_app.py" ]; then
    log_error "flask_app.py not found in current directory!"
    log_error "Please run this script from the AllSkyHyde directory."
    exit 1
fi

# Check if venv exists
if [ -d "${APP_DIR}/venv" ]; then
    log_info "Found existing virtual environment."

    # Check if it's a Windows venv
    if [ -d "${APP_DIR}/venv/Scripts" ] && [ ! -d "${APP_DIR}/venv/bin" ]; then
        log_warning "Detected Windows-style virtual environment (Scripts/ folder)."
    elif [ ! -f "${APP_DIR}/venv/bin/activate" ]; then
        log_warning "Virtual environment appears to be corrupted."
    else
        log_info "Virtual environment appears to be valid."
        read -p "Do you still want to recreate it? (y/n): " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Operation cancelled."
            exit 0
        fi
    fi

    log_info "Removing old virtual environment..."
    rm -rf "${APP_DIR}/venv"
    log_success "Old virtual environment removed."
else
    log_info "No existing virtual environment found."
fi

# Check for python3
if ! command -v python3 &> /dev/null; then
    log_error "Python3 is not installed!"
    log_error "Please install Python3 first: sudo apt-get install python3 python3-venv"
    exit 1
fi

log_info "Python version: $(python3 --version)"

# Ensure python3-venv is installed
log_info "Checking for python3-venv package..."
if ! dpkg -l | grep -q python3-venv; then
    log_warning "python3-venv is not installed."
    read -p "Install python3-venv now? (y/n): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        sudo apt-get update
        sudo apt-get install -y python3-venv
    else
        log_error "Cannot create virtual environment without python3-venv."
        exit 1
    fi
fi

# Create new virtual environment
log_info "Creating new Python virtual environment..."
python3 -m venv "${APP_DIR}/venv"

# Verify creation
if [ ! -f "${APP_DIR}/venv/bin/activate" ]; then
    log_error "Failed to create virtual environment!"
    log_error "Please check that python3-venv is properly installed."
    exit 1
fi

log_success "Virtual environment created successfully."

# Upgrade pip
log_info "Upgrading pip..."
"${APP_DIR}/venv/bin/pip" install --upgrade pip

# Install requirements
if [ -f "${APP_DIR}/requirements.txt" ]; then
    log_info "Installing Python dependencies from requirements.txt..."
    "${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt"
    log_success "Dependencies installed."
else
    log_warning "requirements.txt not found."
    read -p "Install basic dependencies (Flask, gunicorn, psutil, requests)? (y/n): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Installing basic dependencies..."
        "${APP_DIR}/venv/bin/pip" install Flask gunicorn psutil requests Pillow numpy
        log_success "Basic dependencies installed."
    fi
fi

echo ""
log_success "Virtual environment is ready!"
echo ""
log_info "To activate the virtual environment manually:"
echo "  ${GREEN}source venv/bin/activate${NC}"
echo ""
log_info "To test the application:"
echo "  ${GREEN}source venv/bin/activate${NC}"
echo "  ${GREEN}python3 flask_app.py${NC}"
echo ""

# Check if service exists
if systemctl list-unit-files | grep -q "^allskyhyde.service"; then
    log_info "AllSkyHyde service detected. You may want to restart it:"
    echo "  ${GREEN}sudo systemctl restart allskyhyde${NC}"
    echo ""
fi
