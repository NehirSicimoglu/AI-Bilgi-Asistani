import { useEffect, useRef, useState } from 'react'
import {
  deleteDocument,
  listDocuments,
  setDocumentEnabled,
  uploadDocument,
  type DocumentItem,
  type DocumentStatus,
} from '../lib/api'
import { ConfirmDialog } from './ConfirmDialog'
import { Icon } from './Icon'
import type { Tab } from './AppShell'

const SUPPORTED_FORMATS = ['PDF', 'DOCX', 'XLSX', 'TXT', 'MD']
const INITIAL_VISIBLE = 6

const NAV_ITEMS: { id: Tab; label: string }[] = [
  { id: 'chat', label: 'Sohbet' },
  { id: 'documents', label: 'Dokümanlar' },
  { id: 'admin', label: 'Admin' },
]

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatRelativeDate(iso: string): string {
  const date = new Date(iso)
  const now = new Date()
  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const diffDays = Math.round((startOfDay(now) - startOfDay(date)) / 86_400_000)
  const time = date.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' })

  if (diffDays === 0) return `Bugün, ${time}`
  if (diffDays === 1) return `Dün, ${time}`
  return date.toLocaleDateString('tr-TR', { day: 'numeric', month: 'short', year: 'numeric' })
}

function fileIcon(extension: string): { icon: string; className: string } {
  switch (extension) {
    case '.pdf':
      return { icon: 'picture_as_pdf', className: 'bg-error/10 text-error' }
    case '.docx':
      return { icon: 'description', className: 'bg-primary/10 text-primary' }
    case '.xlsx':
      return { icon: 'table_chart', className: 'bg-secondary/10 text-secondary' }
    case '.md':
      return { icon: 'article', className: 'bg-tertiary/10 text-tertiary' }
    default:
      return { icon: 'article', className: 'bg-outline-variant/20 text-outline' }
  }
}

function StatusBadge({
  status,
  error,
  enabled,
}: {
  status: DocumentStatus
  error: string | null
  enabled: boolean
}) {
  if (!enabled) {
    return (
      <>
        <div className="h-2 w-2 rounded-full bg-outline" />
        <span className="text-[14px]/[22px] text-outline">Devre Dışı</span>
      </>
    )
  }
  if (status === 'indexed') {
    return (
      <>
        <div className="h-2 w-2 rounded-full bg-emerald-400" />
        <span className="text-[14px]/[22px] text-emerald-400">Aktif</span>
      </>
    )
  }
  if (status === 'processing') {
    return (
      <>
        <Icon name="sync" className="animate-spin text-[16px] text-primary" />
        <span className="text-[14px]/[22px] text-primary">İşleniyor</span>
      </>
    )
  }
  if (status === 'failed') {
    return (
      <>
        <div className="h-2 w-2 rounded-full bg-error" />
        <span className="text-[14px]/[22px] text-error" title={error ?? undefined}>
          Başarısız
        </span>
      </>
    )
  }
  return (
    <>
      <div className="h-2 w-2 rounded-full bg-outline" />
      <span className="text-[14px]/[22px] text-outline">Bekliyor</span>
    </>
  )
}

function ToggleSwitch({ checked, onChange }: { checked: boolean; onChange: () => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      title={checked ? 'Devre Dışı Bırak' : 'Etkinleştir'}
      onClick={(e) => {
        e.stopPropagation()
        onChange()
      }}
      className={
        'relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors ' +
        (checked ? 'bg-emerald-500' : 'bg-outline-variant/50')
      }
    >
      <span
        className={
          'inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ' +
          (checked ? 'translate-x-[18px]' : 'translate-x-1')
        }
      />
    </button>
  )
}

interface Props {
  onNavigate: (tab: Tab) => void
  onOpenMobileSidebar: () => void
}

export function DocumentsView({ onNavigate, onOpenMobileSidebar }: Props) {
  const [docs, setDocs] = useState<DocumentItem[]>([])
  const [uploading, setUploading] = useState(false)
  const [dragActive, setDragActive] = useState(false)
  const [showAll, setShowAll] = useState(false)
  const [error, setError] = useState<string>()
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'inactive'>('all')
  const [sortOrder, setSortOrder] = useState<'newest' | 'oldest'>('newest')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [confirmDelete, setConfirmDelete] = useState<{ id: string; name: string } | null>(null)
  const [confirmBulkDelete, setConfirmBulkDelete] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  async function refresh() {
    const { items } = await listDocuments()
    setDocs(items)
  }

  useEffect(() => {
    refresh()
  }, [])

  useEffect(() => {
    setSelectedIds(new Set())
  }, [search, statusFilter])

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return
    setUploading(true)
    setError(undefined)
    for (const file of Array.from(files)) {
      try {
        await uploadDocument(file)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Yükleme başarısız.')
      }
    }
    setUploading(false)
    if (fileInput.current) fileInput.current.value = ''
    await refresh()
  }

  async function handleDelete(id: string) {
    await deleteDocument(id)
    await refresh()
  }

  async function handleToggleEnabled(doc: DocumentItem) {
    const updated = await setDocumentEnabled(doc.id, !doc.enabled)
    setDocs((prev) => prev.map((d) => (d.id === updated.id ? updated : d)))
  }

  function toggleSelectOne(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleSelectAll() {
    setSelectedIds((prev) => {
      const allSelected = visibleDocs.length > 0 && visibleDocs.every((d) => prev.has(d.id))
      return allSelected ? new Set() : new Set(visibleDocs.map((d) => d.id))
    })
  }

  async function handleActivateSelected() {
    const ids = Array.from(selectedIds)
    await Promise.all(ids.map((id) => setDocumentEnabled(id, true)))
    setSelectedIds(new Set())
    await refresh()
  }

  async function handleDeactivateSelected() {
    const ids = Array.from(selectedIds)
    await Promise.all(ids.map((id) => setDocumentEnabled(id, false)))
    setSelectedIds(new Set())
    await refresh()
  }

  async function handleDeleteSelected() {
    const ids = Array.from(selectedIds)
    await Promise.all(ids.map((id) => deleteDocument(id)))
    setSelectedIds(new Set())
    await refresh()
  }

  const filteredDocs = docs
    .filter((d) => {
      if (statusFilter === 'active' && !d.enabled) return false
      if (statusFilter === 'inactive' && d.enabled) return false
      return d.filename.toLowerCase().includes(search.toLowerCase())
    })
    .sort((a, b) => {
      const diff = new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
      return sortOrder === 'newest' ? -diff : diff
    })
  const visibleDocs = showAll ? filteredDocs : filteredDocs.slice(0, INITIAL_VISIBLE)
  const allVisibleSelected = visibleDocs.length > 0 && visibleDocs.every((d) => selectedIds.has(d.id))

  return (
    <main className="relative flex h-full w-full flex-1 flex-col overflow-y-auto bg-background">
      {/* Üst bar */}
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
            <span className="ml-2 text-sm font-normal text-on-surface-variant">/ Dokümanlar</span>
          </h1>
        </div>
        <nav className="flex items-center gap-2">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              onClick={() => onNavigate(item.id)}
              className={
                'rounded-full px-4 py-1.5 text-[12px]/[16px] font-medium tracking-wide transition-colors ' +
                (item.id === 'documents'
                  ? 'bg-primary/10 text-primary'
                  : 'text-on-surface-variant hover:bg-primary/10 hover:text-primary')
              }
            >
              {item.label}
            </button>
          ))}
        </nav>
      </header>

      {/* İçerik */}
      <div className="flex-1 px-4 pb-12 pt-8 md:px-8">
        <div className="mx-auto max-w-container-max space-y-8">
          <h2 className="text-[24px]/[32px] font-semibold text-on-surface md:text-[32px]/[40px]">
            Bilgi Tabanı
          </h2>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            {/* Yükleme alanı */}
            <div className="lg:col-span-1">
              <div
                className={
                  'flex h-full min-h-[300px] flex-col items-center justify-center rounded-xl border-2 border-dashed p-8 text-center transition-colors duration-200 ' +
                  (dragActive ? 'border-primary/70 bg-surface-container' : 'border-outline-variant/40 bg-surface-container-low')
                }
                onDragOver={(e) => {
                  e.preventDefault()
                  setDragActive(true)
                }}
                onDragLeave={() => setDragActive(false)}
                onDrop={(e) => {
                  e.preventDefault()
                  setDragActive(false)
                  handleFiles(e.dataTransfer.files)
                }}
              >
                <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-primary/10">
                  <Icon name="cloud_upload" className="text-3xl text-primary" />
                </div>
                <h3 className="mb-2 text-[20px]/[28px] font-medium text-on-surface">Doküman Yükle</h3>
                <p className="mb-6 text-[14px]/[22px] text-on-surface-variant">
                  Dosyaları buraya sürükleyip bırakın veya göz atmak için tıklayın.
                </p>
                <div className="mb-6 flex flex-wrap justify-center gap-2">
                  {SUPPORTED_FORMATS.map((f) => (
                    <span key={f} className="rounded bg-surface-container px-2 py-1 text-xs text-on-surface-variant">
                      {f}
                    </span>
                  ))}
                </div>
                <button
                  className="rounded-lg bg-primary px-6 py-2 text-[12px]/[16px] font-medium text-on-primary shadow-lg transition-colors hover:bg-primary-container hover:text-on-primary-container disabled:opacity-50"
                  onClick={() => fileInput.current?.click()}
                  disabled={uploading}
                >
                  {uploading ? 'Yükleniyor…' : 'Dosyaları Seç'}
                </button>
                <input
                  ref={fileInput}
                  type="file"
                  multiple
                  accept=".pdf,.docx,.xlsx,.txt,.md"
                  className="hidden"
                  onChange={(e) => handleFiles(e.target.files)}
                />
                {error && <p className="mt-3 text-xs text-error">{error}</p>}
              </div>
            </div>

            {/* Doküman listesi */}
            <div className="flex flex-col overflow-hidden rounded-xl border border-outline-variant/20 bg-surface-container-low lg:col-span-2">
              <div className="flex flex-col gap-3 border-b border-outline-variant/10 bg-surface/30 p-5 sm:flex-row sm:items-center sm:justify-between">
                <h3 className="text-[20px]/[28px] font-medium text-on-surface">Son Dokümanlar</h3>
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                  <div className="relative flex items-center">
                    <Icon name="search" className="absolute left-3 text-[18px] text-on-surface-variant" />
                    <input
                      type="text"
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      placeholder="Doküman ara…"
                      className="w-full rounded-lg border border-outline-variant/20 bg-surface-container py-1.5 pl-9 pr-3 text-[13px]/[20px] text-on-surface outline-none transition-colors placeholder:text-on-surface-variant/50 focus:border-primary/50 sm:w-48"
                    />
                  </div>
                  <div className="flex rounded-lg border border-outline-variant/20 bg-surface-container p-0.5">
                    {(
                      [
                        { id: 'all', label: 'Tümü' },
                        { id: 'active', label: 'Aktif' },
                        { id: 'inactive', label: 'Devre Dışı' },
                      ] as const
                    ).map((f) => (
                      <button
                        key={f.id}
                        onClick={() => setStatusFilter(f.id)}
                        className={
                          'whitespace-nowrap rounded-md px-2.5 py-1 text-[12px]/[16px] font-medium transition-colors ' +
                          (statusFilter === f.id
                            ? 'bg-primary text-on-primary'
                            : 'text-on-surface-variant hover:text-on-surface')
                        }
                      >
                        {f.label}
                      </button>
                    ))}
                  </div>
                  <button
                    onClick={() => setSortOrder((o) => (o === 'newest' ? 'oldest' : 'newest'))}
                    title={sortOrder === 'newest' ? 'En yeni önce' : 'En eski önce'}
                    className="flex items-center gap-1.5 whitespace-nowrap rounded-lg border border-outline-variant/20 bg-surface-container px-2.5 py-1.5 text-[12px]/[16px] font-medium text-on-surface-variant transition-colors hover:text-on-surface"
                  >
                    <Icon name="swap_vert" className="text-[18px]" />
                    {sortOrder === 'newest' ? 'En yeni' : 'En eski'}
                  </button>
                </div>
              </div>

              {selectedIds.size > 0 && (
                <div className="flex items-center justify-between border-b border-outline-variant/10 bg-primary/10 px-5 py-2.5">
                  <span className="text-[13px]/[20px] text-on-surface">
                    {selectedIds.size} doküman seçildi
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      className="rounded-lg bg-primary px-3 py-1.5 text-[12px]/[16px] font-medium text-on-primary transition-colors hover:bg-primary-fixed"
                      onClick={handleActivateSelected}
                    >
                      Etkinleştir
                    </button>
                    <button
                      className="rounded-lg border border-outline-variant/30 px-3 py-1.5 text-[12px]/[16px] font-medium text-on-surface transition-colors hover:bg-surface-container-high"
                      onClick={handleDeactivateSelected}
                    >
                      Devre Dışı Bırak
                    </button>
                    <button
                      className="rounded-lg border border-error/30 px-3 py-1.5 text-[12px]/[16px] font-medium text-error transition-colors hover:bg-error/10"
                      onClick={() => setConfirmBulkDelete(true)}
                    >
                      Sil
                    </button>
                  </div>
                </div>
              )}

              <div className="flex-1 overflow-y-auto">
                <div className="grid grid-cols-12 gap-4 border-b border-outline-variant/10 bg-surface/10 px-5 py-3 text-xs font-medium uppercase tracking-wider text-on-surface-variant">
                  <div className="col-span-5 flex items-center gap-3 md:col-span-5">
                    <input
                      type="checkbox"
                      checked={allVisibleSelected}
                      onChange={toggleSelectAll}
                      className="h-3.5 w-3.5 shrink-0 accent-primary"
                      title="Tümünü Seç"
                    />
                    <span>Ad</span>
                  </div>
                  <div className="col-span-2 hidden md:block">Tarih</div>
                  <div className="col-span-4 md:col-span-3">Durum</div>
                  <div className="col-span-3 whitespace-nowrap text-right md:col-span-2">Boyut</div>
                </div>

                {visibleDocs.map((d) => {
                  const { icon, className } = fileIcon(d.extension)
                  return (
                    <div
                      key={d.id}
                      className={
                        'group relative grid grid-cols-12 items-center gap-4 border-b border-outline-variant/10 px-5 py-4 transition-colors last:border-0 hover:bg-surface-container-high ' +
                        (d.status === 'pending' || !d.enabled ? 'opacity-70' : '')
                      }
                    >
                      <div className="col-span-5 flex items-center gap-3 md:col-span-5">
                        <input
                          type="checkbox"
                          checked={selectedIds.has(d.id)}
                          onChange={() => toggleSelectOne(d.id)}
                          className="h-3.5 w-3.5 shrink-0 accent-primary"
                        />
                        <div className={'flex h-8 w-8 shrink-0 items-center justify-center rounded ' + className}>
                          <Icon name={icon} className="text-[18px]" />
                        </div>
                        <p className="truncate text-[14px]/[22px] font-medium text-on-surface" title={d.filename}>
                          {d.filename}
                        </p>
                      </div>
                      <div className="col-span-2 hidden text-[14px]/[22px] text-on-surface-variant md:block">
                        {formatRelativeDate(d.created_at)}
                      </div>
                      <div className="col-span-4 flex items-center gap-2 md:col-span-3">
                        <StatusBadge status={d.status} error={d.error} enabled={d.enabled} />
                        <ToggleSwitch checked={d.enabled} onChange={() => handleToggleEnabled(d)} />
                      </div>
                      <div className="col-span-3 whitespace-nowrap pr-6 text-right text-[13px]/[20px] text-on-surface-variant md:col-span-2">
                        {formatBytes(d.size_bytes)}
                      </div>
                      <div className="absolute right-2 top-1/2 -translate-y-1/2">
                        <button
                          className="hidden rounded p-1 text-on-surface-variant hover:text-error group-hover:block"
                          title="Sil"
                          onClick={() => setConfirmDelete({ id: d.id, name: d.filename })}
                        >
                          <Icon name="delete" className="text-[18px]" />
                        </button>
                      </div>
                    </div>
                  )
                })}

                {docs.length === 0 && (
                  <p className="px-5 py-8 text-center text-[14px] text-on-surface-variant/60">
                    Henüz doküman yüklenmedi.
                  </p>
                )}
                {docs.length > 0 && filteredDocs.length === 0 && (
                  <p className="px-5 py-8 text-center text-[14px] text-on-surface-variant/60">
                    Aramanızla eşleşen doküman bulunamadı.
                  </p>
                )}
              </div>

              {filteredDocs.length > INITIAL_VISIBLE && (
                <div className="border-t border-outline-variant/10 bg-surface/30 p-3 text-center">
                  <button
                    className="text-[12px] font-medium text-primary hover:underline"
                    onClick={() => setShowAll((s) => !s)}
                  >
                    {showAll ? 'Daha Az Göster' : `Tüm Dokümanları Gör (${filteredDocs.length})`}
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={confirmDelete !== null}
        title="Dokümanı sil"
        message={`"${confirmDelete?.name}" kalıcı olarak silinecek. Bu işlem geri alınamaz.`}
        onCancel={() => setConfirmDelete(null)}
        onConfirm={async () => {
          if (confirmDelete) await handleDelete(confirmDelete.id)
          setConfirmDelete(null)
        }}
      />
      <ConfirmDialog
        open={confirmBulkDelete}
        title={`${selectedIds.size} dokümanı sil`}
        message={`Seçili ${selectedIds.size} doküman kalıcı olarak silinecek. Bu işlem geri alınamaz.`}
        onCancel={() => setConfirmBulkDelete(false)}
        onConfirm={async () => {
          await handleDeleteSelected()
          setConfirmBulkDelete(false)
        }}
      />
    </main>
  )
}
