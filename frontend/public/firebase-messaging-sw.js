/* global importScripts, firebase */

importScripts('https://www.gstatic.com/firebasejs/10.14.1/firebase-app-compat.js')
importScripts('https://www.gstatic.com/firebasejs/10.14.1/firebase-messaging-compat.js')

const firebaseConfig = {
  apiKey: new URL(location.href).searchParams.get('apiKey'),
  authDomain: new URL(location.href).searchParams.get('authDomain'),
  projectId: new URL(location.href).searchParams.get('projectId'),
  storageBucket: new URL(location.href).searchParams.get('storageBucket'),
  messagingSenderId: new URL(location.href).searchParams.get('messagingSenderId'),
  appId: new URL(location.href).searchParams.get('appId'),
}

firebase.initializeApp(firebaseConfig)

const messaging = firebase.messaging()

messaging.onBackgroundMessage((payload) => {
  const notification = payload.notification || {}
  const data = payload.data || {}
  const title = notification.title || 'yesh_mishak'
  const options = {
    body: notification.body || data.body || '',
    icon: '/favicon.svg',
    data,
  }

  self.registration.showNotification(title, options)
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()

  const data = event.notification.data || {}
  const targetUrl = data.game_id ? `/?game_id=${data.game_id}` : '/'

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      const existingClient = clients.find((client) => 'focus' in client)

      if (existingClient) {
        existingClient.focus()
        return
      }

      if (self.clients.openWindow) {
        return self.clients.openWindow(targetUrl)
      }
    }),
  )
})
