// Image Zoom and Pan Functionality
document.addEventListener('DOMContentLoaded', function() {
    const imageWrapper = document.getElementById('imageWrapper');
    const image = document.getElementById('zoomableImage');
    const zoomInBtn = document.getElementById('zoomIn');
    const zoomOutBtn = document.getElementById('zoomOut');
    const resetBtn = document.getElementById('resetZoom');
    const zoomLevelEl = document.getElementById('zoomLevel');
    
    if (!image || !imageWrapper) return;
    
    let scale = 1;
    let panning = false;
    let pointX = 0;
    let pointY = 0;
    let start = { x: 0, y: 0 };
    
    function updateTransform() {
        image.style.transform = `translate(${pointX}px, ${pointY}px) scale(${scale})`;
        if (zoomLevelEl) {
            zoomLevelEl.textContent = `${Math.round(scale * 100)}%`;
        }
    }
    
    function resetTransform() {
        scale = 1;
        pointX = 0;
        pointY = 0;
        updateTransform();
    }
    
    // Zoom buttons
    if (zoomInBtn) {
        zoomInBtn.addEventListener('click', function() {
            scale += 0.25;
            if (scale > 5) scale = 5;  // Max zoom
            updateTransform();
        });
    }
    
    if (zoomOutBtn) {
        zoomOutBtn.addEventListener('click', function() {
            scale -= 0.25;
            if (scale < 0.5) scale = 0.5;  // Min zoom
            updateTransform();
        });
    }
    
    if (resetBtn) {
        resetBtn.addEventListener('click', resetTransform);
    }
    
    // Mouse wheel zoom
    imageWrapper.addEventListener('wheel', function(e) {
        e.preventDefault();
        
        const xs = (e.clientX - pointX) / scale;
        const ys = (e.clientY - pointY) / scale;
        
        // Adjust scale based on wheel delta
        if (e.deltaY < 0) {
            scale *= 1.1;
            if (scale > 5) scale = 5;  // Max zoom
        } else {
            scale /= 1.1;
            if (scale < 0.5) scale = 0.5;  // Min zoom
        }
        
        // Adjust pointX and pointY to zoom toward mouse position
        pointX = e.clientX - xs * scale;
        pointY = e.clientY - ys * scale;
        
        updateTransform();
    });
    
    // Pan functionality
    imageWrapper.addEventListener('mousedown', function(e) {
        e.preventDefault();
        start = { x: e.clientX - pointX, y: e.clientY - pointY };
        panning = true;
    });
    
    imageWrapper.addEventListener('mousemove', function(e) {
        e.preventDefault();
        if (!panning) return;
        
        pointX = (e.clientX - start.x);
        pointY = (e.clientY - start.y);
        updateTransform();
    });
    
    imageWrapper.addEventListener('mouseup', function(e) {
        panning = false;
    });
    
    imageWrapper.addEventListener('mouseleave', function(e) {
        panning = false;
    });
    
    // Touch support
    imageWrapper.addEventListener('touchstart', function(e) {
        e.preventDefault();
        if (e.touches.length === 1) {
            panning = true;
            start = { 
                x: e.touches[0].clientX - pointX, 
                y: e.touches[0].clientY - pointY 
            };
        }
    });
    
    let lastDistance = 0;
    
    imageWrapper.addEventListener('touchmove', function(e) {
        e.preventDefault();
        
        if (e.touches.length === 1 && panning) {
            // Pan with one finger
            pointX = (e.touches[0].clientX - start.x);
            pointY = (e.touches[0].clientY - start.y);
            updateTransform();
        } else if (e.touches.length === 2) {
            // Pinch to zoom with two fingers
            const touch1 = e.touches[0];
            const touch2 = e.touches[1];
            
            const distance = Math.sqrt(
                Math.pow(touch2.clientX - touch1.clientX, 2) +
                Math.pow(touch2.clientY - touch1.clientY, 2)
            );
            
            if (lastDistance > 0) {
                if (distance > lastDistance) {
                    // Zoom in
                    scale *= 1.05;
                    if (scale > 5) scale = 5;
                } else if (distance < lastDistance) {
                    // Zoom out
                    scale /= 1.05;
                    if (scale < 0.5) scale = 0.5;
                }
                updateTransform();
            }
            
            lastDistance = distance;
        }
    });
    
    imageWrapper.addEventListener('touchend', function(e) {
        panning = false;
        if (e.touches.length < 2) {
            lastDistance = 0;
        }
    });
    
    // Double tap to reset on mobile
    let lastTap = 0;
    imageWrapper.addEventListener('touchend', function(e) {
        const currentTime = new Date().getTime();
        const tapLength = currentTime - lastTap;
        if (tapLength < 300 && tapLength > 0) {
            resetTransform();
            e.preventDefault();
        }
        lastTap = currentTime;
    });
    
    // Initialize
    resetTransform();
});