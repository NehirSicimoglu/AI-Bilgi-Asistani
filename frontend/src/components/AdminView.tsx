import { useEffect, useRef, useState } from 'react'
import {
  getAdminStats,
  getRecentLogs,
  listChunks,
  listDocuments,
  subscribeToLogs,
  type AdminStats,
  type ChunkItem,
  type DocumentItem,
  type LogEntry,
} from '../lib/api'
import { Icon } from './Icon'
import type { Tab } from './AppShell'

const LOG_SKIP_KEYS = new Set(['event', 'level', 'timestamp'])

function formatLogTime(iso: string) {
  return new Date(iso).toLocaleTimeString('tr-TR', { hour12: false })
}

function formatLogFields(entry: LogEntry) {
  return Object.entries(entry)
    .filter(([key]) => !LOG_SKIP_KEYS.has(key))
    .map(([key, value]) => `${key}=${typeof value === 'string' ? value : JSON.stringify(value)}`)
    .join('  ')
}

function logLevelColor(level: string) {
  if (level === 'error') return 'text-error'
  if (level === 'warning') return 'text-amber-500'
  return 'text-on-surface-variant'
}

const NAV_ITEMS: { id: Tab; label: string }[] = [
  { id: 'chat', label: 'Sohbet' },
  { id: 'documents', label: 'Dokümanlar' },
  { id: 'admin', label: 'Admin' },
]

function StatCard({
  label,
  value,
  icon,
  iconClassName,
  actionLabel,
  onAction,
}: {
  label: string
  value: string | number
  icon: string
  iconClassName: string
  actionLabel?: string
  onAction?: () => void
}) {
  return (
    <div className="rounded-xl border border-outline-variant/20 bg-surface-container-low p-4">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <div className={'flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ' + iconClassName}>
            <Icon name={icon} className="text-[18px]" />
          </div>
          <p className="text-[12px]/[16px] text-on-surface-variant">{label}</p>
        </div>
        {actionLabel && onAction && (
          <button
            onClick={onAction}
            className="rounded-lg px-2 py-1 text-[11px] font-medium text-primary transition-colors hover:bg-primary/10"
          >
            {actionLabel}
          </button>
        )}
      </div>
      <p className="mt-2 text-[24px]/[32px] font-semibold text-on-surface">{value}</p>
    </div>
  )
}

function StatusDot({ ok }: { ok: boolean | null }) {
  const color = ok === true ? 'bg-emerald-500' : ok === false ? 'bg-error' : 'bg-on-surface-variant/40'
  const title =
    ok === true ? 'Çalışıyor' : ok === false ? 'Son çağrı başarısız oldu' : 'Henüz test edilmedi'
  return <span className={'inline-block h-2 w-2 shrink-0 rounded-full ' + color} title={title} />
}

interface Props {
  onNavigate: (tab: Tab) => void
  onOpenMobileSidebar: () => void
}

export function AdminView({ onNavigate, onOpenMobileSidebar }: Props) {
  const [stats, setStats] = useState<AdminStats>()
  const [refreshing, setRefreshing] = useState(false)
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [logStatus, setLogStatus] = useState<'connecting' | 'open' | 'error'>('connecting')
  const logBoxRef = useRef<HTMLDivElement>(null)
  const stickToBottomRef = useRef(true)
  const [chunksOpen, setChunksOpen] = useState(false)
  const [chunks, setChunks] = useState<ChunkItem[]>([])
  const [chunksLoading, setChunksLoading] = useState(false)
  const [chunksNextOffset, setChunksNextOffset] = useState<string | null>(null)
  const [chunkDocs, setChunkDocs] = useState<DocumentItem[]>([])
  const [selectedDocId, setSelectedDocId] = useState('')

  async function loadStats() {
    const data = await getAdminStats()
    setStats(data)
  }

  async function loadChunksFor(docId: string) {
    setSelectedDocId(docId)
    setChunks([])
    setChunksNextOffset(null)
    setChunksLoading(true)
    const { items, next_offset } = await listChunks(docId ? { documentId: docId } : undefined)
    setChunks(items)
    setChunksNextOffset(next_offset)
    setChunksLoading(false)
  }

  async function openChunks() {
    setChunksOpen(true)
    // Doküman Seç dropdown'ı için indekslenen dokümanları getir
    listDocuments()
      .then(({ items }) => setChunkDocs(items))
      .catch(() => setChunkDocs([]))
    await loadChunksFor('')
  }

  async function loadMoreChunks() {
    if (!chunksNextOffset) return
    setChunksLoading(true)
    // "Daha fazla" yalnızca "Tümü" görünümünde geçerli (tek doküman tek seferde gelir)
    const { items, next_offset } = await listChunks({ offset: chunksNextOffset })
    setChunks((prev) => [...prev, ...items])
    setChunksNextOffset(next_offset)
    setChunksLoading(false)
  }

  useEffect(() => {
    loadStats()
  }, [])

  useEffect(() => {
    getRecentLogs()
      .then(setLogs)
      .catch(() => setLogs([]))
    const unsubscribe = subscribeToLogs(
      (entry) => setLogs((prev) => [...prev.slice(-299), entry]),
      setLogStatus,
    )
    return unsubscribe
  }, [])

  useEffect(() => {
    if (!stickToBottomRef.current) return
    const el = logBoxRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [logs])

  function handleLogScroll() {
    const el = logBoxRef.current
    if (!el) return
    stickToBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40
  }

  async function handleRefresh() {
    setRefreshing(true)
    await loadStats()
    setRefreshing(false)
  }

  return (
    <main className="relative flex h-full w-full flex-1 flex-col overflow-y-auto bg-background">
      <header className="sticky top-0 z-30 flex h-16 w-full items-center justify-between border-b border-outline-variant/10 bg-surface/80 px-gutter backdrop-blur-xl">
        <div className="flex items-center gap-4">
          <button
            className="flex items-center justify-center p-1 text-on-surface-variant transition-colors hover:text-on-surface md:hidden"
            onClick={onOpenMobileSidebar}
          >
            <Icon name="menu" />
          </button>
          <h1 className="hidden text-[20px]/[28px] font-bold text-heading md:block">
            AI Bilgi Asistanı
            <span className="ml-2 text-sm font-normal text-on-surface-variant">/ Admin</span>
          </h1>
        </div>
        <nav className="flex items-center gap-2">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              onClick={() => onNavigate(item.id)}
              className={
                'rounded-full px-4 py-1.5 text-[12px]/[16px] font-medium tracking-wide transition-colors ' +
                (item.id === 'admin'
                  ? 'bg-primary/10 text-primary'
                  : 'text-on-surface-variant hover:bg-primary/10 hover:text-primary')
              }
            >
              {item.label}
            </button>
          ))}
        </nav>
      </header>

      <div className="flex-1 px-4 pb-12 pt-8 md:px-8">
        <div className="mx-auto max-w-container-max space-y-8">
          <div className="flex items-center justify-between">
            <h2 className="text-[24px]/[32px] font-semibold text-on-surface md:text-[32px]/[40px]">
              Genel Bakış
            </h2>
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="flex items-center gap-1.5 rounded-lg border border-outline-variant/20 px-3 py-1.5 text-[12px]/[16px] font-medium text-on-surface-variant transition-colors hover:bg-surface-container-high disabled:opacity-50"
            >
              <Icon name="refresh" className={'text-[16px] ' + (refreshing ? 'animate-spin' : '')} />
              Yenile
            </button>
          </div>

          {!stats ? (
            <p className="text-[14px] text-on-surface-variant">Yükleniyor…</p>
          ) : (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
              <StatCard
                label="Doküman Sayısı"
                value={stats.documents_total}
                icon="description"
                iconClassName="bg-primary/10 text-primary"
              />
              <StatCard
                label="İndekslenen Chunk"
                value={stats.chunks_indexed}
                icon="dataset"
                iconClassName="bg-tertiary/10 text-tertiary"
                actionLabel="Göster"
                onAction={openChunks}
              />
              <StatCard
                label="Konuşma Sayısı"
                value={stats.conversations_total}
                icon="chat_bubble"
                iconClassName="bg-secondary/10 text-secondary"
              />
              <StatCard
                label="Chat İsteği"
                value={stats.chat_requests_total}
                icon="send"
                iconClassName="bg-primary/10 text-primary"
              />
              <StatCard
                label="Ort. Cevap süresi"
                value={
                  stats.avg_chat_latency_ms != null
                    ? `${(stats.avg_chat_latency_ms / 1000).toFixed(1)} sn`
                    : '—'
                }
                icon="schedule"
                iconClassName="bg-tertiary/10 text-tertiary"
              />
              <StatCard
                label="Toplam LLM token"
                value={stats.total_llm_tokens}
                icon="bolt"
                iconClassName="bg-secondary/10 text-secondary"
              />
            </div>
          )}

          {stats && (
            <div className="rounded-xl border border-outline-variant/20 bg-surface-container-low p-4">
              <div className="flex items-center gap-2">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Icon name="smart_toy" className="text-[18px]" />
                </div>
                <p className="text-[12px]/[16px] text-on-surface-variant">Aktif Modeller</p>
              </div>
              <div className="mt-3 flex flex-wrap gap-x-8 gap-y-2">
                <div>
                  <p className="text-[11px] text-on-surface-variant">Ana Model (cevap)</p>
                  <p className="flex items-center gap-1.5 text-[14px]/[20px] font-medium text-on-surface">
                    <StatusDot ok={stats.llm_model_ok} />
                    {stats.llm_model}
                  </p>
                </div>
                <div>
                  <p className="text-[11px] text-on-surface-variant">Sorgu Yeniden Yazma</p>
                  <p className="flex items-center gap-1.5 text-[14px]/[20px] font-medium text-on-surface">
                    <StatusDot ok={stats.llm_rewrite_model_ok} />
                    {stats.llm_rewrite_model}
                  </p>
                </div>
              </div>
            </div>
          )}

          <div className="rounded-xl border border-outline-variant/20 bg-surface-container-low p-4">
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-tertiary/10 text-tertiary">
                  <Icon name="terminal" className="text-[18px]" />
                </div>
                <p className="flex items-center gap-1.5 text-[12px]/[16px] text-on-surface-variant">
                  <span
                    className={
                      'inline-block h-2 w-2 rounded-full ' +
                      (logStatus === 'open'
                        ? 'bg-emerald-500'
                        : logStatus === 'error'
                          ? 'bg-error'
                          : 'bg-on-surface-variant/40')
                    }
                    title={
                      logStatus === 'open' ? 'Bağlı' : logStatus === 'error' ? 'Bağlantı koptu' : 'Bağlanıyor…'
                    }
                  />
                  Canlı Loglar
                </p>
              </div>
              <button
                onClick={() => setLogs([])}
                className="rounded-lg px-2 py-1 text-[11px] font-medium text-on-surface-variant transition-colors hover:bg-surface-container-high"
              >
                Temizle
              </button>
            </div>
            <div
              ref={logBoxRef}
              onScroll={handleLogScroll}
              className="h-72 overflow-y-auto rounded-lg bg-surface-container-lowest p-3 font-mono text-[11px]/[16px]"
            >
              {logs.length === 0 ? (
                <p className="text-on-surface-variant/50">
                  Henüz log yok. Sohbette bir soru sor, arka planda ne olduğunu buradan canlı izle.
                </p>
              ) : (
                logs.map((entry, i) => (
                  <div key={i} className="whitespace-pre-wrap break-all">
                    <span className="text-on-surface-variant/50">
                      {formatLogTime(String(entry.timestamp))}
                    </span>{' '}
                    <span className={'font-medium ' + logLevelColor(entry.level)}>{entry.event}</span>{' '}
                    <span className="text-on-surface-variant/70">{formatLogFields(entry)}</span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>

      {chunksOpen && (
        <div
          className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4"
          onClick={() => setChunksOpen(false)}
        >
          <div
            className="flex max-h-[80vh] w-full max-w-2xl flex-col rounded-2xl border border-outline-variant/10 bg-surface-container-high shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-outline-variant/10 px-5 py-4">
              <h2 className="text-[16px]/[24px] font-semibold text-on-surface">
                İndekslenen Chunk'lar
              </h2>
              <button
                onClick={() => setChunksOpen(false)}
                className="text-on-surface-variant transition-colors hover:text-on-surface"
              >
                <Icon name="close" className="text-[20px]" />
              </button>
            </div>
            {/* Doküman Seç: bir dokümanın chunk'larını sırayla incele */}
            <div className="flex items-center gap-2 border-b border-outline-variant/10 px-5 py-3">
              <Icon name="filter_list" className="text-[18px] text-on-surface-variant" />
              <select
                value={selectedDocId}
                onChange={(e) => loadChunksFor(e.target.value)}
                className="min-w-0 flex-1 rounded-lg border border-outline-variant/20 bg-surface-container py-1.5 px-2.5 text-[13px]/[20px] text-on-surface outline-none transition-colors focus:border-primary/50"
              >
                <option value="">Doküman Seç — Tümü ({stats?.documents_total ?? chunkDocs.length})</option>
                {chunkDocs.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.filename} ({d.num_chunks} chunk)
                  </option>
                ))}
              </select>
            </div>
            <div className="flex-1 overflow-y-auto px-5 py-4">
              {chunks.length === 0 && chunksLoading ? (
                <p className="text-[13px] text-on-surface-variant">Yükleniyor…</p>
              ) : chunks.length === 0 ? (
                <p className="text-[13px] text-on-surface-variant">Henüz indekslenmiş chunk yok.</p>
              ) : (
                <div className="flex flex-col gap-3">
                  {chunks.map((c) => (
                    <div
                      key={c.chunk_id}
                      className="rounded-xl border border-outline-variant/10 bg-surface-container-low p-3"
                    >
                      <div className="mb-1.5 flex items-center justify-between gap-2">
                        <span className="flex min-w-0 items-center gap-2">
                          {c.index != null && (
                            <span className="shrink-0 rounded-md bg-primary/10 px-1.5 py-0.5 font-mono text-[11px] font-medium text-primary">
                              #{c.index}
                            </span>
                          )}
                          <span className="truncate text-[12px]/[16px] font-medium text-primary">
                            {c.document_name || 'Bilinmeyen doküman'}
                          </span>
                          {!c.enabled && (
                            <span className="shrink-0 rounded-full bg-error/10 px-2 py-0.5 text-[10px] font-medium text-error">
                              Devre Dışı
                            </span>
                          )}
                        </span>
                        {c.page != null && (
                          <span className="shrink-0 text-[11px] text-on-surface-variant/60">
                            sayfa {c.page}
                          </span>
                        )}
                      </div>
                      <p className="whitespace-pre-wrap text-[13px]/[20px] text-on-surface-variant">
                        {c.text}
                      </p>
                    </div>
                  ))}
                  {chunksNextOffset && (
                    <button
                      onClick={loadMoreChunks}
                      disabled={chunksLoading}
                      className="self-center rounded-lg px-3 py-1.5 text-[12px] font-medium text-primary transition-colors hover:bg-primary/10 disabled:opacity-50"
                    >
                      {chunksLoading ? 'Yükleniyor…' : 'Daha fazla yükle'}
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </main>
  )
}
