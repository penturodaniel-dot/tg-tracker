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

export function fetchConvs(status = 'open', offset = 0, tagId = null) {
  const params = new URLSearchParams({ status, offset })
  if (tagId) params.set('tag_id', tagId)
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

export function deleteMessage(msgId) {
  return fetch(`/api/tga/message/${msgId}`, {
    method: 'DELETE',
    credentials: 'same-origin',
  }).then(res => {
    if (res.status === 401) { window.location.href = '/login'; throw new Error('Unauthorized') }
    if (!res.ok) throw new Error(`DELETE message failed: ${res.status}`)
    return res.json()
  })
}

export function editMessage(msgId, text) {
  return fetch(`/api/tga/message/${msgId}`, {
    method: 'PATCH',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  }).then(res => {
    if (res.status === 401) { window.location.href = '/login'; throw new Error('Unauthorized') }
    if (!res.ok) throw new Error(`PATCH message failed: ${res.status}`)
    return res.json()
  })
}

// ── Scripts ──────────────────────────────────────────────────────────────────

export function fetchScripts() {
  return get('/api/tg_account/scripts')
}

// ── User Status ───────────────────────────────────────────────────────────────

export function fetchUserStatus(tgUserId) {
  return get(`/api/tg_user_status/${tgUserId}`)
}

// ── TG Account Status ────────────────────────────────────────────────────────

export function fetchTgAccountStatus() {
  return get('/api/tg_account/status')
}

// ── Tags ─────────────────────────────────────────────────────────────────────

export function fetchAllTags() {
  return get('/api/tags')
}

export function addConvTag(convId, tagId) {
  return fetch('/api/conv_tag/add', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ conv_type: 'tga', conv_id: convId, tag_id: tagId }),
  }).then(res => {
    if (res.status === 401) { window.location.href = '/login'; throw new Error('Unauthorized') }
    if (!res.ok) throw new Error(`POST /api/conv_tag/add failed: ${res.status}`)
    return res.json()
  })
}

export function removeConvTag(convId, tagId) {
  return fetch('/api/conv_tag/remove', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ conv_type: 'tga', conv_id: convId, tag_id: tagId }),
  }).then(res => {
    if (res.status === 401) { window.location.href = '/login'; throw new Error('Unauthorized') }
    if (!res.ok) throw new Error(`POST /api/conv_tag/remove failed: ${res.status}`)
    return res.json()
  })
}
