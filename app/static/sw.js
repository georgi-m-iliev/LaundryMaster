console.log('Hello from LaundryMaster! 👋🏼 \nService worker is running.');

importScripts('https://storage.googleapis.com/workbox-cdn/releases/3.2.0/workbox-sw.js');

if (workbox) {
    console.log(`Yay! Workbox is loaded 🎉`);

    workbox.routing.registerRoute(
        /\.(?:js|css)$/,
        workbox.strategies.staleWhileRevalidate({
            cacheName: 'static-resources',
        }),
    );

    workbox.routing.registerRoute(
        /\.(?:png|gif|jpg|jpeg|svg)$/,
        workbox.strategies.cacheFirst({
            cacheName: 'images',
            plugins: [
                new workbox.expiration.Plugin({
                    maxEntries: 60,
                    maxAgeSeconds: 30 * 24 * 60 * 60, // 30 Days
                }),
            ],
        }),
    );

    workbox.routing.registerRoute(
        new RegExp('https://fonts.(?:googleapis|gstatic).com/(.*)'),
        workbox.strategies.cacheFirst({
            cacheName: 'googleapis',
            plugins: [
                new workbox.expiration.Plugin({
                    maxEntries: 30,
                }),
            ],
        }),
    );
} else {
    console.log("Workbox didn't load 😬");
}

self.addEventListener('push', function (event) {
    console.log('[Service Worker] Push Received.');
    const pushData = event.data.text();
    console.log(`[Service Worker] Push received this data - "${pushData}"`);
    let data, title, body;
    try {
        data = JSON.parse(pushData);
        title = data.title;
        body = data.body;
    } catch (e) {
        title = "Untitled";
        body = pushData;
    }
    const options = {
        body: body
    };
    console.log(title, options);

    event.waitUntil(
        self.registration.showNotification(title, options)
    );
});