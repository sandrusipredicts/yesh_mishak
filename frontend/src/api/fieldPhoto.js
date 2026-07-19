import { Capacitor } from '@capacitor/core'
import { Camera, CameraDirection, MediaTypeSelection } from '@capacitor/camera'

export const FIELD_PHOTO_MAX_BYTES = 5 * 1024 * 1024
export const FIELD_PHOTO_ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp']

const TYPE_TO_EXTENSION = {
  'image/jpeg': 'jpg',
  'image/png': 'png',
  'image/webp': 'webp',
}

export function isNativeCameraAvailable() {
  return Capacitor.isNativePlatform() && Capacitor.isPluginAvailable('Camera')
}

export function validateFieldPhotoFile(file) {
  if (!file) {
    return { ok: false, error: 'missing' }
  }
  if (!FIELD_PHOTO_ALLOWED_TYPES.includes(file.type)) {
    return { ok: false, error: 'unsupported_type' }
  }
  if (file.size > FIELD_PHOTO_MAX_BYTES) {
    return { ok: false, error: 'too_large' }
  }
  return { ok: true }
}

export function buildFieldPhotoSelection(file, { previewUrl, source }) {
  const validation = validateFieldPhotoFile(file)
  if (!validation.ok) {
    return validation
  }

  return {
    ok: true,
    photo: {
      file,
      previewUrl,
      source,
    },
  }
}

function isCancellation(error) {
  const code = String(error?.code ?? '')
  const message = String(error?.message ?? '')
  return code === 'OS-PLUG-CAMR-0006' ||
    code === 'OS-PLUG-CAMR-0020' ||
    /cancel/i.test(code) ||
    /cancel/i.test(message)
}

function isPermissionDenied(error) {
  const code = String(error?.code ?? '')
  const message = String(error?.message ?? '')
  return code === 'OS-PLUG-CAMR-0003' ||
    code === 'OS-PLUG-CAMR-0005' ||
    /denied|permission/i.test(code) ||
    /denied|permission|access wasn't provided/i.test(message)
}

function inferTypeFromPath(path) {
  const lower = String(path ?? '').toLowerCase()
  if (lower.includes('.png')) return 'image/png'
  if (lower.includes('.webp')) return 'image/webp'
  return 'image/jpeg'
}

async function loadMediaResult(result, source) {
  if (!result?.webPath) {
    return { ok: false, error: 'unavailable' }
  }

  const response = await fetch(result.webPath)
  const blob = await response.blob()
  const mimeType = blob.type || inferTypeFromPath(result.webPath)
  const extension = TYPE_TO_EXTENSION[mimeType] || 'jpg'
  const file = new File([blob], `field-photo.${extension}`, { type: mimeType })

  return buildFieldPhotoSelection(file, {
    previewUrl: result.webPath,
    source,
  })
}

async function runNativePhotoAction(action) {
  if (!isNativeCameraAvailable()) {
    return { ok: false, error: 'unavailable' }
  }

  try {
    return await action()
  } catch (error) {
    if (isCancellation(error)) {
      return { ok: false, error: 'cancelled' }
    }
    if (isPermissionDenied(error)) {
      return { ok: false, error: 'permission_denied' }
    }
    return { ok: false, error: 'capture_failed' }
  }
}

export function captureFieldPhoto() {
  return runNativePhotoAction(async () => {
    const result = await Camera.takePhoto({
      quality: 75,
      targetWidth: 1600,
      targetHeight: 1600,
      cameraDirection: CameraDirection.Rear,
      saveToGallery: false,
      includeMetadata: false,
    })
    return loadMediaResult(result, 'camera')
  })
}

export function chooseExistingFieldPhoto() {
  return runNativePhotoAction(async () => {
    const { results } = await Camera.chooseFromGallery({
      quality: 75,
      targetWidth: 1600,
      targetHeight: 1600,
      limit: 1,
      allowMultipleSelection: false,
      mediaType: MediaTypeSelection.Photo,
      includeMetadata: false,
    })
    return loadMediaResult(results?.[0], 'camera')
  })
}

export function selectFieldPhotoFile(file) {
  if (!file) {
    return { ok: false, error: 'cancelled' }
  }

  return buildFieldPhotoSelection(file, {
    previewUrl: URL.createObjectURL(file),
    source: 'file',
  })
}
