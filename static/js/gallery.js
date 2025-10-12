// Gallery page functionality
document.addEventListener('DOMContentLoaded', function() {
    const searchInput = document.getElementById('searchInput');
    const sortOption = document.getElementById('sortOption');
    const galleryGrid = document.getElementById('galleryGrid');
    
    if (!searchInput || !sortOption || !galleryGrid) return;
    
    const galleryItems = Array.from(galleryGrid.querySelectorAll('.gallery-item'));
    
    // Filter gallery items based on search input
    function filterGallery() {
        const searchTerm = searchInput.value.toLowerCase();
        
        galleryItems.forEach(item => {
            const filename = item.getAttribute('data-filename').toLowerCase();
            if (filename.includes(searchTerm)) {
                item.style.display = 'block';
            } else {
                item.style.display = 'none';
            }
        });
    }
    
    // Sort gallery items
    function sortGallery() {
        const sortValue = sortOption.value;
        
        const sortedItems = galleryItems.sort((a, b) => {
            const filenameA = a.getAttribute('data-filename');
            const filenameB = b.getAttribute('data-filename');
            
            if (sortValue === 'date-desc' || sortValue === 'date-asc') {
                const timestampA = a.getAttribute('data-timestamp') || filenameA;
                const timestampB = b.getAttribute('data-timestamp') || filenameB;
                
                return sortValue === 'date-desc' 
                    ? timestampB.localeCompare(timestampA) 
                    : timestampA.localeCompare(timestampB);
            }
            
            if (sortValue === 'exposure-desc' || sortValue === 'exposure-asc') {
                const exposureA = parseInt(a.getAttribute('data-exposure')) || 0;
                const exposureB = parseInt(b.getAttribute('data-exposure')) || 0;
                
                return sortValue === 'exposure-desc' 
                    ? exposureB - exposureA 
                    : exposureA - exposureB;
            }
            
            return 0;
        });
        
        // Remove and re-append items in sorted order
        sortedItems.forEach(item => galleryGrid.appendChild(item));
    }
    
    // Event listeners
    searchInput.addEventListener('input', filterGallery);
    sortOption.addEventListener('change', sortGallery);
    
    // Initial sort
    sortGallery();
});

// Function to toggle day sections
function toggleDaySection(header) {
    const section = header.parentElement;
    section.classList.toggle('collapsed');
}

// Initialize day sections (collapsed or expanded)
document.addEventListener('DOMContentLoaded', function() {
    // Optional: Collapse all sections except the first one on page load
    const daySections = document.querySelectorAll('.day-section');

    if (daySections.length > 0) {
        // Leave first day expanded, collapse the rest
        for (let i = 1; i < daySections.length; i++) {
            daySections[i].classList.add('collapsed');
        }
    }

    // Initialize the search and sort functionality from before
    // (existing code remains here)
});