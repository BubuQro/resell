// ==========================================================================
// BubuStore — catálogo público
// ==========================================================================

// --- Configuración de contacto -------------------------------------------
// Grupo de Telegram donde se coordinan las compras.
const TELEGRAM_GROUP_URL = 'https://t.me/+FsYQ0AKAyPFmZDIx';
// Si tienes un usuario de Telegram para mensajes directos (sin @), escríbelo aquí:
// "Lo quiero" abrirá el chat con el mensaje ya escrito. Vacío = copia el mensaje
// y abre el grupo (los enlaces de invitación a grupos no aceptan texto).
const TELEGRAM_USERNAME = '';

// Escapa texto antes de insertarlo como HTML (los títulos de Amazon traen comillas,
// p. ej. 15.6", que rompían los atributos alt/title y permitían inyectar HTML).
const escapeHtml = (value) => String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

// Búsqueda sin distinguir acentos ni mayúsculas ("bateria" encuentra "Batería")
const normalizeText = (value) => String(value ?? '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase();

const formatMoney = (n) => `$${Math.round(n).toLocaleString('es-MX')}`;
const parseMoney = (value) => {
    const n = Number(String(value ?? '').replace(/[^0-9.]/g, ''));
    return Number.isFinite(n) && n > 0 ? n : null;
};
const parseFolio = (value) => {
    const n = parseInt(String(value ?? '').replace(/\D/g, ''), 10);
    return Number.isNaN(n) ? null : n;
};

// ---------- Fotos ----------
// Índice de fotos existentes por producto (data/imagenes.json, lo genera
// generar_indice_imagenes.py). Si no está, se prueban nombres _01…_NN.
let imageIndex = null;
const CARD_MAX_PHOTOS = 6;   // la tarjeta muestra unas cuantas; el detalle, todas
const imageNumbers = (id, fallbackCount, max = Infinity) => {
    const list = imageIndex && Array.isArray(imageIndex[id])
        ? imageIndex[id]
        : Array.from({ length: fallbackCount }, (_, i) => String(i + 1).padStart(2, '0'));
    return list.slice(0, max);
};

// Ajusta la galería según cuántas fotos quedan: sin fotos se oculta el área,
// con una sola se ocultan las flechas.
const syncGallery = (gallery) => {
    if (!gallery) return;
    const n = gallery.querySelectorAll('img').length;
    const wrapper = gallery.closest('.card-gallery-wrapper, .modal-gallery-container');
    if (wrapper) {
        wrapper.classList.toggle('no-images', n === 0);
        wrapper.classList.toggle('single-image', n === 1);
    }
    gallery.dispatchEvent(new CustomEvent('gallerychange', { detail: { count: n } }));
};
// Si una foto no carga (no existe o está dañada) se elimina, sin dejar huecos ni íconos rotos
window.dropImage = (img) => {
    const gallery = img.parentElement;
    img.remove();
    syncGallery(gallery);
};

// Copiar texto. navigator.clipboard solo existe en HTTPS o localhost; en la red
// local (http://192.168…) se usa el método antiguo como último recurso.
const legacyCopy = (text) => {
    const field = Object.assign(document.createElement('textarea'), { value: text });
    field.setAttribute('readonly', '');
    field.style.cssText = 'position:fixed;inset-block-start:0;opacity:0';
    document.body.append(field);
    field.select();
    try { return document.execCommand('copy'); } finally { field.remove(); }
};
const safeLegacyCopy = (text) => { try { return legacyCopy(text); } catch { return false; } };
// Devuelve una promesa, pero la copia se INICIA de forma síncrona dentro del clic:
// así sigue funcionando aunque justo después se abra Telegram en otra pestaña.
const copyText = (text) => {
    if (!window.isSecureContext || !navigator.clipboard) {
        return Promise.resolve(safeLegacyCopy(text)); // red local por http://
    }
    return navigator.clipboard.writeText(text).then(() => true, () => safeLegacyCopy(text));
};

document.addEventListener('DOMContentLoaded', () => {
    // Los enlaces a Admin / Generador solo tienen sentido en la red local, no en la tienda pública
    const host = window.location.hostname;
    const isLocalHost = host === 'localhost' || host === '127.0.0.1' || host === '' ||
        /^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(host) || host.endsWith('.local');
    if (!isLocalHost) {
        document.querySelectorAll('.admin-only').forEach(el => el.remove());
    }

    const gridContainer = document.getElementById('products-grid');
    const searchInput = document.getElementById('search-input');
    const folioRangeInput = document.getElementById('folio-range-input');
    const sortSelect = document.getElementById('sort-select');
    const resultsCount = document.getElementById('results-count');
    const priceChips = [...document.querySelectorAll('.chip[data-price]')];

    let stateData = {};
    let allAvailableProducts = [];
    let priceRange = 'all';

    // Datos derivados de cada producto (precio, ahorro, folio)
    const info = (product) => {
        const st = stateData[product.id] || {};
        const price = parseMoney(st.precio);
        const amazon = parseMoney(st.amazon_precio);
        const savings = price && amazon && amazon - price >= 1 ? amazon - price : 0;
        return {
            price,
            amazon,
            savings,
            savingsPct: savings ? Math.round((savings / amazon) * 100) : 0,
            folio: st.folio ? String(st.folio) : '',
            folioNum: parseFolio(st.folio),
        };
    };

    const productUrl = (id) => {
        const url = new URL(window.location.href);
        url.search = '';
        url.hash = '';
        url.searchParams.set('id', id);
        return url.toString();
    };

    // Título corto para mensajes: hasta ~60 caracteres, cortado en un espacio
    const shortTitle = (titulo, max = 60) => {
        const t = String(titulo || '').replace(/\s+/g, ' ').trim();
        if (t.length <= max) return t;
        const cut = t.slice(0, max);
        const atSpace = cut.lastIndexOf(' ') > 30 ? cut.slice(0, cut.lastIndexOf(' ')) : cut;
        return `${atSpace.replace(/[\s,;:.\-|]+$/, '')}…`;
    };

    // ---------- Mensajes junto a los botones (región en vivo) ----------
    const statusTimers = new WeakMap();
    let lastMessage = '';
    const showStatus = (el, message, isError = false) => {
        if (!el) return;
        clearTimeout(statusTimers.get(el));
        // VoiceOver omite un mensaje idéntico al anterior: un espacio duro lo hace distinto
        let text = message;
        if (text === lastMessage) text += ' ';
        lastMessage = text;
        el.textContent = '';
        el.classList.toggle('error', isError);
        el.classList.add('visible');
        // setTimeout (no requestAnimationFrame): si se abrió Telegram la pestaña queda en
        // segundo plano y rAF no corre; así el mensaje ya está al volver.
        setTimeout(() => { el.textContent = text; }, 50);
        statusTimers.set(el, setTimeout(() => {
            el.classList.remove('visible');
            el.textContent = '';
        }, 6000));
    };

    // ---------- "Lo quiero" ----------
    const wantProduct = (product, statusEl) => {
        // Solo la descripción (nombre) del producto y su enlace
        const message = `${String(product.titulo || '').replace(/\s+/g, ' ').trim()}\n${productUrl(product.id)}`;

        if (TELEGRAM_USERNAME) {
            window.open(`https://t.me/${encodeURIComponent(TELEGRAM_USERNAME)}?text=${encodeURIComponent(message)}`, '_blank', 'noopener');
            showStatus(statusEl, 'Abrimos Telegram con tu mensaje listo para enviar.');
            return;
        }

        // Copiar primero (dentro del clic del usuario) y luego abrir el grupo
        const copied = copyText(message);
        window.open(TELEGRAM_GROUP_URL, '_blank', 'noopener');
        copied.then((ok) => {
            showStatus(statusEl, ok
                ? 'Mensaje copiado. Pégalo en el grupo de Telegram para apartarlo.'
                : 'No se pudo copiar el mensaje. Toca Compartir en el detalle del producto para copiar el enlace.', !ok);
        });
    };

    // ---------- Compartir ----------
    const shareProduct = async (product, statusEl) => {
        const url = productUrl(product.id);
        const { price } = info(product);
        const data = { title: 'BubuStore', text: `${shortTitle(product.titulo)}${price ? ` por ${formatMoney(price)}` : ''}`, url };
        if (navigator.share) {
            try { await navigator.share(data); return; } catch (e) {
                if (e && e.name === 'AbortError') return; // la persona canceló
            }
        }
        const ok = await copyText(url);
        showStatus(statusEl, ok ? 'Enlace copiado.' : 'No se pudo copiar el enlace. Cópialo desde la barra de direcciones.', !ok);
    };

    // ---------- Filtros y orden ----------
    const inPriceRange = (price) => {
        if (priceRange === 'all' || !price) return true;
        const [min, max] = priceRange.split('-').map(v => (v === '' ? null : Number(v)));
        if (min !== null && price < min) return false;
        if (max !== null && price > max) return false;
        return true;
    };

    const parseFolioRange = (query) => {
        if (!query) return null;
        if (query.includes('-')) {
            const [a, b] = query.split('-');
            return { min: parseFolio(a) ?? -Infinity, max: parseFolio(b) ?? Infinity };
        }
        const n = parseFolio(query);
        return n === null ? null : { min: n, max: n };
    };

    const applyFiltersAndSort = () => {
        let filtered = [...allAvailableProducts];

        const query = searchInput ? normalizeText(searchInput.value.trim()) : '';
        if (query) {
            const queryFolio = /^#?\d+$/.test(query) ? parseFolio(query) : null;
            filtered = filtered.filter(p => {
                const { folioNum } = info(p);
                return normalizeText(p.titulo).includes(query) ||
                    normalizeText(p.descripcion).includes(query) ||
                    normalizeText(p.id).includes(query) ||
                    (queryFolio !== null && folioNum === queryFolio);
            });
        }

        const range = parseFolioRange(folioRangeInput ? folioRangeInput.value.trim() : '');
        if (range) {
            filtered = filtered.filter(p => {
                const { folioNum } = info(p);
                return folioNum !== null && folioNum >= range.min && folioNum <= range.max;
            });
        }

        filtered = filtered.filter(p => inPriceRange(info(p).price));

        const sortVal = sortSelect ? sortSelect.value : 'default';
        const last = (v, dir) => (v === null || v === undefined ? Infinity : v * dir);
        const sorters = {
            'name-asc': (a, b) => String(a.titulo).localeCompare(String(b.titulo), 'es'),
            'price-asc': (a, b) => last(info(a).price, 1) - last(info(b).price, 1),
            'price-desc': (a, b) => last(info(a).price, -1) - last(info(b).price, -1),
            'savings-desc': (a, b) => info(b).savings - info(a).savings,
            'folio-asc': (a, b) => last(info(a).folioNum, 1) - last(info(b).folioNum, 1),
            'folio-desc': (a, b) => last(info(a).folioNum, -1) - last(info(b).folioNum, -1),
        };
        if (sorters[sortVal]) filtered.sort(sorters[sortVal]);

        // Si se buscó un número, el producto con ese folio exacto va primero
        if (query && /^#?\d+$/.test(query)) {
            const wanted = parseFolio(query);
            filtered.sort((a, b) => (info(b).folioNum === wanted) - (info(a).folioNum === wanted));
        }

        renderProducts(filtered);
    };

    const hasActiveFilters = () =>
        (searchInput && searchInput.value.trim()) ||
        (folioRangeInput && folioRangeInput.value.trim()) ||
        priceRange !== 'all';

    const clearFilters = () => {
        if (searchInput) searchInput.value = '';
        if (folioRangeInput) folioRangeInput.value = '';
        setPriceRange('all');
        applyFiltersAndSort();
        if (searchInput) searchInput.focus();
    };

    const setPriceRange = (value) => {
        priceRange = value;
        priceChips.forEach(chip => chip.setAttribute('aria-pressed', String(chip.dataset.price === value)));
    };

    if (searchInput) searchInput.addEventListener('input', applyFiltersAndSort);
    if (folioRangeInput) folioRangeInput.addEventListener('input', applyFiltersAndSort);
    if (sortSelect) sortSelect.addEventListener('change', applyFiltersAndSort);
    priceChips.forEach(chip => chip.addEventListener('click', () => {
        setPriceRange(chip.dataset.price);
        applyFiltersAndSort();
    }));

    // ---------- Tarjetas ----------
    const priceBlock = ({ price, amazon, savings, savingsPct }) => {
        if (!price) return '';
        const ref = amazon && savings ? `<span class="ref-price">Amazon <s>${formatMoney(amazon)}</s></span>` : '';
        const save = savings ? `<span class="savings">Ahorras ${formatMoney(savings)} (${savingsPct}%)</span>` : '';
        return `<span class="product-price">${formatMoney(price)}</span>${ref}${save}`;
    };

    const renderProducts = (productsToRender) => {
        gridContainer.innerHTML = '';
        const n = productsToRender ? productsToRender.length : 0;

        if (resultsCount) {
            resultsCount.textContent = hasActiveFilters()
                ? `${n} de ${allAvailableProducts.length} productos`
                : `${n} producto${n === 1 ? '' : 's'} disponible${n === 1 ? '' : 's'}`;
        }

        if (n === 0) {
            const empty = document.createElement('div');
            empty.className = 'empty-state';
            empty.innerHTML = '<p>No hay productos con esos filtros.</p>';
            if (hasActiveFilters()) {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'btn-secondary';
                btn.textContent = 'Quitar filtros';
                btn.addEventListener('click', clearFilters);
                empty.append(btn);
            }
            gridContainer.append(empty);
            return;
        }

        const fragment = document.createDocumentFragment();

        productsToRender.forEach((product, index) => {
            const { id, titulo } = product;
            const data = info(product);
            const safeId = encodeURIComponent(id);
            const safeTitle = escapeHtml(titulo);
            // Las primeras tarjetas cargan de inmediato; el resto al acercarse
            const loading = index < 4 ? 'eager' : 'lazy';
            // La primera foto del primer producto es la imagen principal (LCP)
            const priorityAttr = index === 0 ? ' fetchpriority="high"' : '';

            const gallery = imageNumbers(id, 5, CARD_MAX_PHOTOS).map((num, i) => {
                const src = `images/${safeId}_${num}.jpg`;
                return i === 0
                    ? `<img src="${src}" alt="${safeTitle}" class="product-image" width="400" height="400" loading="${loading}"${priorityAttr} decoding="async" onerror="dropImage(this)">`
                    : `<img src="${src}" alt="" class="product-image" width="400" height="400" loading="lazy" decoding="async" onerror="dropImage(this)">`;
            }).join('');

            const folioHtml = data.folio
                ? `<span class="product-folio-badge"><span class="folio-label">Folio</span> ${escapeHtml(data.folio)}</span>`
                : '';

            const card = document.createElement('article');
            card.className = 'product-card';
            card.innerHTML = `
                <div class="card-gallery-wrapper">
                    ${folioHtml}
                    <div class="image-gallery">${gallery}</div>
                    <button type="button" class="carousel-btn prev" aria-label="Foto anterior de ${safeTitle}" data-dir="-1">&#10094;</button>
                    <button type="button" class="carousel-btn next" aria-label="Foto siguiente de ${safeTitle}" data-dir="1">&#10095;</button>
                </div>
                <h3 class="product-title"><button type="button" class="card-link">${safeTitle}</button></h3>
                <p class="product-price-row">${priceBlock(data)}</p>
                <footer class="card-actions">
                    <button type="button" class="btn-want">Lo quiero<span class="sr-only">: ${safeTitle}</span></button>
                    <p class="action-status" role="status"></p>
                </footer>
            `;

            const statusEl = card.querySelector('.action-status');
            card.querySelector('.card-link').addEventListener('click', () => openModal(product));
            // Tocar la foto también abre el detalle (la galería queda encima para poder deslizar)
            card.querySelector('.image-gallery').addEventListener('click', () => openModal(product));
            card.querySelector('.btn-want').addEventListener('click', () => wantProduct(product, statusEl));
            card.querySelectorAll('.carousel-btn').forEach(btn => btn.addEventListener('click', () => {
                const g = card.querySelector('.image-gallery');
                g.scrollBy({ left: Number(btn.dataset.dir) * g.clientWidth, behavior: 'smooth' });
            }));
            syncGallery(card.querySelector('.image-gallery'));

            fragment.appendChild(card);
        });

        gridContainer.appendChild(fragment);
    };

    // ---------- Modal de detalle ----------
    const modal = document.getElementById('product-modal');
    const modalGallery = document.getElementById('modal-gallery');
    const modalFolio = document.getElementById('modal-folio');
    const modalTitle = document.getElementById('modal-title');
    const modalPrice = document.getElementById('modal-price');
    const modalDesc = document.getElementById('modal-desc');
    const modalLink = document.getElementById('modal-link');
    const modalCounter = document.getElementById('modal-counter');
    const modalWant = document.getElementById('modal-want');
    const modalShare = document.getElementById('modal-share');
    const modalStatus = document.getElementById('modal-status');
    let modalProduct = null;

    // Las descripciones de Amazon separan viñetas con " | ": se muestran como lista
    const renderDescription = (text) => {
        const items = String(text || '').split(/\s+\|\s+/).map(s => s.trim()).filter(Boolean);
        if (items.length > 1) {
            modalDesc.innerHTML = `<ul>${items.map(i => `<li>${escapeHtml(i)}</li>`).join('')}</ul>`;
        } else {
            modalDesc.textContent = items[0] || 'Sin descripción.';
        }
    };

    const openModal = (product) => {
        modalProduct = product;
        const { id, titulo, url } = product;
        const data = info(product);

        modalFolio.textContent = data.folio ? `Folio ${data.folio}` : '';
        modalFolio.hidden = !data.folio;
        modalTitle.textContent = titulo;
        modalPrice.innerHTML = priceBlock(data);
        modalPrice.hidden = !data.price;
        renderDescription(product.descripcion);
        modalStatus.textContent = '';
        modalStatus.classList.remove('visible');

        // Solo enlaces http(s) (evita "javascript:" u otros esquemas en los datos)
        modalLink.href = /^https?:\/\//i.test(url || '') ? url : `https://www.amazon.com.mx/dp/${encodeURIComponent(id)}`;

        const safeId = encodeURIComponent(id);
        const safeTitle = escapeHtml(titulo);
        // Todas las fotos del producto. Las que no se ven al abrir cargan con prioridad baja.
        modalGallery.innerHTML = imageNumbers(id, 10).map((num, i) => {
            const src = `images/${safeId}_${num}.jpg`;
            return i === 0
                ? `<img src="${src}" alt="${safeTitle}" decoding="async" onerror="dropImage(this)">`
                : `<img src="${src}" alt="${safeTitle} (foto ${i + 1})" loading="lazy" fetchpriority="low" decoding="async" onerror="dropImage(this)">`;
        }).join('');
        syncGallery(modalGallery);

        if (!modal.open) modal.showModal();
        modalGallery.scrollLeft = 0;
        modal.querySelector('.modal-body').scrollTop = 0;
    };

    modalWant.addEventListener('click', () => modalProduct && wantProduct(modalProduct, modalStatus));
    modalShare.addEventListener('click', () => modalProduct && shareProduct(modalProduct, modalStatus));
    document.getElementById('close-modal').addEventListener('click', () => modal.close());

    // Cerrar tocando fuera: closedby="any" lo hace de forma nativa.
    // Respaldo para navegadores sin soporte (Safari / iPhone).
    if (!('closedBy' in HTMLDialogElement.prototype)) {
        modal.addEventListener('click', (e) => {
            if (e.target !== modal) return; // en el fondo, el target es el propio <dialog>
            const rect = modal.getBoundingClientRect();
            const isDialogContent =
                rect.top <= e.clientY && e.clientY <= rect.top + rect.height &&
                rect.left <= e.clientX && e.clientX <= rect.left + rect.width;
            if (!isDialogContent) modal.close();
        });
    }

    // Quitar ?id= de la dirección al cerrar, para que recargar no reabra el producto
    modal.addEventListener('close', () => {
        const url = new URL(window.location.href);
        if (url.searchParams.has('id')) {
            url.searchParams.delete('id');
            history.replaceState(null, '', url);
        }
    });

    document.getElementById('modal-prev').addEventListener('click', () => {
        modalGallery.scrollBy({ left: -modalGallery.clientWidth, behavior: 'smooth' });
    });
    document.getElementById('modal-next').addEventListener('click', () => {
        modalGallery.scrollBy({ left: modalGallery.clientWidth, behavior: 'smooth' });
    });

    // Contador "3 / 12" en lugar de puntos (con muchas fotos los puntos no caben)
    const updateCounter = () => {
        const total = modalGallery.querySelectorAll('img').length;
        const index = Math.min(total, Math.round(modalGallery.scrollLeft / (modalGallery.clientWidth || 1)) + 1);
        modalCounter.textContent = total > 1 ? `${index} / ${total}` : '';
    };
    modalGallery.addEventListener('scroll', updateCounter, { passive: true });
    modalGallery.addEventListener('gallerychange', updateCounter);

    // ---------- Carga de datos ----------
    const loadProducts = async () => {
        try {
            try {
                const stateRes = await fetch('data/estado_productos.json');
                if (stateRes.ok) stateData = await stateRes.json();
            } catch (e) {
                console.log('Sin archivo de estado; se usan valores por defecto.');
            }

            try {
                const imgRes = await fetch('data/imagenes.json');
                if (imgRes.ok) imageIndex = await imgRes.json();
            } catch (e) {
                console.log('Sin índice de imágenes; se buscan las fotos por nombre.');
            }

            const response = await fetch('data/productos.json');
            if (!response.ok) throw new Error(`Error HTTP: ${response.status}`);
            const data = await response.json();

            let productsArray = [];
            if (Array.isArray(data)) {
                productsArray = data;
            } else if (data.productos && Array.isArray(data.productos)) {
                productsArray = data.productos;
            } else {
                for (const key in data) {
                    if (Array.isArray(data[key])) { productsArray = data[key]; break; }
                }
            }

            // Solo productos no vendidos y con precio válido
            allAvailableProducts = productsArray.filter(p => {
                const st = stateData[p.id];
                return !(st && st.vendido === true) && parseMoney(st && st.precio) !== null;
            });

            applyFiltersAndSort();

            // Abrir el detalle si la dirección trae ?id= (enlaces compartidos)
            const productIdToOpen = new URLSearchParams(window.location.search).get('id');
            if (productIdToOpen) {
                const product = allAvailableProducts.find(p => p.id === productIdToOpen);
                if (product) openModal(product);
            }
        } catch (error) {
            console.error('Error al cargar los productos:', error);
            gridContainer.innerHTML = '<div class="empty-state error"><p>No se pudieron cargar los productos. Revisa tu conexión y recarga la página.</p></div>';
        }
    };

    loadProducts();
});
