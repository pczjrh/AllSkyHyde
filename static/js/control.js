// Control panel functionality
document.addEventListener('DOMContentLoaded', function() {
    const captureButton = document.getElementById('captureButton');
    const autoExposureButton = document.getElementById('autoExposureButton');
    const exposureTimeInput = document.getElementById('exposureTime');
    const captureStatusEl = document.getElementById('captureStatus');
    const logOutputEl = document.getElementById('logOutput');
    
    if (!captureButton || !captureStatusEl || !logOutputEl) return;
    
    let isCapturing = false;
    
    // Update status display
    function updateStatus(capturing) {
        isCapturing = capturing;
        
        if (capturing) {
            captureStatusEl.innerHTML = '<div class="status capturing">Capture in progress...</div>';
            captureButton.disabled = true;
            autoExposureButton.disabled = true;
        } else {
            captureStatusEl.innerHTML = '<div class="status idle">Idle - Ready to capture</div>';
            captureButton.disabled = false;
            autoExposureButton.disabled = false;
        }
    }
    
    // Update log display
    function updateLog(logData) {
        logOutputEl.innerHTML = '';
        
        logData.forEach(line => {
            const logLine = document.createElement('div');
            logLine.className = 'log-line';
            logLine.textContent = line;
            logOutputEl.appendChild(logLine);
        });
        
        // Scroll to bottom
        logOutputEl.scrollTop = logOutputEl.scrollHeight;
    }
    
    // Poll status
    function pollStatus() {
        fetch('/api/capture_status')
            .then(response => response.json())
            .then(data => {
                if (data.is_capturing !== isCapturing) {
                    updateStatus(data.is_capturing);
                }
                
                updateLog(data.log);
            })
            .catch(error => {
                console.error('Error fetching status:', error);
            });
    }
    
    // Trigger image capture
    function captureImage(useAutoExposure) {
        const formData = new FormData();
        
        if (!useAutoExposure) {
            const exposure = parseInt(exposureTimeInput.value, 10);
            if (isNaN(exposure) || exposure <= 0) {
                alert('Please enter a valid exposure time');
                return;
            }
            formData.append('exposure_ms', exposure);
        }
        
        updateStatus(true);
        
        fetch('/api/capture', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            console.log('Capture response:', data);
            // Status will be updated by the polling function
        })
        .catch(error => {
            console.error('Error capturing image:', error);
            updateStatus(false);
        });
    }
    
    // Add event listeners
    captureButton.addEventListener('click', function() {
        captureImage(false);
    });
    
    autoExposureButton.addEventListener('click', function() {
        captureImage(true);
    });
    
    // Start polling status
    setInterval(pollStatus, 1000);
    
    // Initial status check
    pollStatus();
});