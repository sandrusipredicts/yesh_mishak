import { api } from './client'

export async function getActiveGames() {
  const response = await api.get('/games/active')
  return response.data
}

export async function createGame(data) {
  const response = await api.post('/games', data)
  return response.data
}

export async function joinGame(gameId) {
  const response = await api.post(`/games/${gameId}/join`)
  return response.data
}

export async function leaveGame(gameId) {
  const response = await api.post(`/games/${gameId}/leave`)
  return response.data
}

export async function extendGame(gameId) {
  const response = await api.post(`/games/${gameId}/extend`)
  return response.data
}

export async function closeGame(gameId) {
  const response = await api.post(`/games/${gameId}/close`)
  return response.data
}
