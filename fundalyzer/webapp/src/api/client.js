const BASE = '/api'

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  if (res.status === 204) return null
  return res.json()
}

// Groups
export const fetchGroups      = ()                   => request('/groups')
export const fetchGroup       = (name)               => request(`/groups/${name}`)
export const createGroup      = (name, tickers)      => request('/groups', { method: 'POST', body: JSON.stringify({ name, tickers }) })
export const deleteGroup      = (name)               => request(`/groups/${name}`, { method: 'DELETE' })

// Results
export const fetchLatestResult  = (group)            => request(`/results/${group}`)
export const fetchResultByDate  = (group, date)      => request(`/results/${group}/${date}`)
export const fetchAvailDates    = (group)            => request(`/results/${group}/dates`)
export const fetchCompanyResult = (group, ticker)    => request(`/results/${group}/company/${ticker}`)

// Analysis
export const triggerAnalysis  = (group)              => request(`/analyze/${group}`, { method: 'POST' })
export const fetchRunning     = ()                   => request('/analyze/running')

// Settings
export const fetchSettings    = ()                   => request('/settings')
export const patchSettings    = (body)               => request('/settings', { method: 'PATCH', body: JSON.stringify(body) })

// SSE — returns an EventSource; caller owns lifecycle
export const openAnalysisStream = (group) => new EventSource(`${BASE}/analyze/${group}/stream`)
