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
        magnitudeLimit: 4.0
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

        // Draw each star
        stars.forEach(star => {
            // Skip stars fainter than the current magnitude limit
            if (star.mag > settings.magnitudeLimit) return;

            // Transform coordinates
            const x = star.x * scaleX;
            const y = star.y * scaleY;

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

        let drawnCount = 0;
        constellationLines.forEach(line => {
            const x1 = line.x1 * scaleX;
            const y1 = line.y1 * scaleY;
            const x2 = line.x2 * scaleX;
            const y2 = line.y2 * scaleY;

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
