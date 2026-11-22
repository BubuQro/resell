// Cambio de estilo BubuStore ⇄ Clásico (compartido por index.html y admin.html).
// El tema inicial lo aplica un script mínimo en <head> para evitar parpadeo;
// este archivo solo maneja el botón y la sincronización entre pestañas.
(() => {
    const STORAGE_KEY = 'bubu-estilo';
    const THEMES = {
        bubu: { label: 'Estilo clásico', aria: 'Cambiar al estilo clásico', themeColor: '#1D2452' },
        clasico: { label: 'Estilo BubuStore', aria: 'Cambiar al estilo BubuStore', themeColor: '#131921' },
    };

    const current = () => (document.documentElement.dataset.theme === 'clasico' ? 'clasico' : 'bubu');

    const render = () => {
        const theme = current();
        document.querySelectorAll('[data-theme-toggle]').forEach((btn) => {
            btn.textContent = THEMES[theme].label;
            btn.setAttribute('aria-label', THEMES[theme].aria);
        });
        const meta = document.querySelector('meta[name="theme-color"]');
        if (meta) meta.content = THEMES[theme].themeColor;
    };

    const apply = (theme, persist) => {
        document.documentElement.dataset.theme = theme;
        if (persist) {
            // localStorage puede fallar (modo privado, datos bloqueados): el tema se aplica igual
            try {
                if (theme === 'bubu') localStorage.removeItem(STORAGE_KEY);
                else localStorage.setItem(STORAGE_KEY, theme);
            } catch (e) { /* sin persistencia */ }
        }
        render();
    };

    document.addEventListener('click', (e) => {
        const btn = e.target.closest('[data-theme-toggle]');
        if (!btn) return;
        apply(current() === 'bubu' ? 'clasico' : 'bubu', true);
    });

    // Mantener en sincronía otras pestañas abiertas
    window.addEventListener('storage', (e) => {
        if (e.key === STORAGE_KEY) apply(e.newValue === 'clasico' ? 'clasico' : 'bubu', false);
    });

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', render);
    else render();
})();
