if ('serviceWorker' in navigator) {
  window.addEventListener('load', function() {
    navigator.serviceWorker.register("/sw.js", { scope: '/' })
    .then(function(registration) {
      // Registration was successful
      console.log('ServiceWorker registration successful with scope: ', registration.scope);
    }, function(err) {
      // registration failed :(
      console.log('ServiceWorker registration failed: ', err);
    });
  });
}

// Request notification permission
if (Notification.permission === 'default') {
  Notification.requestPermission().then(permission => {
    if (permission === 'granted') {
      // User granted permission, subscribe to push notifications
      subscribeToPush();
    }
  });
}

function subscribeToPush() {
  navigator.serviceWorker.ready.then(serviceWorkerRegistration => {
    serviceWorkerRegistration.pushManager.subscribe({ userVisibleOnly: true })
      .then(subscription => {
        // Send the subscription data to your Flask app
        sendSubscriptionToServer(subscription);
      })
      .catch(error => {
        console.error('Error subscribing to push notifications:', error);
      });
  });
}