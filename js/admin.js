document.addEventListener('DOMContentLoaded', () => {
    const tableBody = document.getElementById('admin-table-body');
    const adminStatusFilter = document.getElementById('admin-status-filter');
    const adminSearchInput = document.getElementById('admin-search-input');
    
    let productsList = [];
    let stateData = {};

    if (adminStatusFilter) adminStatusFilter.addEventListener('change', () => renderAdminTable());
    if (adminSearchInput) adminSearchInput.addEventListener('input', () => renderAdminTable());

    const loadData = async () => {
        try {
            // Load base products
            const prodRes = await fetch('data/productos.json');
            const data = await prodRes.json();
            
            if (Array.isArray(data)) {
                productsList = data;
            } else if (data.productos && Array.isArray(data.productos)) {
                productsList = data.productos;
            } else {
                for (const key in data) {
                    if (Array.isArray(data[key])) {
                        productsList = data[key];
                        break;
                    }
                }
            }

            // Load states and prices
            try {
                const stateRes = await fetch('data/estado_productos.json');
                if(stateRes.ok) {
                    stateData = await stateRes.json();
                }
            } catch(e) {
                console.log("No se pudo cargar estado_productos.json (puede que esté vacío o no exista aún).");
            }

            renderAdminTable();

        } catch (error) {
            console.error('Error:', error);
            tableBody.innerHTML = `<tr><td colspan="5" style="color:red">Error al cargar los datos</td></tr>`;
        }
    };

    const renderAdminTable = () => {
        tableBody.innerHTML = '';
        
        let filteredList = productsList;
        
        // Filter by text
        const query = adminSearchInput ? adminSearchInput.value.toLowerCase().trim() : '';
        if (query) {
            filteredList = filteredList.filter(p => 
                p.titulo.toLowerCase().includes(query) || 
                p.id.toLowerCase().includes(query)
            );
        }

        // Filter by status
        const statusVal = adminStatusFilter ? adminStatusFilter.value : 'all';
        if (statusVal !== 'all') {
            filteredList = filteredList.filter(p => {
                const state = stateData[p.id] || {};
                const isSold = state.vendido === true;
                const hasPrice = state.precio !== undefined && state.precio !== null && String(state.precio).trim() !== '';

                if (statusVal === 'available') return !isSold;
                if (statusVal === 'sold') return isSold;
                if (statusVal === 'no-price') return !isSold && !hasPrice;
                return true;
            });
        }

        if (filteredList.length === 0) {
            tableBody.innerHTML = `<tr><td colspan="7" style="text-align: center;">No se encontraron productos.</td></tr>`;
            return;
        }
        
        filteredList.forEach(product => {
            const { id, titulo } = product;
            const imageUrl = `images/${id}_01.jpg`;
            const amazonUrl = product.url || `https://www.amazon.com.mx/dp/${id}`;
            
            const state = stateData[id] || { precio: '', vendido: false, amazon_precio: '' };
            const isSold = state.vendido;
            const amazonPrice = state.amazon_precio || '---';
            
            // Sugerencia de 20% menos para el placeholder si no tiene precio
            let placeholderPrice = "0";
            if (state.amazon_precio) {
                const cleanedAmz = Number(String(state.amazon_precio).replace(/[^0-9.]/g, ''));
                if (!isNaN(cleanedAmz) && cleanedAmz > 0) {
                    placeholderPrice = Math.round(cleanedAmz * 0.8);
                }
            }
            
            const tr = document.createElement('tr');
            
            tr.innerHTML = `
                <td>
                    <a href="${amazonUrl}" target="_blank" rel="noopener noreferrer" class="admin-thumbnail-link" title="Ver foto y producto en Amazon">
                        <img src="${imageUrl}" alt="img" class="admin-thumbnail" onerror="this.src='https://via.placeholder.com/60'">
                    </a>
                </td>
                <td style="max-width:320px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${titulo}">
                    <a href="${amazonUrl}" target="_blank" rel="noopener noreferrer" class="admin-product-link" title="Abrir ficha en Amazon: ${titulo}">
                        <span class="product-asin-tag"><strong>${id}</strong> <span style="font-size: 0.75rem;">↗</span></span><br>
                        <small class="product-link-title">${titulo}</small>
                    </a>
                </td>
                <td>
                    <span class="status-badge ${isSold ? 'status-sold' : 'status-available'}" id="badge-${id}">
                        ${isSold ? 'VENDIDO' : 'DISPONIBLE'}
                    </span>
                </td>
                <td style="font-weight: 600; color: #64748b;">
                    ${amazonPrice}
                </td>
                <td>
                    <input type="text" class="price-input" id="folio-${id}" value="${state.folio || ''}" placeholder="#Lote" style="width: 80px;">
                </td>
                <td>
                    <input type="number" step="1" class="price-input" id="price-${id}" value="${state.precio !== undefined && state.precio !== null && state.precio !== '' ? Math.round(Number(state.precio)) : ''}" placeholder="${placeholderPrice}">
                    <button class="action-btn save-btn" onclick="saveData('${id}')">Guardar</button>
                </td>
                <td>
                    <button class="action-btn toggle-btn ${isSold ? '' : 'is-sold'}" id="toggle-${id}" onclick="toggleSold('${id}')">
                        ${isSold ? 'Marcar Disponible' : 'Marcar Vendido'}
                    </button>
                </td>
            `;
            
            tableBody.appendChild(tr);
        });
    };

    window.saveData = async (id) => {
        const priceInput = document.getElementById(`price-${id}`);
        const folioInput = document.getElementById(`folio-${id}`);
        const rawPrice = priceInput.value.trim();
        const newPrice = rawPrice !== '' ? Math.round(Number(rawPrice)) : '';
        const newFolio = folioInput.value.trim();
        
        await updateAPI(id, { precio: newPrice, folio: newFolio });
        priceInput.value = newPrice;
        alert('Datos guardados correctamente');
    };

    window.toggleSold = async (id) => {
        if(!stateData[id]) stateData[id] = { vendido: false };
        const newState = !stateData[id].vendido;
        stateData[id].vendido = newState;
        
        await updateAPI(id, { vendido: newState });
        renderAdminTable(); // re-render to update UI
    };

    const updateAPI = async (id, dataObj) => {
        dataObj.id = id;
        try {
            const response = await fetch('/api/update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(dataObj)
            });
            if(!response.ok) throw new Error("Error en servidor");
            
            // update local state cache
            if(!stateData[id]) stateData[id] = {};
            if('precio' in dataObj) stateData[id].precio = dataObj.precio;
            if('vendido' in dataObj) stateData[id].vendido = dataObj.vendido;
            if('folio' in dataObj) stateData[id].folio = dataObj.folio;
            
        } catch(e) {
            console.error(e);
            alert("Hubo un error guardando los datos. Asegúrate de que el servidor python (server.py) esté corriendo.");
        }
    };

    loadData();
});
