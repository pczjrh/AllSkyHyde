# HydeHome-AllSky Quick Start Guide

Get your all-sky camera up and running in minutes!

## Installation (5 minutes)

### 1. Download or Clone the Repository

```bash
# If using git
git clone <repository-url>
cd AllSkyHyde

# Or download and extract the ZIP file
```

### 2. Run the Installation Script

```bash
sudo ./install.sh
```

The script will automatically:
- ✅ Install system dependencies
- ✅ Create directories (`/opt/allskyhyde`, `/var/log/allskyhyde`, `~/allsky_images`)
- ✅ Set up Python virtual environment
- ✅ Install Python packages (Flask, Gunicorn, etc.)
- ✅ Configure application paths
- ✅ Create systemd service
- ✅ Enable auto-start on boot
- ✅ Start the service

### 3. Access the Web Interface

Open your browser and navigate to:

```
http://your-server-ip:5000
```

Or from the same machine:

```
http://localhost:5000
```

**That's it!** The application is now running.

---

## Initial Configuration (2 minutes)

### 1. Set Your Location

Navigate to **Control Panel** and configure:

- **Latitude**: Your location's latitude (e.g., 40.7128)
- **Longitude**: Your location's longitude (e.g., -74.0060)
- **Timezone**: UTC offset in hours (e.g., -5 for EST)
- **Daylight Saving Time**: Check if currently active

Click **Save Settings**

### 2. Add Weather API Key (Optional)

1. Get a free API key from [OpenWeatherMap](https://openweathermap.org/api)
2. In Control Panel, enter the key in **OpenWeather API Key** field
3. Click **Save Settings**

Weather information will now appear on the main page!

### 3. Test Image Capture

In the **Control Panel**:

1. Click **Auto Exposure** to capture your first image
2. Wait 10-30 seconds for capture to complete
3. Navigate to **Latest** page to see the image
4. Check **Gallery** to see all captured images

---

## Background Capture Setup (1 minute)

For automatic image capture throughout the night:

1. Go to **Control Panel**
2. Set **Capture Interval** (e.g., 300 seconds = 5 minutes)
3. Click **Update Interval**
4. Click **Start Background Capture**

The camera will now automatically capture images at your specified interval!

---

## Verify Installation

### Check Service Status

```bash
sudo systemctl status allskyhyde
```

You should see: **Active: active (running)**

### View Live Logs

```bash
sudo journalctl -u allskyhyde -f
```

Press `Ctrl+C` to exit log view.

### Test Manual Capture

```bash
cd /opt/allskyhyde
source venv/bin/activate
python image_capture.py
```

Check if an image appears in `~/allsky_images/`

---

## Common Tasks

### Restart the Service

```bash
sudo systemctl restart allskyhyde
```

### Stop the Service

```bash
sudo systemctl stop allskyhyde
```

### Start the Service

```bash
sudo systemctl start allskyhyde
```

### View Application Logs

```bash
tail -f /var/log/allskyhyde/error.log
```

### View Access Logs

```bash
tail -f /var/log/allskyhyde/access.log
```

---

## Troubleshooting

### Can't Access Web Interface

1. **Check if service is running:**
   ```bash
   sudo systemctl status allskyhyde
   ```

2. **Check firewall:**
   ```bash
   sudo ufw status
   # If needed, allow port 5000
   sudo ufw allow 5000/tcp
   ```

3. **Find your IP address:**
   ```bash
   hostname -I
   ```

### Camera Not Working

1. **Check USB connection:**
   - Ensure camera is plugged in
   - Check `lsusb` output

2. **Verify ZWO SDK:**
   ```bash
   ls -la /usr/local/lib/libASICamera2.so
   ```

3. **Add user to dialout group:**
   ```bash
   sudo usermod -a -G dialout $USER
   # Log out and log back in for changes to take effect
   ```

### Permission Errors

```bash
# Fix ownership of installation directory
sudo chown -R $USER:$USER /opt/allskyhyde

# Fix ownership of image directory
sudo chown -R $USER:$USER ~/allsky_images

# Restart service
sudo systemctl restart allskyhyde
```

### Service Fails to Start

```bash
# View detailed error logs
sudo journalctl -u allskyhyde -n 50 --no-pager

# Test manually to see errors
cd /opt/allskyhyde
source venv/bin/activate
python flask_app.py
```

---

## Next Steps

### 🌙 Optimize for Night Imaging

1. Test captures at different times (day vs night)
2. Adjust capture interval based on sky conditions
3. Review exposure times in Gallery page
4. Fine-tune gain settings in `image_capture.py` if needed

### 📊 Monitor System Health

- Visit **System Status** page regularly
- Check disk space (images can accumulate quickly)
- Use the built-in image deletion feature to manage storage

### 🔒 Secure Your Installation

- See [INSTALLATION.md](INSTALLATION.md) for Nginx reverse proxy setup
- Configure HTTPS with Let's Encrypt for remote access
- Set up firewall rules to restrict access

### 🚀 Advanced Configuration

- Configure auto-start of background capture (edit `flask_app.py`)
- Set up Nginx for production deployment
- Schedule automatic image cleanup
- Export images to external storage

---

## Getting Help

- **Detailed Installation**: See [INSTALLATION.md](INSTALLATION.md)
- **Project Documentation**: See [CLAUDE.md](CLAUDE.md)
- **Full README**: See [README.md](README.md)

---

## Quick Reference

### File Locations

| Item | Location |
|------|----------|
| Application | `/opt/allskyhyde` |
| Images | `~/allsky_images` |
| Logs | `/var/log/allskyhyde` |
| Service File | `/etc/systemd/system/allskyhyde.service` |
| Config | `/opt/allskyhyde/app_config.json` |

### Important Commands

```bash
# Service control
sudo systemctl start allskyhyde
sudo systemctl stop allskyhyde
sudo systemctl restart allskyhyde
sudo systemctl status allskyhyde

# View logs
sudo journalctl -u allskyhyde -f
tail -f /var/log/allskyhyde/error.log

# Manual capture
cd /opt/allskyhyde && source venv/bin/activate && python image_capture.py
```

### Default Settings

- **Port**: 5000
- **Capture Interval**: 300 seconds (5 minutes)
- **Image Format**: PNG
- **Exposure Range**: 1ms - 30,000ms (30 seconds)
- **Auto-exposure Target**: 64 ADU (25% of full-well)

---

## Success! 🎉

Your HydeHome-AllSky camera is now ready to capture the night sky!

Navigate to `http://your-server-ip:5000` and enjoy monitoring your all-sky camera.

Clear skies! 🌌
