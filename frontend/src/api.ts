const API_BASE = import.meta.env?.VITE_API_BASE ?? "http://127.0.0.1:8000"

const formatErrorLocation = (loc: unknown) => (Array.isArray(loc) ? loc.map(String).join(".") : "")

const stringifyErrorItem = (item: unknown) => {
  if (typeof item === "string") {
    return item
  }

  if (item && typeof item === "object") {
    const detailItem = item as { loc?: unknown; msg?: unknown }
    if (typeof detailItem.msg === "string") {
      const location = formatErrorLocation(detailItem.loc)
      return location ? `${location}: ${detailItem.msg}` : detailItem.msg
    }
  }

  try {
    return JSON.stringify(item)
  } catch {
    return String(item)
  }
}

async function parseErrorMessage(response: Response): Promise<string> {
  const text = await response.text()

  if (!text) {
    return response.statusText || `HTTP ${response.status}`
  }

  try {
    const payload = JSON.parse(text) as { detail?: unknown }
    const detail = payload.detail

    if (typeof detail === "string") {
      return detail
    }

    if (Array.isArray(detail)) {
      return detail.map(stringifyErrorItem).join("\n")
    }

    return text || stringifyErrorItem(payload)
  } catch {
    return text
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`)
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }
  return response.json() as Promise<T>
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method: "POST" }
  if (body !== undefined) {
    init.headers = { "Content-Type": "application/json" }
    init.body = JSON.stringify(body)
  }

  const response = await fetch(`${API_BASE}${path}`, init)
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }
  return response.json() as Promise<T>
}

export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }
  return response.json() as Promise<T>
}

export async function apiDelete(path: string): Promise<void> {
  const response = await fetch(`${API_BASE}${path}`, { method: "DELETE" })
  if (!response.ok) {
    throw new Error(await parseErrorMessage(response))
  }
}
