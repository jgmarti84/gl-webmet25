/**
 * Webmet25 Radar Viewer Map JavaScript
 * Displays radar images as overlays on a Leaflet map
 */

// Initialize map centered on Argentina (where RMA3 is)
const map = L.map('map').setView([-24.73, -60.55], 5);

// Add OpenStreetMap tile layer
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
}).addTo(map);

// Layer groups for different map elements
const radarLayer = L.layerGroup().addTo(map);  // Radar station markers
const imagesLayer = L.layerGroup().addTo(map);  // Radar image overlays

// Store current state
let currentImages = [];
let currentImageOverlays = [];

/**
 * Load available radars and populate the radar select dropdown
 */
function loadRadars() {
    fetch('/radar_api/radares/return_codes/')
        .then(response => response.json())
        .then(codes => {
            const select = document.getElementById('radar-select');
            codes.forEach(code => {
                const option = document.createElement('option');
                option.value = code;
                option.textContent = code;
                select.appendChild(option);
            });
        })
        .catch(error => console.error('Error loading radars:', error));
}

/**
 * Load available products (polarimetric variables) and populate dropdown
 */
function loadProducts() {
    // For simplicity, hardcode common radar products
    const products = ['DBZH', 'VR', 'RHOHV', 'KDP', 'ZDR', 'VRAD', 'WRAD', 'COLMAX'];
    const select = document.getElementById('product-select');
    products.forEach(product => {
        const option = document.createElement('option');
        option.value = product;
        option.textContent = product;
        select.appendChild(option);
    });
}

/**
 * Clear all image overlays from the map
 */
function clearImages() {
    currentImageOverlays.forEach(overlay => {
        imagesLayer.removeLayer(overlay);
    });
    currentImageOverlays = [];
    currentImages = [];
    document.getElementById('image-count').textContent = '0';
}

/**
 * Load radar images based on current filter settings and display them on the map
 */
function loadImages() {
    const radarCode = document.getElementById('radar-select').value;
    const product = document.getElementById('product-select').value;
    const dateFrom = document.getElementById('date-from').value;
    const dateTo = document.getElementById('date-to').value;

    // Validate date inputs
    if (!dateFrom || !dateTo) {
        alert('Please select both "From" and "To" dates');
        return;
    }

    // Convert datetime-local to ISO 8601 format with Z (UTC)
    const dateFromISO = new Date(dateFrom).toISOString();
    const dateToISO = new Date(dateTo).toISOString();

    // Build API URL with query parameters
    let url = '/radar_api/images_radares/filtered/?';
    url += 'date_from=' + encodeURIComponent(dateFromISO);
    url += '&date_to=' + encodeURIComponent(dateToISO);
    if (radarCode) url += '&radar_code=' + encodeURIComponent(radarCode);
    if (product) url += '&polarimetric_var=' + encodeURIComponent(product);

    console.log('Fetching images from:', url);

    fetch(url)
        .then(response => response.json())
        .then(data => {
            console.log('Received', data.count, 'images');
            currentImages = data.images || [];

            // Clear existing overlays
            clearImages();

            // Add new overlays
            data.images.forEach(image => {
                addImageOverlay(image);
            });

            // Update info panel
            document.getElementById('image-count').textContent = data.count;
            updateInfoPanel(data);
        })
        .catch(error => {
            console.error('Error loading images:', error);
            alert('Error loading images: ' + error);
        });
}

/**
 * Add a single radar image as an overlay on the map
 */
function addImageOverlay(image) {
    // Create a custom popup with image preview
    const popupContent = `
        <div style="width: 400px; max-width: 90vw;">
            <h4>${image.radar_code} - ${image.polarimetric_var}</h4>
            <p><strong>Date:</strong> ${new Date(image.date).toLocaleString()}</p>
            <p><strong>Sweep:</strong> ${image.sweep}°</p>
            <img src="${image.product_image_url}" style="width: 100%; border: 1px solid #ccc; margin: 10px 0;">
            <p style="font-size: 11px; color: #666;">Location: ${image.radar_lat.toFixed(3)}, ${image.radar_long.toFixed(3)}</p>
        </div>
    `;

    // Create a marker at the radar location
    const marker = L.circleMarker(
        [image.radar_lat, image.radar_long],
        {
            radius: 12,
            fillColor: '#3498db',
            color: '#fff',
            weight: 2,
            opacity: 0.8,
            fillOpacity: 0.7
        }
    );

    marker.bindPopup(popupContent, { maxWidth: 500 });
    marker.on('click', function() {
        // Optionally: highlight on click or fetch full image
        console.log('Image clicked:', image);
    });

    imagesLayer.addLayer(marker);
    currentImageOverlays.push(marker);
}

/**
 * Update the info panel with image metadata and radar details
 */
function updateInfoPanel(data) {
    const infoDiv = document.getElementById('product-info');
    let html = `<p><strong>${data.count} images loaded</strong></p>`;
    
    if (data.radars && Object.keys(data.radars).length > 0) {
        html += '<p><strong>Radars:</strong></p><ul>';
        Object.values(data.radars).forEach(radar => {
            html += `<li>${radar.code}: ${radar.title} (${radar.lat.toFixed(2)}, ${radar.long.toFixed(2)})</li>`;
        });
        html += '</ul>';
    }

    if (data.images && data.images.length > 0) {
        const products = [...new Set(data.images.map(img => img.polarimetric_var))];
        html += '<p><strong>Products:</strong> ' + products.join(', ') + '</p>';
        
        const dateMin = new Date(Math.min(...data.images.map(img => new Date(img.date))));
        const dateMax = new Date(Math.max(...data.images.map(img => new Date(img.date))));
        html += `<p><strong>Time Range:</strong><br>${dateMin.toLocaleString()}<br>to<br>${dateMax.toLocaleString()}</p>`;
    }

    infoDiv.innerHTML = html;
}

/**
 * Set default date range (last 2 hours from now)
 */
function setDefaultDateRange() {
    const now = new Date();
    const twoHoursAgo = new Date(now.getTime() - 2 * 60 * 60 * 1000);

    // Format as datetime-local (YYYY-MM-DDTHH:mm)
    const formatDateTime = (d) => {
        const year = d.getFullYear();
        const month = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        const hours = String(d.getHours()).padStart(2, '0');
        const minutes = String(d.getMinutes()).padStart(2, '0');
        return `${year}-${month}-${day}T${hours}:${minutes}`;
    };

    document.getElementById('date-from').value = formatDateTime(twoHoursAgo);
    document.getElementById('date-to').value = formatDateTime(now);
}

/**
 * Initialize the map and set up event listeners
 */
function initMap() {
    // Set default date range
    setDefaultDateRange();

    // Load available options
    loadRadars();
    loadProducts();

    // Set up button click handlers
    document.getElementById('load-images-btn').addEventListener('click', loadImages);
    document.getElementById('clear-images-btn').addEventListener('click', clearImages);

    // Optional: Auto-load images on page load (first 2 hours)
    // Uncomment to enable:
    // loadImages();
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initMap);
} else {
    initMap();
}