document.addEventListener('DOMContentLoaded', () => {
    const gridContainer = document.getElementById('products-grid');
    const searchInput = document.getElementById('search-input');
    const folioRangeInput = document.getElementById('folio-range-input');
    const sortSelect = document.getElementById('sort-select');
    
    let stateData = {};
    let allAvailableProducts = [];

    const applyFiltersAndSort = () => {
        let filtered = [...allAvailableProducts];
        
        // Búsqueda
        const query = searchInput ? searchInput.value.toLowerCase().trim() : '';
        if (query) {
            filtered = filtered.filter(p => 
                p.titulo.toLowerCase().includes(query) || 
                p.descripcion.toLowerCase().includes(query)
            );
        }
        
        // Rango de folios
        const folioQuery = folioRangeInput ? folioRangeInput.value.trim() : '';
        if (folioQuery) {
            let minFolio = -Infinity;
            let maxFolio = Infinity;
            
            if (folioQuery.includes('-')) {
                const parts = folioQuery.split('-');
                if (parts[0].trim() !== '') minFolio = parseInt(parts[0].replace(/\D/g, ''), 10);
                if (parts[1].trim() !== '') maxFolio = parseInt(parts[1].replace(/\D/g, ''), 10);
            } else {
                const singleNum = parseInt(folioQuery.replace(/\D/g, ''), 10);
                if (!isNaN(singleNum)) {
                    minFolio = singleNum;
                    maxFolio = singleNum;
                }
            }
            
            filtered = filtered.filter(p => {
                const productFolioStr = stateData[p.id] ? stateData[p.id].folio : '';
                if (!productFolioStr) return false;
                
                const productFolioNum = parseInt(String(productFolioStr).replace(/\D/g, ''), 10);
                if (isNaN(productFolioNum)) return false;
                
                return productFolioNum >= minFolio && productFolioNum <= maxFolio;
            });
        }
        
        // Ordenamiento
        const sortVal = sortSelect ? sortSelect.value : 'default';
        if (sortVal !== 'default') {
            filtered.sort((a, b) => {
                if (sortVal === 'name-asc') return a.titulo.localeCompare(b.titulo);
                if (sortVal === 'name-desc') return b.titulo.localeCompare(a.titulo);
                
                const priceA = (stateData[a.id] && stateData[a.id].precio !== undefined && stateData[a.id].precio !== null && stateData[a.id].precio !== '')
                    ? Number(stateData[a.id].precio)
                    : Infinity;
                const priceB = (stateData[b.id] && stateData[b.id].precio !== undefined && stateData[b.id].precio !== null && stateData[b.id].precio !== '')
                    ? Number(stateData[b.id].precio)
                    : Infinity;
                
                if (sortVal === 'price-asc') return priceA - priceB;
                if (sortVal === 'price-desc') {
                    if (priceA === Infinity && priceB === Infinity) return 0;
                    if (priceA === Infinity) return 1;
                    if (priceB === Infinity) return -1;
                    return priceB - priceA;
                }
                
                let folioA = Infinity;
                if (stateData[a.id] && stateData[a.id].folio) {
                    const parsed = parseInt(String(stateData[a.id].folio).replace(/\D/g, ''), 10);
                    if (!isNaN(parsed)) folioA = parsed;
                }
                
                let folioB = Infinity;
                if (stateData[b.id] && stateData[b.id].folio) {
                    const parsed = parseInt(String(stateData[b.id].folio).replace(/\D/g, ''), 10);
                    if (!isNaN(parsed)) folioB = parsed;
                }
                
                if (sortVal === 'folio-asc') {
                    if (folioA === Infinity && folioB === Infinity) return 0;
                    return folioA - folioB;
                }
                if (sortVal === 'folio-desc') {
                    if (folioA === Infinity && folioB === Infinity) return 0;
                    if (folioA === Infinity) return 1;
                    if (folioB === Infinity) return -1;
                    return folioB - folioA;
                }
                
                return 0;
            });
        }
        
        renderProducts(filtered);
    };

    if (searchInput) searchInput.addEventListener('input', applyFiltersAndSort);
    if (folioRangeInput) folioRangeInput.addEventListener('input', applyFiltersAndSort);
    if (sortSelect) sortSelect.addEventListener('change', applyFiltersAndSort);

    // Función para renderizar los productos
    const renderProducts = (productsToRender) => {
        gridContainer.innerHTML = '';

        if (!productsToRender || productsToRender.length === 0) {
            gridContainer.innerHTML = '<p>No hay productos que coincidan con la búsqueda.</p>';
            return;
        }

        productsToRender.forEach(product => {
            const { id, titulo, descripcion, url } = product;
            
            let galleryHtml = '<div class="image-gallery">';
            for (let i = 1; i <= 5; i++) {
                const num = i.toString().padStart(2, '0');
                const imageUrl = `images/${id}_${num}.jpg`;
                if (i === 1) {
                    galleryHtml += `<img src="${imageUrl}" alt="${titulo}" class="product-image" onerror="this.onerror=null; this.src='https://via.placeholder.com/400x250?text=Sin+Imagen';">`;
                } else {
                    galleryHtml += `<img src="${imageUrl}" alt="${titulo}" class="product-image" onerror="this.remove()">`;
                }
            }
            galleryHtml += '</div>';
            // Controles para tarjeta
            galleryHtml += `
                <button class="carousel-btn prev" onclick="scrollGallery(event, this, -1)">&#10094;</button>
                <button class="carousel-btn next" onclick="scrollGallery(event, this, 1)">&#10095;</button>
            `;

            // Obtener precio si existe y es válido
            let price = '';
            let priceHtml = '';
            const rawPrecio = stateData[id] && stateData[id].precio;
            if (rawPrecio !== undefined && rawPrecio !== null && rawPrecio !== '') {
                const precioNum = Number(rawPrecio);
                if (!isNaN(precioNum) && precioNum > 0) {
                    const roundedPrice = Math.round(precioNum);
                    price = `$${roundedPrice.toLocaleString('en-US')}`;
                    
                    let refAmazonHtml = '';
                    if (stateData[id].amazon_precio) {
                        refAmazonHtml = `<span class="product-amazon-ref" title="Precio de referencia en Amazon">Amazon: <span class="ref-strike">${stateData[id].amazon_precio}</span></span>`;
                    }

                    priceHtml = `
                        <div class="product-price-row">
                            <div class="product-price-container">
                                <span class="product-price-symbol">$</span>
                                <span class="product-price">${roundedPrice.toLocaleString('en-US')}</span>
                            </div>
                            ${refAmazonHtml}
                        </div>
                    `;
                }
            }

            let folioHtml = '';
            if (stateData[id] && stateData[id].folio) {
                folioHtml = `<div class="product-folio-badge">${stateData[id].folio}</div>`;
            }

            const card = document.createElement('article');
            card.className = 'product-card';

            card.innerHTML = `
                <div class="card-gallery-wrapper">
                    ${folioHtml}
                    ${galleryHtml}
                </div>
                <div class="product-content">
                    <h2 class="product-title">${titulo}</h2>
                    ${priceHtml}
                    <p class="product-desc">${descripcion}</p>
                    <button class="product-link">Ver Detalles</button>
                </div>
            `;

            card.addEventListener('click', (e) => {
                if(e.target.classList.contains('carousel-btn')) return;
                openModal(product, price);
            });

            gridContainer.appendChild(card);
        });
    };

    // Lógica del modal
    const modal = document.getElementById('product-modal');
    const closeModalBtn = document.getElementById('close-modal');
    const modalGallery = document.getElementById('modal-gallery');
    const modalTitle = document.getElementById('modal-title');
    const modalDesc = document.getElementById('modal-desc');
    const modalLink = document.getElementById('modal-link');
    const modalIndicators = document.getElementById('modal-indicators');

    const openModal = (product, price) => {
        const { id, titulo, descripcion, url } = product;
        
        let modalPriceHtml = '';
        if (price) {
            let refText = '';
            if (stateData[id] && stateData[id].amazon_precio) {
                refText = ` <small class="modal-ref-price">(Amazon: <s>${stateData[id].amazon_precio}</s> - 20% OFF)</small>`;
            }
            modalPriceHtml = `<span class="modal-price">${price}${refText}</span>`;
        }
        
        modalTitle.innerHTML = `${titulo} ${modalPriceHtml}`;
        modalDesc.textContent = descripcion;
        modalLink.href = url;
        modalLink.className = 'product-link amazon-link';

        let galleryHtml = '';
        let indicatorsHtml = '';
        for (let i = 1; i <= 10; i++) {
            const num = i.toString().padStart(2, '0');
            const imageUrl = `images/${id}_${num}.jpg`;
            if (i === 1) {
                galleryHtml += `<img src="${imageUrl}" alt="${titulo}" onload="updateIndicators()" onerror="this.onerror=null; this.src='https://via.placeholder.com/600x400?text=Sin+Imagen'; updateIndicators()">`;
                indicatorsHtml += `<span class="dot active"></span>`;
            } else {
                galleryHtml += `<img src="${imageUrl}" alt="${titulo}" onload="updateIndicators()" onerror="this.remove(); updateIndicators()">`;
                indicatorsHtml += `<span class="dot"></span>`;
            }
        }
        modalGallery.innerHTML = galleryHtml;
        modalIndicators.innerHTML = indicatorsHtml;

        modal.showModal();
        modalGallery.scrollLeft = 0;
    };

    closeModalBtn.addEventListener('click', () => modal.close());

    modal.addEventListener('click', (e) => {
        const dialogDimensions = modal.getBoundingClientRect();
        if (
            e.clientX < dialogDimensions.left ||
            e.clientX > dialogDimensions.right ||
            e.clientY < dialogDimensions.top ||
            e.clientY > dialogDimensions.bottom
        ) {
            modal.close();
        }
    });

    // Control de scroll del modal
    document.getElementById('modal-prev').addEventListener('click', () => {
        modalGallery.scrollBy({ left: -modalGallery.clientWidth, behavior: 'smooth' });
    });
    document.getElementById('modal-next').addEventListener('click', () => {
        modalGallery.scrollBy({ left: modalGallery.clientWidth, behavior: 'smooth' });
    });

    modalGallery.addEventListener('scroll', () => {
        const index = Math.round(modalGallery.scrollLeft / modalGallery.clientWidth);
        const dots = document.querySelectorAll('#modal-indicators .dot');
        dots.forEach((dot, i) => {
            dot.classList.toggle('active', i === index);
        });
    });

    window.updateIndicators = () => {
        const imagesCount = modalGallery.querySelectorAll('img').length;
        const dots = document.querySelectorAll('#modal-indicators .dot');
        dots.forEach((dot, i) => {
            dot.style.display = i < imagesCount ? 'inline-block' : 'none';
        });
    };

    window.scrollGallery = (e, btn, dir) => {
        e.stopPropagation();
        const gallery = btn.parentElement.querySelector('.image-gallery');
        gallery.scrollBy({ left: dir * gallery.clientWidth, behavior: 'smooth' });
    };

    const loadProducts = async () => {
        try {
            // Load state
            try {
                const stateRes = await fetch('data/estado_productos.json');
                if(stateRes.ok) {
                    stateData = await stateRes.json();
                }
            } catch(e) {
                console.log("No state file found, proceeding with defaults");
            }

            // Load products
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
                    if (Array.isArray(data[key])) {
                        productsArray = data[key];
                        break;
                    }
                }
            }
            
            // Guardar globalmente filtrando los vendidos y asegurando que tengan precio válido
            allAvailableProducts = productsArray.filter(p => {
                const itemState = stateData[p.id];
                const isSold = itemState && itemState.vendido === true;
                const priceVal = itemState ? itemState.precio : null;
                const hasValidPrice = priceVal !== undefined && priceVal !== null && String(priceVal).trim() !== '' && Number(priceVal) > 0;
                return !isSold && hasValidPrice;
            });
            
            applyFiltersAndSort();

            // Auto-open modal if ?id= is present in URL
            const urlParams = new URLSearchParams(window.location.search);
            const productIdToOpen = urlParams.get('id');
            if (productIdToOpen) {
                const productToOpen = allAvailableProducts.find(p => p.id === productIdToOpen);
                if (productToOpen) {
                    let price = '';
                    if (stateData[productToOpen.id]) {
                        const rawPrecio = stateData[productToOpen.id].precio;
                        if (rawPrecio !== undefined && rawPrecio !== null && rawPrecio !== '') {
                            const precioNum = Number(rawPrecio);
                            if (!isNaN(precioNum) && precioNum > 0) {
                                price = `$${Math.round(precioNum).toLocaleString('en-US')}`;
                            }
                        }
                    }
                    openModal(productToOpen, price);
                }
            }
            
        } catch (error) {
            console.error('Error al cargar los productos:', error);
            gridContainer.innerHTML = `<p style="color: #ef4444;">Error al cargar los productos.</p>`;
        }
    };

    loadProducts();
});
