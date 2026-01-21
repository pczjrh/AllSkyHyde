/**
 * Star Map Overlay for AllSky Camera
 * Renders stars from the Yale Bright Star Catalog on a canvas overlay
 */

(function() {
    'use strict';

    // Configuration
    const UPDATE_INTERVAL = 30 * 60 * 1000; // 30 minutes in milliseconds
    const NAME_MAG_THRESHOLD = 2.0; // Show names for stars brighter than this

    // State
    let canvas = null;
    let ctx = null;
    let stars = [];
    let constellationLines = [];
    let settings = {
        enabled: true,
        showNames: true,
        showConstellations: true,
        opacity: 0.8,
        color: '#FFD700',
        magnitudeLimit: 4.0,
        rotationAdjust: 0,
        offsetX: 0,
        offsetY: 0,
        scaleX: 1.0,
        scaleY: 1.0
    };
    let updateTimer = null;
    let imageElement = null;

    /**
     * Initialize the star map overlay
     */
    function init() {
        canvas = document.getElementById('starmapCanvas');
        if (!canvas) {
            console.log('Star map canvas not found');
            return;
        }

        ctx = canvas.getContext('2d');
        imageElement = document.getElementById('zoomableImage');

        if (!imageElement) {
            console.log('Image element not found');
            return;
        }

        // Set up resize handling
        window.addEventListener('resize', handleResize);
        imageElement.addEventListener('load', handleResize);

        // Initial resize
        handleResize();

        // Load settings and fetch stars
        loadSettings().then(() => {
            if (settings.enabled) {
                fetchStars();
            }
        });

        // Set up periodic updates
        updateTimer = setInterval(() => {
            if (settings.enabled) {
                fetchStars();
            }
        }, UPDATE_INTERVAL);

        console.log('Star map overlay initialized');
    }

    /**
     * Load starmap settings from the API
     */
    async function loadSettings() {
        try {
            const response = await fetch('/api/settings');
            const data = await response.json();

            settings.enabled = data.starmap_enabled !== undefined ? data.starmap_enabled : false;
            settings.showNames = data.starmap_show_names !== undefined ? data.starmap_show_names : true;
            settings.showConstellations = data.starmap_show_constellations !== undefined ? data.starmap_show_constellations : true;
            settings.opacity = data.starmap_opacity !== undefined ? data.starmap_opacity : 0.8;
            settings.color = data.starmap_color || '#FFD700';
            settings.magnitudeLimit = data.starmap_magnitude_limit !== undefined ? data.starmap_magnitude_limit : 4.0;
            settings.rotationAdjust = data.starmap_rotation_adjust !== undefined ? data.starmap_rotation_adjust : 0;
            settings.offsetX = data.starmap_offset_x !== undefined ? data.starmap_offset_x : 0;
            settings.offsetY = data.starmap_offset_y !== undefined ? data.starmap_offset_y : 0;
            settings.scaleX = data.starmap_scale_x !== undefined ? data.starmap_scale_x : 1.0;
            settings.scaleY = data.starmap_scale_y !== undefined ? data.starmap_scale_y : 1.0;

            console.log('Star map settings loaded:', settings);
        } catch (error) {
            console.error('Error loading starmap settings:', error);
        }
    }

    /**
     * Fetch star positions from the API
     */
    async function fetchStars() {
        try {
            const response = await fetch('/api/starmap');
            const data = await response.json();

            if (data.status === 'success') {
                stars = data.stars;
                constellationLines = data.constellation_lines || [];
                console.log(`Fetched ${stars.length} visible stars and ${constellationLines.length} constellation lines`);
                console.log('Show constellations setting:', settings.showConstellations);
                if (constellationLines.length > 0) {
                    console.log('First constellation line:', constellationLines[0]);
                }
                render();
            } else if (data.status === 'disabled') {
                console.log('Star map is disabled');
                clearCanvas();
            } else {
                console.error('Error fetching stars:', data.message);
            }
        } catch (error) {
            console.error('Error fetching star data:', error);
        }
    }

    /**
     * Handle window/image resize
     */
    function handleResize() {
        if (!canvas || !imageElement) return;

        // Get the image wrapper dimensions
        const wrapper = document.getElementById('imageWrapper');
        if (!wrapper) return;

        // Match canvas size to the displayed image size
        const rect = imageElement.getBoundingClientRect();
        canvas.width = rect.width;
        canvas.height = rect.height;

        // Re-render if we have stars
        if (stars.length > 0) {
            render();
        }
    }

    /**
     * Clear the canvas
     */
    function clearCanvas() {
        if (!ctx || !canvas) return;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
    }

    /**
     * Render stars on the canvas
     */
    function render() {
        if (!ctx || !canvas || !settings.enabled) {
            clearCanvas();
            return;
        }

        clearCanvas();

        // Get scale factors for coordinate transformation
        // The API returns coordinates based on 1280x960 image
        const scaleX = canvas.width / 1280;
        const scaleY = canvas.height / 960;

        // Set global opacity
        ctx.globalAlpha = settings.opacity;

        // Draw constellation lines first (behind stars)
        if (settings.showConstellations && constellationLines.length > 0) {
            console.log(`Drawing ${constellationLines.length} constellation lines`);
            drawConstellationLines(scaleX, scaleY);
        } else {
            console.log(`Not drawing lines: showConstellations=${settings.showConstellations}, lineCount=${constellationLines.length}`);
        }

        // Fine-tuning adjustments
        const centerX = canvas.width / 2;
        const centerY = canvas.height / 2;
        const rotationAdjust = settings.rotationAdjust * Math.PI / 180;

        // Draw each star
        stars.forEach(star => {
            // Skip stars fainter than the current magnitude limit
            if (star.mag > settings.magnitudeLimit) return;

            // Scale with custom scale factors and flip Y
            let x = star.x * scaleX * settings.scaleX;
            let y = canvas.height - (star.y * scaleY * settings.scaleY);  // Flip Y axis

            // Adjust for scale center offset
            x = centerX + (x - centerX * settings.scaleX);
            y = centerY + (y - centerY * settings.scaleY);

            // Apply rotation adjustment around center
            const dx = x - centerX;
            const dy = y - centerY;
            x = centerX + dx * Math.cos(rotationAdjust) - dy * Math.sin(rotationAdjust);
            y = centerY + dx * Math.sin(rotationAdjust) + dy * Math.cos(rotationAdjust);

            // Apply offset
            x += settings.offsetX * scaleX;
            y += settings.offsetY * scaleY;

            // Check if within canvas bounds
            if (x < 0 || x > canvas.width || y < 0 || y > canvas.height) return;

            // Calculate star size based on magnitude (brighter = larger)
            // Magnitude scale: -1.5 to 4.0, we want sizes 8 to 2 pixels
            const minSize = 1.5;
            const maxSize = 6;
            const minMag = -1.5;
            const maxMag = 4.0;
            const size = maxSize - ((star.mag - minMag) / (maxMag - minMag)) * (maxSize - minSize);

            // Draw star
            drawStar(x, y, Math.max(minSize, size), settings.color);

            // Draw name for bright stars
            if (settings.showNames && star.mag < NAME_MAG_THRESHOLD && star.name) {
                drawStarName(x, y, star.name, size);
            }
        });

        // Reset global alpha
        ctx.globalAlpha = 1.0;
    }

    /**
     * Draw a single star
     */
    function drawStar(x, y, size, color) {
        ctx.beginPath();
        ctx.arc(x, y, size, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();

        // Add a subtle glow for brighter stars
        if (size > 3) {
            ctx.beginPath();
            ctx.arc(x, y, size * 1.5, 0, Math.PI * 2);
            const gradient = ctx.createRadialGradient(x, y, size * 0.5, x, y, size * 1.5);
            gradient.addColorStop(0, color);
            gradient.addColorStop(1, 'transparent');
            ctx.fillStyle = gradient;
            ctx.fill();
        }
    }

    /**
     * Draw star name label
     */
    function drawStarName(x, y, name, starSize) {
        const offset = starSize + 4;

        ctx.font = '11px Arial, sans-serif';
        ctx.fillStyle = settings.color;
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';

        // Add text shadow for readability
        ctx.shadowColor = 'rgba(0, 0, 0, 0.8)';
        ctx.shadowBlur = 3;
        ctx.shadowOffsetX = 1;
        ctx.shadowOffsetY = 1;

        ctx.fillText(name, x + offset, y);

        // Reset shadow
        ctx.shadowColor = 'transparent';
        ctx.shadowBlur = 0;
        ctx.shadowOffsetX = 0;
        ctx.shadowOffsetY = 0;
    }

    /**
     * Draw constellation lines
     */
    function drawConstellationLines(scaleX, scaleY) {
        ctx.strokeStyle = settings.color;
        ctx.lineWidth = 1.5;
        ctx.globalAlpha = settings.opacity * 0.6; // Lines slightly more transparent

        const centerX = canvas.width / 2;
        const centerY = canvas.height / 2;
        const rotationAdjust = settings.rotationAdjust * Math.PI / 180;

        let drawnCount = 0;
        constellationLines.forEach(line => {
            // Scale with custom scale factors and flip Y
            let x1 = line.x1 * scaleX * settings.scaleX;
            let y1 = canvas.height - (line.y1 * scaleY * settings.scaleY);
            let x2 = line.x2 * scaleX * settings.scaleX;
            let y2 = canvas.height - (line.y2 * scaleY * settings.scaleY);

            // Adjust for scale center offset
            x1 = centerX + (x1 - centerX * settings.scaleX);
            y1 = centerY + (y1 - centerY * settings.scaleY);
            x2 = centerX + (x2 - centerX * settings.scaleX);
            y2 = centerY + (y2 - centerY * settings.scaleY);

            // Apply rotation adjustment around center
            let dx1 = x1 - centerX, dy1 = y1 - centerY;
            let dx2 = x2 - centerX, dy2 = y2 - centerY;
            x1 = centerX + dx1 * Math.cos(rotationAdjust) - dy1 * Math.sin(rotationAdjust);
            y1 = centerY + dx1 * Math.sin(rotationAdjust) + dy1 * Math.cos(rotationAdjust);
            x2 = centerX + dx2 * Math.cos(rotationAdjust) - dy2 * Math.sin(rotationAdjust);
            y2 = centerY + dx2 * Math.sin(rotationAdjust) + dy2 * Math.cos(rotationAdjust);

            // Apply offset
            x1 += settings.offsetX * scaleX;
            y1 += settings.offsetY * scaleY;
            x2 += settings.offsetX * scaleX;
            y2 += settings.offsetY * scaleY;

            // Check if line endpoints are within canvas bounds
            if (x1 < 0 || x1 > canvas.width || y1 < 0 || y1 > canvas.height) return;
            if (x2 < 0 || x2 > canvas.width || y2 < 0 || y2 > canvas.height) return;

            ctx.beginPath();
            ctx.moveTo(x1, y1);
            ctx.lineTo(x2, y2);
            ctx.stroke();
            drawnCount++;
        });

        console.log(`Actually drew ${drawnCount} constellation lines within bounds`);

        // Reset opacity for stars
        ctx.globalAlpha = settings.opacity;
    }

    /**
     * Update settings and re-render
     */
    function updateSettings(newSettings) {
        Object.assign(settings, newSettings);

        if (settings.enabled) {
            fetchStars();
        } else {
            clearCanvas();
        }
    }

    /**
     * Force refresh of star positions
     */
    function refresh() {
        if (settings.enabled) {
            fetchStars();
        }
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Export functions for external access
    window.StarMap = {
        refresh: refresh,
        updateSettings: updateSettings,
        loadSettings: loadSettings
    };

})();
