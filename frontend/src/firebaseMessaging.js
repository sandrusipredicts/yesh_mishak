import { initializeApp } from 'firebase/app'
import { getMessaging, getToken, isSupported, onMessage } from 'firebase/messaging'

const FIREBASE_CONFIG = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
}

const REQUIRED_CONFIG_KEYS = [
  'apiKey',
  'authDomain',
  'projectId',
  'messagingSenderId',
  'appId',
]

let firebaseApp
let foregroundUnsubscribe

function assertFirebaseConfig() {
  const missingKeys = REQUIRED_CONFIG_KEYS.filter((key) => !FIREBASE_CONFIG[key])

  if (missingKeys.length || !import.meta.env.VITE_FIREBASE_VAPID_KEY) {
    throw new Error('Firebase push config is missing. Check the VITE_FIREBASE_* values.')
  }
}

function getNotificationFromPayload(payload) {
  const notification = payload?.notification || {}
  const data = payload?.data || {}

  return {
    title: notification.title || data.title || 'yesh_mishak',
    options: {
      body: notification.body || data.body || '',
      icon: '/favicon.svg',
      data,
    },
  }
}

async function getFirebaseMessaging() {
  assertFirebaseConfig()

  if (!('serviceWorker' in navigator)) {
    throw new Error('Push notifications are not supported in this browser.')
  }

  if (!('Notification' in window)) {
    throw new Error('Notification permission is not supported in this browser.')
  }

  if (!(await isSupported())) {
    throw new Error('Firebase messaging is not supported in this browser.')
  }

  if (!firebaseApp) {
    firebaseApp = initializeApp(FIREBASE_CONFIG)
  }

  return getMessaging(firebaseApp)
}

async function requestNotificationPermission() {
  if (!('Notification' in window)) {
    throw new Error('Notification permission is not supported in this browser.')
  }

  if (Notification.permission === 'granted') {
    return 'granted'
  }

  if (Notification.permission === 'denied') {
    throw new Error('Push notification permission was denied. Enable it in your browser settings.')
  }

  const permission = await Notification.requestPermission()

  if (permission === 'denied') {
    throw new Error('Push notification permission was denied. Enable it in your browser settings.')
  }

  if (permission !== 'granted') {
    throw new Error('Push notification permission was not granted.')
  }

  return permission
}

async function registerFirebaseServiceWorker() {
  const workerParams = new URLSearchParams(
    Object.entries(FIREBASE_CONFIG).filter(([, value]) => Boolean(value)),
  )
  const registration = await navigator.serviceWorker.register(
    `/firebase-messaging-sw.js?${workerParams.toString()}`,
  )

  await navigator.serviceWorker.ready

  return registration
}

export async function startForegroundPushNotifications() {
  if (foregroundUnsubscribe) {
    return foregroundUnsubscribe
  }

  if (typeof window === 'undefined' || Notification.permission !== 'granted') {
    return null
  }

  const messaging = await getFirebaseMessaging()
  foregroundUnsubscribe = onMessage(messaging, async (payload) => {
    const { title, options } = getNotificationFromPayload(payload)

    try {
      new Notification(title, options)
    } catch {
      const registration = await navigator.serviceWorker.getRegistration('/firebase-messaging-sw.js')
      await registration?.showNotification(title, options)
    }
  })

  return foregroundUnsubscribe
}

export async function requestFirebasePushToken() {
  assertFirebaseConfig()
  await requestNotificationPermission()
  const registration = await registerFirebaseServiceWorker()
  const messaging = await getFirebaseMessaging()
  const token = await getToken(messaging, {
    vapidKey: import.meta.env.VITE_FIREBASE_VAPID_KEY,
    serviceWorkerRegistration: registration,
  })

  if (!token) {
    throw new Error('Firebase did not return a push token.')
  }

  await startForegroundPushNotifications()

  return token
}
