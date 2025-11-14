# AllSkyHyde Production Installation Guide

This guide explains how to install AllSkyHyde as a production service using Gunicorn and systemd.

## Overview

The production installation uses:
- **Gunicorn** - Production WSGI HTTP server for Flask applications
- **systemd** - Linux service manager for auto-start and management
- **Virtual Environment** - Isolated Python environment for dependencies

## Prerequisites

- Linux system with systemd (Raspberry Pi OS, Ubuntu, Debian, etc.)
- Python 3.7 or higher
- User account with sudo privileges
- Internet connection for package installation

## Quick Installation

1. Navigate to the AllSkyHyde directory:
   ```bash
   cd /home/yourusername/AllSkyHyde
   ```

2. Run the installation script:
   ```bash
   ./install_production.sh
   ```

3. Follow the interactive prompts:
   - Confirm removal of any previous installations
   - Verify the installation directory
   - Choose whether to enable shutdown/restart from web interface

4. Access the web interface:
   ```
   http://your-pi-ip-address:5000
   ```

## What the Installation Script Does

### 1. Pre-Installation Checks
- Verifies not running as root
- Detects and removes previous installations
- Confirms installation directory
- Ensures installation is in user's home directory

### 2. Dependency Installation
- Checks for Python3 and pip
- Creates Python virtual environment (if not exists)
- Installs all required packages from requirements.txt
- Verifies Gunicorn installation

### 3. Directory Setup
- Creates image directory at `~/allsky_images`
- Verifies all required files are present

### 4. Service Configuration
- Creates systemd service file: `/etc/systemd/system/allskyhyde.service`
- Configures Gunicorn with:
  - 2 worker processes
  - 4 threads per worker
  - Automatic restart on failure
  - Logging to application directory

### 5. Optional Sudo Configuration
- Allows web interface to restart/shutdown system
- Grants sudo access for specific commands only
- Completely optional and can be skipped

### 6. Service Activation
- Enables service to start on boot
- Starts the service immediately
- Verifies service is running

## Installation Location
The script is designed to work with installations in your home directory (e.g., `/home/pi/AllSkyHyde`).

## Service Management

### View Service Status
```bash
sudo systemctl status allskyhyde
```

### Stop Service
```bash
sudo systemctl stop allskyhyde
```

### Start Service
```bash
sudo systemctl start allskyhyde
```

### Restart Service
```bash
sudo systemctl restart allskyhyde
```

### View Live Logs
```bash
sudo journalctl -u allskyhyde -f
```

### Disable Auto-Start
```bash
sudo systemctl disable allskyhyde
```

### Re-Enable Auto-Start
```bash
sudo systemctl enable allskyhyde
```

## Log Files

The application creates two log files in the installation directory:

- **gunicorn-access.log** - HTTP access logs (all requests)
- **gunicorn-error.log** - Application errors and output

View logs:
```bash
tail -f ~/AllSkyHyde/gunicorn-error.log
tail -f ~/AllSkyHyde/gunicorn-access.log
```

## Configuration Files

- **app_config.json** - Application settings (location, API keys, capture settings)
- **requirements.txt** - Python dependencies

## Port Configuration

By default, the application runs on port **5000**.

To change the port:
1. Edit the service file: `sudo nano /etc/systemd/system/allskyhyde.service`
2. Change the `--bind 0.0.0.0:5000` line to your desired port
3. Reload and restart:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart allskyhyde
   ```

## Firewall Configuration

If you have a firewall enabled, allow port 5000:

```bash
# For UFW (Ubuntu/Debian)
sudo ufw allow 5000/tcp

# For firewalld (CentOS/RHEL)
sudo firewall-cmd --permanent --add-port=5000/tcp
sudo firewall-cmd --reload
```

## Uninstallation

To remove the service:

```bash
cd /home/yourusername/AllSkyHyde
./uninstall_production.sh
```

The uninstall script will:
- Stop and disable the service
- Remove the systemd service file
- Optionally remove sudo configuration
- Optionally remove logs and config files
- Optionally remove Python virtual environment

**Note:** Image files in `~/allsky_images` are NOT removed automatically.

## Helper Scripts

The installation includes several helper scripts:

- **`install_production.sh`** - Main installation script
- **`uninstall_production.sh`** - Complete removal script
- **`fix_venv.sh`** - Fix virtual environment issues (WSL/Windows compatibility)
- **`fix_paths.sh`** - Fix hardcoded paths in configuration file

## Troubleshooting

### Hardcoded Paths

If you moved the installation directory or see path-related errors, run:

```bash
cd ~/AllSkyHyde
./fix_paths.sh
```

This will update `app_config.json` with the correct paths based on your current directory.

### Virtual Environment Issues (WSL/Windows)

If you see an error like `/home/user/AllSkyHyde/venv/bin/pip: No such file or directory`:

This happens when you have a Windows-style virtual environment on WSL. The installation script will automatically detect and fix this, or you can run:

```bash
cd ~/AllSkyHyde
./fix_venv.sh
```

This will recreate the virtual environment for Linux.

### Service Won't Start

Check the service status:
```bash
sudo systemctl status allskyhyde
```

View recent errors:
```bash
sudo journalctl -u allskyhyde -n 50 --no-pager
```

Check error log:
```bash
tail -n 50 ~/AllSkyHyde/gunicorn-error.log
```

### Permission Errors

Ensure the installation directory is owned by your user:
```bash
ls -la ~/AllSkyHyde
```

Fix permissions if needed:
```bash
sudo chown -R $USER:$USER ~/AllSkyHyde
```

### Dependencies Missing

Reinstall dependencies:
```bash
cd ~/AllSkyHyde
source venv/bin/activate
pip install -r requirements.txt
```

### Port Already in Use

Check what's using port 5000:
```bash
sudo lsof -i :5000
```

Kill the process or change the port in the service file.

### Can't Access Web Interface

1. Verify service is running:
   ```bash
   sudo systemctl status allskyhyde
   ```

2. Check if port is listening:
   ```bash
   sudo netstat -tlnp | grep 5000
   ```

3. Test locally:
   ```bash
   curl http://localhost:5000
   ```

4. Check firewall settings
5. Verify IP address: `hostname -I`

## Upgrading the Application

To upgrade after pulling new code:

```bash
cd ~/AllSkyHyde
git pull  # if using git
sudo systemctl restart allskyhyde
```

If new dependencies were added:
```bash
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart allskyhyde
```

## Performance Tuning

### Adjusting Workers and Threads

Edit the service file to tune Gunicorn:
```bash
sudo nano /etc/systemd/system/allskyhyde.service
```

Guidelines:
- **Workers**: (2 x CPU cores) + 1
- **Threads**: 2-4 per worker
- **Timeout**: Increase if captures take longer

Example for Raspberry Pi 4 (4 cores):
```
--workers 4
--threads 4
--timeout 180
```

After changes:
```bash
sudo systemctl daemon-reload
sudo systemctl restart allskyhyde
```

## Security Notes

1. **Sudo Configuration**: Only enable if you trust all users who can access the web interface
2. **Firewall**: Consider restricting access to port 5000 to your local network
3. **HTTPS**: For remote access, consider using a reverse proxy (nginx) with HTTPS
4. **Updates**: Keep your system and Python packages updated

## Using with Nginx (Advanced)

For production deployments, consider using Nginx as a reverse proxy:

1. Install Nginx:
   ```bash
   sudo apt-get install nginx
   ```

2. Create Nginx configuration:
   ```bash
   sudo nano /etc/nginx/sites-available/allskyhyde
   ```

3. Add configuration:
   ```nginx
   server {
       listen 80;
       server_name your-domain.com;

       location / {
           proxy_pass http://127.0.0.1:5000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       }
   }
   ```

4. Enable and restart:
   ```bash
   sudo ln -s /etc/nginx/sites-available/allskyhyde /etc/nginx/sites-enabled/
   sudo nginx -t
   sudo systemctl restart nginx
   ```

## Support

If you encounter issues:
1. Check the troubleshooting section above
2. Review log files for error messages
3. Ensure all prerequisites are met
4. Verify file permissions

## Additional Resources

- Gunicorn Documentation: https://docs.gunicorn.org/
- systemd Documentation: https://www.freedesktop.org/wiki/Software/systemd/
- Flask Deployment: https://flask.palletsprojects.com/en/latest/deploying/
