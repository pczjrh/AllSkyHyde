# HydeHome-AllSky Installation Guide

This guide provides instructions for installing and running the HydeHome-AllSky Flask application as a production service using a WSGI server.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation Steps](#installation-steps)
- [Option 1: Gunicorn with systemd (Recommended)](#option-1-gunicorn-with-systemd-recommended)
- [Option 2: uWSGI with systemd](#option-2-uwsgi-with-systemd)
- [Option 3: Nginx + Gunicorn](#option-3-nginx--gunicorn)
- [Starting and Managing the Service](#starting-and-managing-the-service)
- [Troubleshooting](#troubleshooting)
- [Security Considerations](#security-considerations)

---

## Prerequisites

- Linux system (Ubuntu/Debian recommended)
- Python 3.7 or higher
- Root/sudo access
- ZWO ASI Camera SDK installed
- Git (optional, for cloning repository)

---

## Installation Steps

### 1. Install System Dependencies

```bash
# Update package list
sudo apt update

# Install Python and pip
sudo apt install python3 python3-pip python3-venv

# Install system dependencies for image processing
sudo apt install libjpeg-dev zlib1g-dev

# Install sudo (if not already installed) - required for system restart/shutdown
sudo apt install sudo
```

### 2. Set Up Application Directory

```bash
# Navigate to the application directory
cd /path/to/AllSkyHyde

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install --upgrade pip
pip install flask numpy pillow psutil zwoasi gunicorn
```

### 3. Configure Sudo Permissions (for System Control)

The application needs sudo permissions to restart/shutdown the system. Create a sudoers file:

```bash
sudo visudo -f /etc/sudoers.d/allskyhyde
```

Add the following lines (replace `username` with the actual user running the service):

```
# Allow user to restart and shutdown without password
username ALL=(ALL) NOPASSWD: /sbin/reboot
username ALL=(ALL) NOPASSWD: /sbin/poweroff
```

Save and exit. Set proper permissions:

```bash
sudo chmod 0440 /etc/sudoers.d/allskyhyde
```

### 4. Create Image Storage Directory

```bash
# Create directory for captured images
mkdir -p ~/zwo_images/zwo_images

# Set proper permissions
chmod 755 ~/zwo_images
```

### 5. Configure Application Paths

Edit `flask_app.py` and update the following paths:

```python
# Around line 20-25
IMAGE_DIR = "/home/yourusername/zwo_images/zwo_images"  # Update to your path
SCRIPT_PATH = "/path/to/AllSkyHyde/image_capture.py"  # Update to your path
```

Also update `image_capture.py` if needed:

```python
# Around line 17
OUTPUT_DIR = "./zwo_images"  # Or absolute path
```

---

## Option 1: Gunicorn with systemd (Recommended)

Gunicorn is a Python WSGI HTTP server that's simple, fast, and widely used.

### 1. Install Gunicorn

```bash
# Activate virtual environment if not already active
source /path/to/AllSkyHyde/venv/bin/activate

# Install Gunicorn
pip install gunicorn
```

### 2. Test Gunicorn

```bash
cd /path/to/AllSkyHyde
gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 120 flask_app:app
```

Visit `http://your-server-ip:5000` to verify it works. Press Ctrl+C to stop.

### 3. Create systemd Service File

```bash
sudo nano /etc/systemd/system/allskyhyde.service
```

Add the following content (update paths and username):

```ini
[Unit]
Description=HydeHome-AllSky Camera Web Application
After=network.target

[Service]
Type=notify
User=yourusername
Group=yourusername
WorkingDirectory=/path/to/AllSkyHyde
Environment="PATH=/path/to/AllSkyHyde/venv/bin"
ExecStart=/path/to/AllSkyHyde/venv/bin/gunicorn \
    --bind 0.0.0.0:5000 \
    --workers 2 \
    --timeout 120 \
    --access-logfile /var/log/allskyhyde/access.log \
    --error-logfile /var/log/allskyhyde/error.log \
    flask_app:app

Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 4. Create Log Directory

```bash
sudo mkdir -p /var/log/allskyhyde
sudo chown yourusername:yourusername /var/log/allskyhyde
```

### 5. Enable and Start Service

```bash
# Reload systemd to recognize new service
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable allskyhyde

# Start the service
sudo systemctl start allskyhyde

# Check status
sudo systemctl status allskyhyde
```

---

## Option 2: uWSGI with systemd

uWSGI is another popular WSGI server with more configuration options.

### 1. Install uWSGI

```bash
source /path/to/AllSkyHyde/venv/bin/activate
pip install uwsgi
```

### 2. Create uWSGI Configuration File

```bash
nano /path/to/AllSkyHyde/uwsgi.ini
```

Add the following:

```ini
[uwsgi]
module = flask_app:app
master = true
processes = 2
threads = 2
socket = /tmp/allskyhyde.sock
chmod-socket = 666
vacuum = true
die-on-term = true
```

### 3. Create systemd Service File

```bash
sudo nano /etc/systemd/system/allskyhyde-uwsgi.service
```

Add:

```ini
[Unit]
Description=HydeHome-AllSky uWSGI Service
After=network.target

[Service]
User=yourusername
Group=yourusername
WorkingDirectory=/path/to/AllSkyHyde
Environment="PATH=/path/to/AllSkyHyde/venv/bin"
ExecStart=/path/to/AllSkyHyde/venv/bin/uwsgi --ini /path/to/AllSkyHyde/uwsgi.ini

Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 4. Enable and Start Service

```bash
sudo systemctl daemon-reload
sudo systemctl enable allskyhyde-uwsgi
sudo systemctl start allskyhyde-uwsgi
sudo systemctl status allskyhyde-uwsgi
```

---

## Option 3: Nginx + Gunicorn

For production deployments, use Nginx as a reverse proxy in front of Gunicorn.

### 1. Set Up Gunicorn (Follow Option 1)

Configure Gunicorn to bind to a local socket instead of a port:

```bash
sudo nano /etc/systemd/system/allskyhyde.service
```

Change the `ExecStart` line to use a socket:

```ini
ExecStart=/path/to/AllSkyHyde/venv/bin/gunicorn \
    --bind unix:/tmp/allskyhyde.sock \
    --workers 2 \
    --timeout 120 \
    --access-logfile /var/log/allskyhyde/access.log \
    --error-logfile /var/log/allskyhyde/error.log \
    flask_app:app
```

### 2. Install Nginx

```bash
sudo apt install nginx
```

### 3. Configure Nginx

```bash
sudo nano /etc/nginx/sites-available/allskyhyde
```

Add the following:

```nginx
server {
    listen 80;
    server_name your-domain.com;  # Or your server IP

    client_max_body_size 50M;

    location / {
        proxy_pass http://unix:/tmp/allskyhyde.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Increase timeouts for long-running captures
        proxy_connect_timeout 300;
        proxy_send_timeout 300;
        proxy_read_timeout 300;
    }

    # Serve static files directly
    location /static {
        alias /path/to/AllSkyHyde/static;
        expires 30d;
    }
}
```

### 4. Enable Nginx Configuration

```bash
# Create symbolic link
sudo ln -s /etc/nginx/sites-available/allskyhyde /etc/nginx/sites-enabled/

# Test Nginx configuration
sudo nginx -t

# Restart Nginx
sudo systemctl restart nginx
```

### 5. Start Both Services

```bash
sudo systemctl start allskyhyde
sudo systemctl start nginx
```

---

## Starting and Managing the Service

### Service Management Commands

```bash
# Start service
sudo systemctl start allskyhyde

# Stop service
sudo systemctl stop allskyhyde

# Restart service
sudo systemctl restart allskyhyde

# Check status
sudo systemctl status allskyhyde

# View logs
sudo journalctl -u allskyhyde -f

# View application logs
tail -f /var/log/allskyhyde/error.log
tail -f /var/log/allskyhyde/access.log
```

### Enable/Disable Auto-start on Boot

```bash
# Enable auto-start
sudo systemctl enable allskyhyde

# Disable auto-start
sudo systemctl disable allskyhyde
```

---

## Troubleshooting

### Service Won't Start

1. Check service status and logs:
   ```bash
   sudo systemctl status allskyhyde
   sudo journalctl -u allskyhyde -n 50
   ```

2. Verify paths in service file are correct

3. Check Python virtual environment is activated:
   ```bash
   /path/to/AllSkyHyde/venv/bin/python --version
   ```

4. Test Flask app manually:
   ```bash
   cd /path/to/AllSkyHyde
   source venv/bin/activate
   python flask_app.py
   ```

### Permission Errors

1. Check file ownership:
   ```bash
   ls -la /path/to/AllSkyHyde
   ```

2. Ensure user in service file matches file owner

3. Check image directory permissions:
   ```bash
   ls -la ~/zwo_images
   ```

### Camera Not Detected

1. Verify ZWO SDK is installed:
   ```bash
   ls -la /usr/local/lib/libASICamera2.so
   ```

2. Check USB permissions - add user to dialout group:
   ```bash
   sudo usermod -a -G dialout yourusername
   ```

3. Restart system after adding to group

### Port Already in Use

1. Check what's using port 5000:
   ```bash
   sudo lsof -i :5000
   ```

2. Change port in service file or kill conflicting process

### High Memory Usage

1. Reduce number of Gunicorn workers in service file
2. Add worker timeout and max requests:
   ```bash
   --timeout 120 --max-requests 1000 --max-requests-jitter 50
   ```

---

## Security Considerations

### 1. Firewall Configuration

```bash
# Allow SSH
sudo ufw allow ssh

# Allow HTTP
sudo ufw allow 80/tcp

# Allow Flask app port (if not using Nginx)
sudo ufw allow 5000/tcp

# Enable firewall
sudo ufw enable
```

### 2. HTTPS with Let's Encrypt (Recommended for Production)

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d your-domain.com

# Certbot will automatically configure Nginx for HTTPS
```

### 3. Restrict Access

If running on a local network only, bind to local IP:

```bash
# In service file, change --bind to:
--bind 192.168.1.100:5000  # Your local IP
```

### 4. Keep System Updated

```bash
# Regular updates
sudo apt update
sudo apt upgrade

# Update Python packages
source venv/bin/activate
pip list --outdated
pip install --upgrade package-name
```

---

## Additional Configuration

### Auto-start Background Capture

To have background capture start automatically when the service starts, uncomment the appropriate line in `flask_app.py`:

```python
start_background_capture()  # Uncomment this line
```

### Configure Capture Settings

Edit `flask_app.py` to change default settings:

```python
# Around line 30
CAPTURE_INTERVAL = 300  # Default capture interval in seconds
```

### Log Rotation

Create log rotation configuration:

```bash
sudo nano /etc/logrotate.d/allskyhyde
```

Add:

```
/var/log/allskyhyde/*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    missingok
    sharedscripts
}
```

---

## Testing the Installation

1. **Access the web interface:**
   - Open browser to `http://your-server-ip:5000`
   - Should see the latest image page

2. **Test manual capture:**
   - Go to Control Panel
   - Click "Auto Exposure" or "Capture Image Now"
   - Check if image appears in Gallery

3. **Test background capture:**
   - In Control Panel, start background capture
   - Wait for capture interval
   - Verify new images appear

4. **Test system controls:**
   - Go to System Status page
   - Check system information displays correctly
   - Test restart/shutdown buttons (confirm but cancel)

---

## Support

For issues or questions:
- Check application logs: `/var/log/allskyhyde/error.log`
- Check system logs: `sudo journalctl -u allskyhyde`
- Review CLAUDE.md for project details
- Check GitHub issues if using version control

---

## License

This application is provided as-is for astrophotography and all-sky camera monitoring purposes.
