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
    // console.log(`[Service Worker] Push received this data - "${pushData}"`);
    let data, title, body, icon, url, actions, actionsURLs;
    try {
        data = JSON.parse(pushData);
        title = data.title;
        body = data.body;
        icon = data.icon;
        url = data.url;
        actions = data.actions
        actionsURLs = data.actionsURLs
    } catch (e) {
        title = "Error with retrieving notification";
        body = pushData;
        icon = null;
        url = '/';
        actions = [];
        actionsURLs = [];
    }
    const options = {
        body: body,
        badge: 'static/assets/img/icons/android-chrome-192x192.png',
        icon: `static/assets/img/icons/${icon}`,
        data: {
            url: url,
            actionsURLs: actionsURLs
        },
        // actions: [{action: "open_url", title: "Read Now"}]
        actions: actions,
    };

    event.waitUntil(
        self.registration.showNotification(title, options)
    );
});

self.addEventListener('notificationclick', event => {
    const origin = new URL('/', location).origin;
    event.notification.close();
    // Enumerate windows, and call window.focus(), or open a new one.
    event.waitUntil(
        clients.matchAll().then(matchedClients => {
            let newURL;

            if(event.action === '') {
                newURL = event.notification.data.url;
            }
            else {
                const actions = event.notification.actions;
                const actionsURLs = event.notification.data.actionsURLs;
                for(let i = 0; i < actions.length; i++) {
                    if(actions[i].action === event.action) {
                        newURL = actionsURLs[i];
                    }
                }
            }

            //TODO: bug on android (presumably on other mobile configs too)
            // if app not opened, action is not triggered
            // if app opened, action is triggered
            // on windows and chrome it works fine
            // temporary solution: open new window always
            return clients.openWindow(newURL);


            for (let client of matchedClients) {
                if (client.url.startsWith(origin)) {
                    return client.navigate(newURL).then(client => client.focus());
                }
            }
            // if no clients are open, then open one.
            return clients.openWindow(newURL);
        })
    );
});

// self.addEventListener('notificationclick', function(event) {
//     switch(event.action){
//         case 'open_url':
//             clients.openWindow(event.notification.data.url); //which we got from above
//         break;
//         case 'any_other_action':
//             clients.openWindow("https://www.example.com");
//         break;
//     }
// });
