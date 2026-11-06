const CACHE_NAME = 'liga-futbol-auto';
const urlsToCache = [
    '/',
    '/static/index.html',
    '/static/logo.png',
    '/static/Equipo_Canal.png'
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

// Limpiar cachés antiguas y tomar el control
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

// Estrategia Stale-While-Revalidate (Velocidad + Actualización automática)
self.addEventListener('fetch', event => {
    if (event.request.method !== 'GET') return;

    event.respondWith(
        caches.open(CACHE_NAME).then(cache => {
            return cache.match(event.request).then(cachedResponse => {
                // Iniciamos la descarga en segundo plano
                const fetchPromise = fetch(event.request).then(networkResponse => {
                    if (networkResponse && networkResponse.status === 200) {
                        cache.put(event.request, networkResponse.clone()); // Guardamos la nueva
                    }
                    return networkResponse;
                }).catch(() => {}); // Si no hay internet, ignoramos el error

                // Devolvemos la copia guardada al instante (o esperamos a la red si no existe)
                return cachedResponse || fetchPromise;
            });
        })
    );
});
