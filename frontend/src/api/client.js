import axios from 'axios'

/**
 * S-GLOBAL DOMINION — Axios API Client
 * VERSHINA v200.11 Protocol
 * 
 * withCredentials: true — КРИТИЧНО для httpOnly cookie auth.
 * Все запросы к бэкенду должны идти через этот инстанс.
 */
const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
  withCredentials: true,
})

export default api
