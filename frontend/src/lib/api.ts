// Backend REST/SSE API istemcisi. Tek dosyada tutuluyor — proje küçük
// ölçekli olduğu için ayrı bir HTTP kütüphanesi (axios vb.) gerekmiyor,
// yerleşik fetch yeterli.

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
const API = `${API_BASE}/api/v1`
const API_KEY = import.meta.env.VITE_API_KEY as string | undefined

// Her isteğe eklenir (backend `API_KEY` ayarlıysa zorunlu). fetch'in 2. argümanı
// olarak init nesnesine header'ı ekler; body/method gibi diğer alanları korur.
function withAuth(init: RequestInit = {}): RequestInit {
  if (!API_KEY) return init
  return { ...init, headers: { ...init.headers, 'X-API-Key': API_KEY } }
}

export type DocumentStatus = 'pending' | 'processing' | 'indexed' | 'failed'

export interface DocumentItem {
  id: string
  filename: string
  extension: string
  category: string | null
  size_bytes: number
  num_chunks: number
  status: DocumentStatus
  error: string | null
  enabled: boolean
  created_at: string
}

export interface Source {
  marker: number
  chunk_id: string
  document_id: string
  document_name: string
  page: number | null
  snippet: string
  score: number | null
}

export interface AdminStats {
  documents_total: number
  documents_by_status: Record<string, number>
  chunks_indexed: number
  conversations_total: number
  chat_requests_total: number
  avg_chat_latency_ms: number | null
  total_llm_tokens: number
  llm_model: string
  llm_rewrite_model: string
  llm_model_ok: boolean | null
  llm_rewrite_model_ok: boolean | null
}

// HTTP durum kodunu taşır; çağıranlar 401'i (yanlış/eksik API anahtarı) diğer
// hatalardan ayırıp kullanıcıya doğru mesajı gösterebilsin diye.
export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }

  get isAuthError(): boolean {
    return this.status === 401
  }
}

async function asJson<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    const body = await resp.text()
    throw new ApiError(resp.status, `${resp.status} ${resp.statusText}: ${body}`)
  }
  return resp.json() as Promise<T>
}

export async function listDocuments(): Promise<{ total: number; items: DocumentItem[] }> {
  return asJson(await fetch(`${API}/documents`, withAuth()))
}

export async function uploadDocument(file: File): Promise<DocumentItem> {
  const form = new FormData()
  form.append('file', file)
  return asJson(await fetch(`${API}/documents`, withAuth({ method: 'POST', body: form })))
}

export async function setDocumentEnabled(id: string, enabled: boolean): Promise<DocumentItem> {
  return asJson(
    await fetch(
      `${API}/documents/${id}`,
      withAuth({
        method: 'PATCH',
        headers: jsonHeaders,
        body: JSON.stringify({ enabled }),
      }),
    ),
  )
}

export async function deleteDocument(id: string): Promise<void> {
  const resp = await fetch(`${API}/documents/${id}`, withAuth({ method: 'DELETE' }))
  if (!resp.ok && resp.status !== 404) {
    throw new Error(`${resp.status} ${resp.statusText}`)
  }
}

export interface ConversationSummary {
  id: string
  title: string | null
  pinned: boolean
  project_id: string | null
  created_at: string
  updated_at: string
}

export async function listConversations(): Promise<{ total: number; items: ConversationSummary[] }> {
  return asJson(await fetch(`${API}/conversations`, withAuth()))
}

export async function createConversation(): Promise<ConversationSummary> {
  return asJson(
    await fetch(
      `${API}/conversations`,
      withAuth({ method: 'POST', body: JSON.stringify({}), headers: jsonHeaders }),
    ),
  )
}

export async function renameConversation(id: string, title: string): Promise<ConversationSummary> {
  return asJson(
    await fetch(
      `${API}/conversations/${id}`,
      withAuth({
        method: 'PATCH',
        headers: jsonHeaders,
        body: JSON.stringify({ title }),
      }),
    ),
  )
}

export async function setConversationPinned(id: string, pinned: boolean): Promise<ConversationSummary> {
  return asJson(
    await fetch(
      `${API}/conversations/${id}`,
      withAuth({
        method: 'PATCH',
        headers: jsonHeaders,
        body: JSON.stringify({ pinned }),
      }),
    ),
  )
}

export async function setConversationProject(
  id: string,
  projectId: string | null,
): Promise<ConversationSummary> {
  return asJson(
    await fetch(
      `${API}/conversations/${id}`,
      withAuth({
        method: 'PATCH',
        headers: jsonHeaders,
        body: JSON.stringify({ project_id: projectId }),
      }),
    ),
  )
}

export async function deleteConversation(id: string): Promise<void> {
  const resp = await fetch(`${API}/conversations/${id}`, withAuth({ method: 'DELETE' }))
  if (!resp.ok && resp.status !== 404) throw new Error(`${resp.status} ${resp.statusText}`)
}

export interface Project {
  id: string
  name: string
  created_at: string
}

export async function listProjects(): Promise<{ total: number; items: Project[] }> {
  return asJson(await fetch(`${API}/projects`, withAuth()))
}

export async function createProject(name: string): Promise<Project> {
  return asJson(
    await fetch(
      `${API}/projects`,
      withAuth({
        method: 'POST',
        headers: jsonHeaders,
        body: JSON.stringify({ name }),
      }),
    ),
  )
}

export async function renameProject(id: string, name: string): Promise<Project> {
  return asJson(
    await fetch(
      `${API}/projects/${id}`,
      withAuth({
        method: 'PATCH',
        headers: jsonHeaders,
        body: JSON.stringify({ name }),
      }),
    ),
  )
}

export async function deleteProject(id: string): Promise<void> {
  const resp = await fetch(`${API}/projects/${id}`, withAuth({ method: 'DELETE' }))
  if (!resp.ok && resp.status !== 404) throw new Error(`${resp.status} ${resp.statusText}`)
}

export interface StoredMessage {
  role: 'user' | 'assistant'
  content: string
  citations: Source[]
}

// Sayfa yenilendiğinde geçmişi geri yüklemek için (conversation_id localStorage'da tutulur).
export async function getConversation(
  id: string,
): Promise<{ id: string; created_at: string; messages: StoredMessage[] }> {
  const resp = await fetch(`${API}/conversations/${id}`, withAuth())
  if (resp.status === 404) throw new Error('not_found')
  return asJson(resp)
}

export async function getAdminStats(): Promise<AdminStats> {
  return asJson(await fetch(`${API}/admin/stats`, withAuth()))
}

export interface ChunkItem {
  chunk_id: string
  document_id: string
  document_name: string
  index: number | null
  text: string
  page: number | null
  enabled: boolean
}

export async function listChunks(
  opts?: { offset?: string; documentId?: string },
): Promise<{ items: ChunkItem[]; next_offset: string | null }> {
  const url = new URL(`${API}/admin/chunks`)
  url.searchParams.set('limit', '50')
  if (opts?.offset) url.searchParams.set('offset', opts.offset)
  if (opts?.documentId) url.searchParams.set('document_id', opts.documentId)
  return asJson(await fetch(url, withAuth()))
}

export interface LogEntry {
  event: string
  level: string
  timestamp: string
  [key: string]: unknown
}

export async function getRecentLogs(): Promise<LogEntry[]> {
  return asJson(await fetch(`${API}/admin/logs/recent`, withAuth()))
}

export function subscribeToLogs(
  onEntry: (entry: LogEntry) => void,
  onStatusChange?: (status: 'open' | 'error') => void,
): () => void {
  // EventSource özel header ekleyemez; anahtar query param olarak taşınır
  // (backend `require_api_key` header veya query'i kabul eder).
  const url = new URL(`${API}/admin/logs/stream`)
  if (API_KEY) url.searchParams.set('api_key', API_KEY)
  const source = new EventSource(url)
  source.onopen = () => onStatusChange?.('open')
  source.onerror = () => onStatusChange?.('error')
  source.onmessage = (e) => {
    if (!e.data) return
    onEntry(JSON.parse(e.data))
  }
  return () => source.close()
}

const jsonHeaders = { 'Content-Type': 'application/json' }

export interface StreamHandlers {
  onToken?: (text: string) => void
  onCitations?: (citations: Source[]) => void
  onError?: (message: string) => void
}

// Backend'in POST /chat/stream ucu SSE (`event: ...\ndata: ...\n\n`) döner.
// Tarayıcının EventSource'u yalnızca GET destekler, bu yüzden fetch + manuel
// ayrıştırma kullanıyoruz (native ReadableStream, ekstra kütüphane gerekmez).
export async function streamChat(
  query: string,
  conversationId: string | undefined,
  handlers: StreamHandlers,
): Promise<void> {
  const resp = await fetch(
    `${API}/chat/stream`,
    withAuth({
      method: 'POST',
      headers: jsonHeaders,
      body: JSON.stringify({ query, conversation_id: conversationId ?? null }),
    }),
  )
  if (!resp.ok || !resp.body) {
    handlers.onError?.(`${resp.status} ${resp.statusText}`)
    return
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    let sep = buffer.indexOf('\n\n')
    while (sep !== -1) {
      dispatchEvent(buffer.slice(0, sep), handlers)
      buffer = buffer.slice(sep + 2)
      sep = buffer.indexOf('\n\n')
    }
  }
}

function dispatchEvent(block: string, handlers: StreamHandlers): void {
  let event = 'message'
  let data = ''
  for (const line of block.split('\n')) {
    if (line.startsWith('event: ')) event = line.slice(7)
    else if (line.startsWith('data: ')) data = line.slice(6)
  }
  if (!data) return
  const payload = JSON.parse(data)

  if (event === 'token') handlers.onToken?.(payload.text)
  else if (event === 'citations') handlers.onCitations?.(payload.citations)
  else if (event === 'error') handlers.onError?.(payload.message)
}
