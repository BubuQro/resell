// Escapa texto antes de insertarlo como HTML (títulos con comillas como 15.6" rompían la tabla)
const escapeHtml = (value) => String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

const ADMIN_PLACEHOLDER_IMG = 'data:image/svg+xml,' + encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="60" height="60"><rect width="60" height="60" fill="#F3F4F4"/>' +
    '<text x="30" y="34" font-family="sans-serif" font-size="9" fill="#8A8F8F" text-anchor="middle">Sin foto</text></svg>'
);
window.ADMIN_PLACEHOLDER_IMG = ADMIN_PLACEHOLDER_IMG;

document.addEventListener('DOMContentLoaded', () => {
    const tableBody = document.getElementById('admin-table-body');
    const adminStatusFilter = document.getElementById('admin-status-filter');
    const adminSearchInput = document.getElementById('admin-search-input');
    const toastContainer = document.getElementById('admin-toast-container');
    
    let productsList = [];
    let stateData = {};
    const statusTimers = {};

    if (adminStatusFilter) adminStatusFilter.addEventListener('change', () => renderAdminTable());
    if (adminSearchInput) adminSearchInput.addEventListener('input', () => renderAdminTable());

    // Muestra un aviso flotante a un costado que desaparece solo sin requerir clic
    // action = { label, onClick }: botón opcional (p. ej. "Deshacer"). Es solo un atajo:
    // la misma acción siempre está disponible en la fila del producto.
    const showSideToast = (message, type = 'success', action = null) => {
        if (!toastContainer) return;
        const toast = document.createElement('div');
        toast.className = `admin-side-toast ${type === 'error' ? 'error' : (type === 'info' ? 'info' : '')}`;
        let icon = '✅';
        if (type === 'error') icon = '⚠️';
        if (type === 'info') icon = '⏳';
        toast.innerHTML = `<span aria-hidden="true">${icon}</span><span>${escapeHtml(message)}</span>`;

        const dismiss = () => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(20px)';
            setTimeout(() => toast.remove(), 250);
        };

        let timer;
        const schedule = (ms) => { clearTimeout(timer); timer = setTimeout(dismiss, ms); };

        if (action) {
            toast.classList.add('has-action');
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'toast-action';
            btn.textContent = action.label;
            btn.addEventListener('click', () => { dismiss(); action.onClick(); });
            toast.append(btn);
            // No cerrar mientras el foco o el puntero estén en el aviso
            toast.addEventListener('focusin', () => clearTimeout(timer));
            toast.addEventListener('focusout', () => schedule(3000));
            toast.addEventListener('pointerenter', () => clearTimeout(timer));
            toast.addEventListener('pointerleave', () => schedule(3000));
        }

        toastContainer.appendChild(toast);
        schedule(action ? 7000 : 2500);
    };

    // ---------- Contadores (también filtran la tabla) ----------
    const summaryButtons = [...document.querySelectorAll('.summary-btn[data-filter]')];
    const updateSummary = () => {
        let noPrice = 0, available = 0, sold = 0;
        productsList.forEach(p => {
            const st = stateData[p.id] || {};
            const hasPrice = st.precio !== undefined && st.precio !== null && String(st.precio).trim() !== '';
            if (st.vendido === true) sold++;
            else { available++; if (!hasPrice) noPrice++; }
        });
        const set = (id, n) => { const el = document.getElementById(id); if (el) el.textContent = n; };
        set('count-no-price', noPrice);
        set('count-available', available);
        set('count-sold', sold);
        set('count-all', productsList.length);
        const warn = document.querySelector('.summary-btn[data-filter="no-price"]');
        if (warn) warn.classList.toggle('is-warning', noPrice > 0);
        const current = adminStatusFilter ? adminStatusFilter.value : 'all';
        summaryButtons.forEach(b => b.setAttribute('aria-pressed', String(b.dataset.filter === current)));
    };
    summaryButtons.forEach(btn => btn.addEventListener('click', () => {
        if (adminStatusFilter) adminStatusFilter.value = btn.dataset.filter;
        renderAdminTable();
    }));

    // Muestra el indicador de guardado justo al costado del input/botón de la fila
    const showInlineRowStatus = (id, text, type = 'success', autoHide = true) => {
        const badge = document.getElementById(`save-status-${id}`);
        if (!badge) return;

        if (statusTimers[id]) {
            clearTimeout(statusTimers[id]);
        }

        badge.textContent = text;
        badge.className = `inline-save-status visible ${type}`;

        if (autoHide) {
            statusTimers[id] = setTimeout(() => {
                badge.classList.remove('visible');
            }, 2200);
        }
    };

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
            tableBody.innerHTML = `<tr><td colspan="7" style="color:red">Error al cargar los datos</td></tr>`;
        }
    };

    const renderAdminTable = () => {
        tableBody.innerHTML = '';
        updateSummary();
        
        let filteredList = productsList;
        
        // Filter by text
        const query = adminSearchInput ? adminSearchInput.value.toLowerCase().trim() : '';
        if (query) {
            filteredList = filteredList.filter(p => {
                const folio = stateData[p.id] && stateData[p.id].folio ? String(stateData[p.id].folio).toLowerCase() : '';
                return String(p.titulo || '').toLowerCase().includes(query) ||
                    String(p.id || '').toLowerCase().includes(query) ||
                    folio === query;
            });
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
            const msg = query
                ? 'Ningún producto coincide con tu búsqueda.'
                : statusVal === 'no-price'
                    ? 'Todos los productos disponibles ya tienen precio.'
                    : 'No hay productos en esta vista.';
            tableBody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 28px;">${msg}</td></tr>`;
            return;
        }
        
        const fragment = document.createDocumentFragment();
        filteredList.forEach(product => {
            const { id } = product;
            if (!/^[A-Za-z0-9_-]+$/.test(String(id))) return; // IDs inválidos no se pueden guardar en el servidor
            const titulo = escapeHtml(product.titulo);
            const imageUrl = `images/${id}_01.jpg`;
            const amazonUrl = escapeHtml(/^https?:\/\//i.test(product.url || '') ? product.url : `https://www.amazon.com.mx/dp/${id}`);
            
            const state = stateData[id] || { precio: '', vendido: false, amazon_precio: '' };
            const isSold = state.vendido;
            const amazonPrice = escapeHtml(state.amazon_precio || '---');
            
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
                        <img src="${imageUrl}" alt="" class="admin-thumbnail" width="60" height="60" loading="lazy" decoding="async" onerror="this.remove()">
                    </a>
                </td>
                <td class="product-cell" title="${titulo}">
                    <a href="${amazonUrl}" target="_blank" rel="noopener noreferrer" class="admin-product-link" title="Abrir ficha en Amazon: ${titulo}">
                        <span class="product-asin-tag"><strong>${id}</strong> <span style="font-size: 0.75rem;">↗</span></span><br>
                        <small class="product-link-title">${titulo}</small>
                    </a>
                </td>
                <td>
                    <span class="status-badge ${isSold ? 'status-sold' : 'status-available'}" id="badge-${id}">
                        ${isSold ? 'Vendido' : 'Disponible'}
                    </span>
                </td>
                <td style="font-weight: 600; color: #64748b;">
                    ${amazonPrice}
                </td>
                <td>
                    <input type="text" class="price-input" id="folio-${id}" value="${escapeHtml(state.folio || '')}" placeholder="#Lote" style="width: 80px;" aria-label="Folio de ${titulo}" title="Presiona Enter para guardar">
                </td>
                <td>
                    <div class="price-cell-wrap">
                        <input type="number" step="1" class="price-input" id="price-${id}" value="${state.precio !== undefined && state.precio !== null && state.precio !== '' ? Math.round(Number(state.precio)) : ''}" placeholder="${placeholderPrice}" min="0" inputmode="numeric" aria-label="Tu precio para ${titulo}" title="Escribe el precio y presiona Enter para guardar">
                        <button type="button" class="action-btn save-btn" onclick="saveData('${id}')">Guardar</button>
                        <span class="inline-save-status" id="save-status-${id}" role="status"></span>
                    </div>
                </td>
                <td>
                    <button type="button" class="action-btn toggle-btn ${isSold ? '' : 'is-sold'}" id="toggle-${id}" onclick="toggleSold('${id}')">
                        ${isSold ? 'Marcar disponible' : 'Marcar vendido'}
                    </button>
                </td>
            `;
            
            fragment.appendChild(tr);

            // Auto-guardar al presionar Enter en el campo de precio o de folio
            const priceInputEl = tr.querySelector(`#price-${id}`);
            const folioInputEl = tr.querySelector(`#folio-${id}`);

            const handleEnterKey = (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    window.saveData(id);
                }
            };

            if (priceInputEl) priceInputEl.addEventListener('keydown', handleEnterKey);
            if (folioInputEl) folioInputEl.addEventListener('keydown', handleEnterKey);
        });
        tableBody.appendChild(fragment);
    };

    window.saveData = async (id) => {
        const priceInput = document.getElementById(`price-${id}`);
        const folioInput = document.getElementById(`folio-${id}`);
        if (!priceInput || !folioInput) return;

        const rawPrice = priceInput.value.trim();
        const newPrice = rawPrice !== '' ? Math.round(Number(rawPrice)) : '';
        const newFolio = folioInput.value.trim();
        
        showInlineRowStatus(id, 'Guardando...', 'saving', false);

        const ok = await updateAPI(id, { precio: newPrice, folio: newFolio });
        if (ok) {
            priceInput.value = newPrice;
            priceInput.classList.add('input-saved-flash');
            setTimeout(() => priceInput.classList.remove('input-saved-flash'), 1200);

            showInlineRowStatus(id, '✓ Guardado', 'success', true);
            const priceLabel = newPrice !== '' ? `$${newPrice}` : 'Sin precio';
            const folioLabel = newFolio ? ` • Folio #${newFolio}` : '';
            showSideToast(`Guardado (${id}): ${priceLabel}${folioLabel}`, 'success');
        } else {
            showInlineRowStatus(id, '✕ Error', 'error', true);
        }
    };

    window.toggleSold = async (id, fromUndo = false) => {
        const previous = !!(stateData[id] && stateData[id].vendido);
        const newState = !previous;

        // updateAPI actualiza el estado local solo si el servidor confirmó
        const ok = await updateAPI(id, { vendido: newState });
        if (ok && !fromUndo) {
            showSideToast(`${id} marcado como ${newState ? 'vendido' : 'disponible'}`, 'success', {
                label: 'Deshacer',
                onClick: () => window.toggleSold(id, true),
            });
        } else if (ok) {
            showSideToast(`Listo: ${id} vuelve a estar ${newState ? 'vendido' : 'disponible'}`, 'success');
        }
        renderAdminTable();
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
            return true;
        } catch(e) {
            console.error(e);
            showSideToast("No se guardó: el servidor no responde. Inicia server.py e inténtalo de nuevo.", "error");
            return false;
        }
    };

    // Botón para actualizar el sitio y subir a Git
    const btnActualizar = document.getElementById('btn-actualizar-sitio');
    const btnSyncIcon = document.getElementById('btn-sync-icon');
    const btnSyncText = document.getElementById('btn-sync-text');

    if (btnActualizar) {
        btnActualizar.addEventListener('click', async () => {
            const confirmed = window.confirm('¿Publicar los cambios en la tienda pública ahora?');
            if (!confirmed) return;

            btnActualizar.disabled = true;
            if (btnSyncIcon) btnSyncIcon.textContent = '⏳';
            if (btnSyncText) btnSyncText.textContent = 'Publicando…';
            showSideToast('Publicando cambios en la tienda…', 'info');

            try {
                const response = await fetch('/api/actualizar_sitio', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({})
                });

                const result = await response.json();
                if (result.status === 'success') {
                    showSideToast('Cambios publicados. La tienda se actualiza en unos minutos.', 'success');
                } else {
                    const msg = result.message || 'No se pudieron publicar los cambios. Revisa la terminal del servidor.';
                    showSideToast(msg, 'error');
                    console.error('Error Git Output:', result.output);
                }
            } catch (err) {
                console.error(err);
                showSideToast('No hay conexión con el servidor. Inicia server.py e inténtalo de nuevo.', 'error');
            } finally {
                btnActualizar.disabled = false;
                if (btnSyncIcon) btnSyncIcon.textContent = '🚀';
                if (btnSyncText) btnSyncText.textContent = 'Publicar cambios';
            }
        });
    }

    loadData();
});
