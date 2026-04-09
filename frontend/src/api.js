/**
 * api.js – thin wrappers around fetch for the TG CRM backend.
 * All requests use same-origin cookie auth.
 * A 401 response redirects the browser to /login.
 */

function handleUnauth(res) {
  if (res.status === 401) {
    window.location.href = '/login'
    throw new Error('Unauthorized')
  }
  return res
}

export async function get(url) {
  const res = await fetch(url, { credentials: 'same-origin' })
  handleUnauth(res)
  if (!res.ok) throw new Error(`GET ${url} failed: ${res.status}`)
  return res.json()
}

export async function postForm(url, data) {
  const form = new FormData()
  Object.entries(data).forEach(([k, v]) => {
    if (v !== undefined && v !== null) form.append(k, v)
  })
  const res = await fetch(url, {
    method: 'POST',
    credentials: 'same-origin',
    body: form,
  })
  handleUnauth(res)
  if (!res.ok) throw new Error(`POST ${url} failed: ${res.status}`)
  return res.json()
}

// ── Convs ────────────────────────────────────────────────────────────────────

export function fetchConvs(status = 'open', offset = 0) {
  const params = new URLSearchParams({ status, offset })
  return get(`/api/tg_account_convs?${params}`)
}

export function fetchConv(convId) {
  return get(`/api/tg_account/conv/${convId}`)
}

// ── Messages ─────────────────────────────────────────────────────────────────

export function fetchMessages(convId, afterId = 0) {
  return get(`/api/tg_account_messages/${convId}?after=${afterId}`)
}

export function markRead(convId) {
  return postForm('/api/tg_account/mark_read', { conv_id: convId })
}

// ── Actions ──────────────────────────────────────────────────────────────────

export function sendMessage(convId, text) {
  return postForm('/tg_account/send', { conv_id: convId, text })
}

export function sendMedia(convId, file) {
  return postForm('/tg_account/send_media', { conv_id: convId, file })
}

export function closeConv(convId) {
  return postForm('/tg_account/close', { conv_id: convId })
}

export function reopenConv(convId) {
  return postForm('/tg_account/reopen', { conv_id: convId })
}

export function deleteConv(convId) {
  return postForm('/tg_account/delete', { conv_id: convId })
}

export function sendLead(convId) {
  return postForm('/tg_account/send_lead', { conv_id: convId })
}

// ── Scripts ──────────────────────────────────────────────────────────────────

export function fetchScripts() {
  return get('/api/tg_account/scripts')
}

// ── User Status ───────────────────────────────────────────────────────────────

export function fetchUserStatus(tgUserId) {
  return get(`/api/tg_user_status/${tgUserId}`)
}
