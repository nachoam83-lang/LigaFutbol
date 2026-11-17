const CACHE_NAME = 'liga-futbol-v1.02.00'; // <-- CAMBIA ESTO CADA VEZ QUE ACTUALICES (ej: v1.02.01)
const urlsToCache = [
    '/',
    '/static/index.html',
    '/static/logo.png',
    '/static/Equipo_Canal.png',
    '/static/escudo_canal.png'
];

// Instalar y forzar la activación inmediata
self.addEventListener('install', event => {
    self.skipWaiting(); 
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => {
            return cache.addAll(urlsToCache);
        })
    );
});

// Limpiar cachés antiguas y tomar el control de forma segura
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.map(cacheName => {
                    if (cacheName !== CACHE_NAME) {
                        return caches.delete(cacheName);
                    }
                })
            );
        }).then(() => self.clients.claim())
    );
});

// Estrategias de red
self.addEventListener('fetch', event => {
    if (event.request.method !== 'GET') return;

    const url = new URL(event.request.url);

    // 1. NETWORK FIRST: Para HTML, API y datos dinámicos
    if (url.pathname === '/' || 
        url.pathname.endsWith('.html') || 
        url.pathname.startsWith('/api/') || 
        url.pathname.endsWith('grupos.json')) {
        
        event.respondWith(
            fetch(event.request)
                .then(networkResponse => {
                    if (networkResponse && networkResponse.status === 200) {
                        const responseClone = networkResponse.clone();
                        caches.open(CACHE_NAME).then(cache => cache.put(event.request, responseClone));
                    }
                    return networkResponse;
                })
                .catch(() => {
                    return caches.match(event.request);
                })
        );
        return;
    }

    // 2. STALE-WHILE-REVALIDATE: Para imágenes, CDNs y recursos estáticos
    event.respondWith(
        caches.open(CACHE_NAME).then(cache => {
            return cache.match(event.request).then(cachedResponse => {
                const fetchPromise = fetch(event.request).then(networkResponse => {
                    if (networkResponse && networkResponse.status === 200) {
                        cache.put(event.request, networkResponse.clone());
                    }
                    return networkResponse;
                }).catch(() => {});

                return cachedResponse || fetchPromise;
            });
        })
    );
});
