export const API = '/api'
export async function request(path: string, options?: RequestInit) {
  const r = await fetch(API + path, options)
  const data = await r.json()
  if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail))
  return data
}
export function json(method: string, data?: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, ...(data === undefined ? {} : { body: JSON.stringify(data) }) }
}
