// Auto-refresh functionality for the latest image page
document.addEventListener('DOMContentLoaded', function() {
    const autoRefreshCheckbox = document.getElementById('autoRefresh');
    const refreshIntervalInput = document.getElementById('refreshInterval');
    const manualRefreshBtn = document.getElementById('manualRefresh');
    
    if (!autoRefreshCheckbox || !refreshIntervalInput) return;
    
    let refreshTimer;
    
    function refreshPage() {
        location.reload();
    }
    
    function startAutoRefresh() {
        if (refreshTimer) {
            clearTimeout(refreshTimer);
        }
        
        if (autoRefreshCheckbox.checked) {
            const interval = Math.max(5, parseInt(refreshIntervalInput.value, 10)) * 1000;
            refreshTimer = setTimeout(refreshPage, interval);
        }
    }
    
    // Event listeners
    autoRefreshCheckbox.addEventListener('change', startAutoRefresh);
    
    refreshIntervalInput.addEventListener('change', function() {
        if (autoRefreshCheckbox.checked) {
            startAutoRefresh();
        }
    });
    
    if (manualRefreshBtn) {
        manualRefreshBtn.addEventListener('click', refreshPage);
    }
    
    // Initial start of auto-refresh if enabled
    startAutoRefresh();
});