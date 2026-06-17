// Estado global de la aplicación
const state = {
    userLocation: { lat: -32.4846, lon: -58.2322 }, // Concepción del Uruguay, Entre Ríos
    searchRadius: 5.0, // km
    activeCategory: 'all',
    map: null,
    userMarker: null,
    radiusCircle: null,
    poiMarkers: [],
    categories: {}
};

// Mapeo de categorías a iconos de FontAwesome
const categoryIcons = {
    cervecerias: 'fa-beer-mug-empty',
    universidades: 'fa-graduation-cap',
    farmacias: 'fa-pills',
    emergencias: 'fa-truck-medical',
    supermercados: 'fa-cart-shopping'
};

// URL Base de la API (relativa gracias al proxy de Nginx)
const API_BASE = '/api';

// Inicialización cuando carga la página
document.addEventListener('DOMContentLoaded', async () => {
    // 1. Inicializar Mapa Leaflet
    initMap();

    // 2. Verificar estado de la API
    await checkBackendStatus();

    // 3. Registrar Listeners de Eventos
    setupEventListeners();

    // 4. Realizar búsqueda inicial
    await searchPOIs();
});

// Inicializar el mapa de Leaflet
function initMap() {
    // Crear mapa centrado en la ubicación inicial del usuario
    state.map = L.map('map').setView([state.userLocation.lat, state.userLocation.lon], 13);

    // Cargar capa de mapa base (OpenStreetMap tiles)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(state.map);

    // Marcador del usuario (Círculo azul personalizado)
    const userIcon = L.divIcon({
        className: 'user-location-marker',
        html: '<div class="user-pulse"></div>',
        iconSize: [20, 20],
        iconAnchor: [10, 10]
    });

    state.userMarker = L.marker([state.userLocation.lat, state.userLocation.lon], {
        icon: userIcon,
        draggable: true
    }).addTo(state.map);

    // Círculo de radio alrededor del usuario
    state.radiusCircle = L.circle([state.userLocation.lat, state.userLocation.lon], {
        radius: state.searchRadius * 1000, // metros
        color: '#4f46e5',
        fillColor: '#4f46e5',
        fillOpacity: 0.08,
        weight: 1.5
    }).addTo(state.map);

    // Evento al arrastrar el marcador del usuario
    state.userMarker.on('dragend', async (e) => {
        const position = state.userMarker.getLatLng();
        await updateUserLocation(position.lat, position.lng);
    });

    // Evento al hacer clic en el mapa
    state.map.on('click', async (e) => {
        await updateUserLocation(e.latlng.lat, e.latlng.lng);
    });
}

// Configurar los listeners del DOM
function setupEventListeners() {
    // Slider del Radio de Búsqueda
    const radiusSlider = document.getElementById('search-radius');
    const radiusValText = document.getElementById('radius-val');
    const radiusLabelText = document.getElementById('current-radius-label');

    radiusSlider.addEventListener('input', (e) => {
        const radius = parseFloat(e.target.value);
        state.searchRadius = radius;
        radiusValText.textContent = radius;
        radiusLabelText.textContent = radius;
        
        // Actualizar el círculo visual en el mapa
        if (state.radiusCircle) {
            state.radiusCircle.setRadius(radius * 1000);
        }
    });

    radiusSlider.addEventListener('change', async () => {
        await searchPOIs();
    });

    // Filtros por Categoría
    const filters = document.querySelectorAll('.filter-badge');
    filters.forEach(filter => {
        filter.addEventListener('click', async (e) => {
            filters.forEach(f => f.classList.remove('active'));
            
            // Si hace clic en el badge o en el icono dentro del badge
            const target = e.currentTarget;
            target.classList.add('active');
            
            state.activeCategory = target.dataset.category;
            await searchPOIs();
        });
    });

    // Formulario de Registro de POI
    const addPoiForm = document.getElementById('add-poi-form');
    addPoiForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const category = document.getElementById('poi-category').value;
        const name = document.getElementById('poi-name').value.trim();
        const latitude = parseFloat(document.getElementById('poi-lat').value);
        const longitude = parseFloat(document.getElementById('poi-lon').value);

        if (!category || !name || isNaN(latitude) || isNaN(longitude)) {
            showToast('Por favor, completa todos los campos correctamente.', 'error');
            return;
        }

        try {
            const response = await fetch(`${API_BASE}/poi`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ category, name, latitude, longitude })
            });

            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.detail || 'Error al guardar el punto de interés');
            }

            showToast('Punto de interés guardado en Redis correctamente', 'success');
            
            // Resetear campos de texto pero mantener coordenadas
            document.getElementById('poi-name').value = '';
            document.getElementById('poi-category').selectedIndex = 0;
            
            // Refrescar la búsqueda
            await searchPOIs();
        } catch (error) {
            showToast(error.message, 'error');
        }
    });

    // Botón para cerrar panel de distancia
    document.getElementById('close-geodist-btn').addEventListener('click', () => {
        document.getElementById('geodist-panel').classList.add('hidden');
    });
}

// Actualizar la ubicación del usuario
async function updateUserLocation(lat, lon) {
    state.userLocation.lat = lat;
    state.userLocation.lon = lon;

    // Actualizar campos en UI
    document.getElementById('user-lat').textContent = lat.toFixed(6);
    document.getElementById('user-lon').textContent = lon.toFixed(6);
    
    // Auto-completar formulario para registrar nuevo lugar
    document.getElementById('poi-lat').value = lat.toFixed(6);
    document.getElementById('poi-lon').value = lon.toFixed(6);

    // Mover marcador y círculo
    state.userMarker.setLatLng([lat, lon]);
    state.radiusCircle.setLatLng([lat, lon]);

    // Ocultar panel de GEODIST viejo al cambiar de ubicación
    document.getElementById('geodist-panel').classList.add('hidden');

    // Buscar POIs en la nueva zona
    await searchPOIs();
}

// Buscar POIs cercanos mediante la API
async function searchPOIs() {
    const { lat, lon } = state.userLocation;
    const radius = state.searchRadius;
    const category = state.activeCategory === 'all' ? '' : state.activeCategory;

    // Limpiar marcadores viejos de POI
    state.poiMarkers.forEach(m => state.map.removeLayer(m));
    state.poiMarkers = [];

    try {
        let url = `${API_BASE}/poi/search?lat=${lat}&lon=${lon}&radius_km=${radius}`;
        if (category) {
            url += `&category=${category}`;
        }

        const response = await fetch(url);
        if (!response.ok) throw new Error('Error al consultar puntos de interés');
        
        const data = await response.json();
        renderPOIs(data);
    } catch (error) {
        console.error(error);
        showToast('Error al conectar con la base de datos de turismo', 'error');
    }
}

// Renderizar la lista de POIs y agregarlos al mapa
function renderPOIs(pois) {
    const listContainer = document.getElementById('poi-list');
    const emptyState = document.getElementById('no-results-msg');
    
    listContainer.innerHTML = '';

    if (pois.length === 0) {
        emptyState.classList.remove('hidden');
        return;
    }

    emptyState.classList.add('hidden');

    pois.forEach(poi => {
        // --- 1. Agregar marcador al mapa ---
        const iconClass = categoryIcons[poi.category] || 'fa-location-dot';
        
        // Crear DivIcon personalizado para que use los colores del frontend
        const poiIcon = L.divIcon({
            className: `custom-marker ${poi.category}`,
            html: `<i class="fa-solid ${iconClass}"></i>`,
            iconSize: [30, 30],
            iconAnchor: [15, 15],
            popupAnchor: [0, -15]
        });

        const marker = L.marker([poi.latitude, poi.longitude], { icon: poiIcon }).addTo(state.map);
        
        // Agregar Popup con botón de distancia
        const popupContent = `
            <div style="font-family: 'Outfit', sans-serif;">
                <strong style="font-size: 1rem; color: #fff;">${poi.name}</strong><br/>
                <span style="font-size: 0.8rem; color: #9ca3af;">Categoría: ${poi.category_label}</span><br/>
                <button onclick="calculateExactDistance('${poi.category}', '${poi.name.replace(/'/g, "\\'")}')" 
                        style="margin-top: 0.5rem; background: #4f46e5; color: white; border: none; padding: 0.35rem 0.65rem; border-radius: 6px; cursor: pointer; font-size: 0.75rem; font-weight: 600; width: 100%;">
                    <i class="fa-solid fa-calculator"></i> Calcular GEODIST
                </button>
            </div>
        `;
        
        marker.bindPopup(popupContent);
        state.poiMarkers.push(marker);

        // --- 2. Agregar elemento a la lista en el DOM ---
        const distText = poi.distance_meters > 1000 
            ? `${(poi.distance_meters / 1000).toFixed(2)} km` 
            : `${poi.distance_meters.toFixed(0)} metros`;

        const li = document.createElement('li');
        li.className = 'poi-item';
        li.innerHTML = `
            <div class="poi-item-left">
                <span class="poi-name-txt">${poi.name}</span>
                <span class="poi-cat-badge ${poi.category}">
                    <i class="fa-solid ${iconClass}"></i> ${poi.category_label}
                </span>
            </div>
            <div class="poi-item-right">
                <span class="poi-distance"><i class="fa-solid fa-route"></i> ${distText}</span>
                <button class="btn-calc-dist" onclick="calculateExactDistance('${poi.category}', '${poi.name.replace(/'/g, "\\'")}')">
                    Calcular GEODIST
                </button>
            </div>
        `;
        
        // Al hacer clic en el item, centrar el mapa en él
        li.addEventListener('click', (e) => {
            if (e.target.tagName !== 'BUTTON') {
                state.map.setView([poi.latitude, poi.longitude], 15);
                marker.openPopup();
            }
        });

        listContainer.appendChild(li);
    });
}

// Calcular distancia exacta usando Redis GEODIST
async function calculateExactDistance(category, name) {
    const { lat, lon } = state.userLocation;

    try {
        const response = await fetch(`${API_BASE}/poi/distance?lat=${lat}&lon=${lon}&category=${category}&name=${encodeURIComponent(name)}`);
        if (!response.ok) throw new Error('Error al calcular la distancia');
        
        const data = await response.json();
        
        // Actualizar UI del panel de GEODIST
        document.getElementById('active-poi-name').textContent = data.name;
        
        // Cambiar icono en el flujo del panel
        const iconClass = categoryIcons[category] || 'fa-location-dot';
        const activePoiIconDiv = document.getElementById('active-poi-icon');
        activePoiIconDiv.className = `flow-node active-poi-node ${category}`;
        activePoiIconDiv.innerHTML = `<i class="fa-solid ${iconClass}"></i>`;

        // Mostrar distancia
        const distanceVal = data.distance_meters;
        if (distanceVal >= 1000) {
            document.getElementById('exact-distance-val').textContent = (distanceVal / 1000).toFixed(3);
            document.querySelector('.geodist-unit').textContent = 'kilómetros';
        } else {
            document.getElementById('exact-distance-val').textContent = distanceVal.toFixed(1);
            document.querySelector('.geodist-unit').textContent = 'metros';
        }

        // Mostrar logs de los comandos en el log
        document.getElementById('redis-cat').textContent = category;
        document.getElementById('redis-poi').textContent = name;

        // Mostrar panel
        document.getElementById('geodist-panel').classList.remove('hidden');
        
        // Scroll suave al panel
        document.getElementById('geodist-panel').scrollIntoView({ behavior: 'smooth', block: 'nearest' });

        showToast(`Distancia exacta con ${name} calculada.`, 'success');
    } catch (error) {
        console.error(error);
        showToast('No se pudo calcular la distancia exacta con Redis.', 'error');
    }
}

// Verificar que el backend esté online y conectado a Redis
async function checkBackendStatus() {
    const statusDot = document.getElementById('backend-status');
    const statusText = document.getElementById('backend-status-text');

    try {
        const response = await fetch(`${API_BASE.replace('/api', '')}/health`);
        if (!response.ok) throw new Error('Salud de backend fallida');
        
        const data = await response.json();
        if (data.status === 'online' && data.redis_connected) {
            statusDot.className = 'status-dot online';
            statusText.textContent = 'Servicios Online (Redis OK)';
        } else {
            statusDot.className = 'status-dot offline';
            statusText.textContent = 'Backend degraded (Redis desconectado)';
            showToast('Redis no está respondiendo', 'error');
        }
    } catch (error) {
        statusDot.className = 'status-dot offline';
        statusText.textContent = 'Servidor Offline';
        showToast('No se puede conectar al servidor backend', 'error');
    }
}

// Mostrar notificaciones Toast
function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast ${type}`;
    toast.classList.remove('hidden');

    // Ocultar después de 3.5 segundos
    setTimeout(() => {
        toast.classList.add('hidden');
    }, 3500);
}

// Exponer la función para que Leaflet popups y la lista la puedan llamar desde HTML
window.calculateExactDistance = calculateExactDistance;
window.renderPOIs = renderPOIs;
