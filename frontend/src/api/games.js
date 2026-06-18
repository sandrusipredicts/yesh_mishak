import { api } from './client'

export async function getActiveGames() {
  const response = await api.get('/games/active/')
  return response.data
}

export async function getUpcomingGames() {
  const response = await api.get('/games/upcoming/')
  return response.data
}

export async function createGame(data) {
  const response = await api.post('/games/', data)
  return response.data
}

function requireGameId(gameId) {
  if (!gameId) {
    throw new Error('Game id is required')
  }

  return gameId
}

export async function joinGame(gameId, userId) {
  const response = await api.post(
    `/games/${requireGameId(gameId)}/join`,
    { user_id: userId }
  )
  return response.data
}

export async function leaveGame(gameId, userId) {
  const response = await api.post(
    `/games/${requireGameId(gameId)}/leave`,
    { user_id: userId }
  )
  return response.data
}

export async function extendGame(gameId) {
  const response = await api.post(
    `/games/${requireGameId(gameId)}/extend`
  )
  return response.data
}

export async function closeGame(gameId) {
  const response = await api.post(
    `/games/${requireGameId(gameId)}/close`
  )
  return response.data
}
