// Gallery page functionality
document.addEventListener('DOMContentLoaded', function() {
    const searchInput = document.getElementById('searchInput');
    const sortOption = document.getElementById('sortOption');
    const galleryGrid = document.getElementById('galleryGrid');

    if (searchInput && sortOption && galleryGrid) {
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
                    const exposureB = parseInt(a.getAttribute('data-exposure')) || 0;

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
    }
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
});

// Deletion Mode Functionality
document.addEventListener('DOMContentLoaded', function() {
    let deletionModeActive = false;
    const toggleButton = document.getElementById('toggleDeletionMode');
    const deletionPanel = document.getElementById('deletionPanel');
    const deleteSelectedBtn = document.getElementById('deleteSelected');
    const selectAllBtn = document.getElementById('selectAllDays');
    const deselectAllBtn = document.getElementById('deselectAllDays');
    const deletionStatus = document.getElementById('deletionStatus');
    const dayCheckboxes = document.querySelectorAll('.day-checkbox');
    const daySections = document.querySelectorAll('.day-section');

    // Toggle deletion mode
    if (toggleButton) {
        toggleButton.addEventListener('click', function() {
            deletionModeActive = !deletionModeActive;

            if (deletionModeActive) {
                toggleButton.textContent = 'Disable Deletion Mode';
                toggleButton.classList.remove('secondary-button');
                toggleButton.classList.add('danger-button');
                deletionPanel.classList.remove('hidden');

                // Show all checkboxes
                dayCheckboxes.forEach(checkbox => {
                    checkbox.style.display = 'inline-block';
                });
            } else {
                toggleButton.textContent = 'Enable Deletion Mode';
                toggleButton.classList.remove('danger-button');
                toggleButton.classList.add('secondary-button');
                deletionPanel.classList.add('hidden');

                // Hide all checkboxes and uncheck them
                dayCheckboxes.forEach(checkbox => {
                    checkbox.style.display = 'none';
                    checkbox.checked = false;
                });

                deletionStatus.textContent = '';
            }
        });
    }

    // Select all days
    if (selectAllBtn) {
        selectAllBtn.addEventListener('click', function() {
            dayCheckboxes.forEach(checkbox => {
                checkbox.checked = true;
            });
        });
    }

    // Deselect all days
    if (deselectAllBtn) {
        deselectAllBtn.addEventListener('click', function() {
            dayCheckboxes.forEach(checkbox => {
                checkbox.checked = false;
            });
        });
    }

    // Delete selected days
    if (deleteSelectedBtn) {
        deleteSelectedBtn.addEventListener('click', async function() {
            const selectedDays = [];

            dayCheckboxes.forEach(checkbox => {
                if (checkbox.checked) {
                    selectedDays.push(checkbox.dataset.day);
                }
            });

            if (selectedDays.length === 0) {
                deletionStatus.innerHTML = '<span class="error">Please select at least one day to delete.</span>';
                return;
            }

            // Calculate total images to be deleted
            let totalImages = 0;
            selectedDays.forEach(day => {
                const section = document.querySelector(`.day-section[data-day="${day}"]`);
                if (section) {
                    totalImages += parseInt(section.dataset.imageCount || 0);
                }
            });

            // Confirmation dialog
            const confirmMessage = `Are you sure you want to delete ${selectedDays.length} day(s) with approximately ${totalImages} image(s)?\n\nDays to delete:\n${selectedDays.join('\n')}\n\nThe latest image will be preserved.`;

            if (!confirm(confirmMessage)) {
                return;
            }

            // Show loading status
            deletionStatus.innerHTML = '<span class="info">Deleting images...</span>';
            deleteSelectedBtn.disabled = true;

            try {
                const response = await fetch('/api/delete_images', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        days: selectedDays
                    })
                });

                const result = await response.json();

                if (result.status === 'success') {
                    deletionStatus.innerHTML = `<span class="success">${result.message}</span>`;

                    // Remove deleted day sections from DOM
                    selectedDays.forEach(day => {
                        const section = document.querySelector(`.day-section[data-day="${day}"]`);
                        if (section && result.deleted_days.includes(day)) {
                            section.remove();
                        }
                    });

                    // Reload page after 2 seconds
                    setTimeout(() => {
                        window.location.reload();
                    }, 2000);
                } else {
                    deletionStatus.innerHTML = `<span class="error">Error: ${result.message}</span>`;
                }
            } catch (error) {
                deletionStatus.innerHTML = `<span class="error">Error: ${error.message}</span>`;
            } finally {
                deleteSelectedBtn.disabled = false;
            }
        });
    }
});