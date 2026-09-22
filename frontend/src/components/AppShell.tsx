import { useEffect, useState } from 'react'
import {
  createConversation,
  createProject,
  deleteConversation,
  deleteProject,
  listConversations,
  listProjects,
  renameConversation,
  renameProject,
  setConversationPinned,
  setConversationProject,
  ApiError,
  type ConversationSummary,
  type Project,
} from '../lib/api'
import { ConversationSidebar } from './ConversationSidebar'
import { ChatView } from './ChatView'
import { DocumentsView } from './DocumentsView'
import { AdminView } from './AdminView'

const STORAGE_KEY = 'rag_conversation_id'

export type Tab = 'chat' | 'documents' | 'admin'

interface Props {
  tab: Tab
  onNavigate: (tab: Tab) => void
}

// Sol kenar çubuğu (sohbet listesi) tüm sayfalarda ortak — bu yüzden onu ve
// konuşma state'ini burada, tüm sekmelerin üstünde tek bir yerde tutuyoruz.
export function AppShell({ tab, onNavigate }: Props) {
  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  // undefined = henüz kaydedilmemiş taslak sohbet (backend'de karşılığı yok).
  const [activeId, setActiveId] = useState<string>()
  const [sessionKey, setSessionKey] = useState(0)
  // ChatView, mount anındaki conversationId'yi bir kere okuyup geçmişi öyle yükler
  // (bkz. ChatView.tsx) — bu yüzden ilk liste isteği bitmeden onu hiç render etmiyoruz,
  // yoksa "henüz undefined" haliyle mount olup gerçek id'yi asla göremez.
  const [loading, setLoading] = useState(true)
  const [startupError, setStartupError] = useState<unknown>()
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)

  useEffect(() => {
    listConversations()
      .then(({ items }) => {
        setConversations(items)
        const stored = localStorage.getItem(STORAGE_KEY)
        if (stored && items.some((c) => c.id === stored)) {
          setActiveId(stored)
        } else if (items.length > 0) {
          localStorage.setItem(STORAGE_KEY, items[0].id)
          setActiveId(items[0].id)
        }
      })
      // Hata yutulursa `loading` hiç kapanmaz ve kullanıcı boş ekranda kalır;
      // bu yüzden sebebini gösterip yüklemeyi her hâlükârda sonlandırıyoruz.
      .catch(setStartupError)
      .finally(() => setLoading(false))
    listProjects()
      .then(({ items }) => setProjects(items))
      .catch(setStartupError)
  }, [])

  function handleNew() {
    localStorage.removeItem(STORAGE_KEY)
    setActiveId(undefined)
    setSessionKey((k) => k + 1)
    setMobileOpen(false)
    onNavigate('chat')
  }

  function handleSelect(id: string) {
    setMobileOpen(false)
    onNavigate('chat')
    if (id === activeId) return
    localStorage.setItem(STORAGE_KEY, id)
    setActiveId(id)
    setSessionKey((k) => k + 1)
  }

  // Taslak sohbette ilk mesaj gönderilirken çağrılır — sohbeti o an oluşturur.
  // sessionKey'e DOKUNMAZ, aksi halde akış ortasında ChatView yeniden mount olurdu.
  async function ensureConversation(): Promise<string> {
    const c = await createConversation()
    localStorage.setItem(STORAGE_KEY, c.id)
    setConversations((prev) => [c, ...prev])
    setActiveId(c.id)
    return c.id
  }

  async function handleDelete(id: string) {
    await deleteConversation(id)
    const remaining = conversations.filter((c) => c.id !== id)
    setConversations(remaining)
    if (id === activeId) {
      if (remaining.length > 0) handleSelect(remaining[0].id)
      else handleNew()
    }
  }

  async function handleFirstMessage(id: string, title: string) {
    const updated = await renameConversation(id, title)
    setConversations((prev) => prev.map((c) => (c.id === id ? updated : c)))
  }

  async function handleRename(id: string, title: string) {
    const updated = await renameConversation(id, title)
    setConversations((prev) => prev.map((c) => (c.id === id ? updated : c)))
  }

  async function handleTogglePin(id: string, pinned: boolean) {
    const updated = await setConversationPinned(id, pinned)
    setConversations((prev) => prev.map((c) => (c.id === id ? updated : c)))
  }

  async function handleMoveToProject(id: string, projectId: string | null) {
    const updated = await setConversationProject(id, projectId)
    setConversations((prev) => prev.map((c) => (c.id === id ? updated : c)))
  }

  async function handleCreateProject(name: string): Promise<Project> {
    const project = await createProject(name)
    setProjects((prev) => [...prev, project])
    return project
  }

  async function handleRenameProject(id: string, name: string) {
    const updated = await renameProject(id, name)
    setProjects((prev) => prev.map((p) => (p.id === id ? updated : p)))
  }

  async function handleDeleteProject(id: string) {
    await deleteProject(id)
    setProjects((prev) => prev.filter((p) => p.id !== id))
    setConversations((prev) =>
      prev.map((c) => (c.project_id === id ? { ...c, project_id: null } : c)),
    )
  }

  const active = conversations.find((c) => c.id === activeId)
  const openMobileSidebar = () => setMobileOpen(true)

  if (startupError) {
    return <StartupError error={startupError} />
  }

  return (
    <div className="flex h-screen w-screen bg-surface-container-lowest text-on-surface">
      <ConversationSidebar
        conversations={conversations}
        projects={projects}
        activeId={activeId}
        onSelect={handleSelect}
        onNew={handleNew}
        onDelete={handleDelete}
        onRename={handleRename}
        onTogglePin={handleTogglePin}
        onMoveToProject={handleMoveToProject}
        onCreateProject={handleCreateProject}
        onRenameProject={handleRenameProject}
        onDeleteProject={handleDeleteProject}
        collapsed={collapsed}
        onToggleCollapse={() => setCollapsed((c) => !c)}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
      />
      <div
        className={
          'flex h-full flex-1 flex-col overflow-hidden ' +
          (collapsed ? 'md:ml-sidebar-collapsed' : 'md:ml-sidebar-width')
        }
      >
        {/* ChatView, sekme değişince unmount OLMAZ (yalnızca CSS ile gizlenir) — aksi halde
            akan bir cevap Admin/Dokümanlar'a geçilince arka planda tamamlansa bile ekranda
            "kesilmiş" gibi görünür (bkz. ChatView.tsx'teki sessionKey/mount açıklaması). */}
        {!loading && (
          <div className={'h-full min-h-0 flex-1 flex-col ' + (tab === 'chat' ? 'flex' : 'hidden')}>
            <ChatView
              key={sessionKey}
              conversationId={activeId}
              title={active?.title ?? null}
              onFirstMessage={handleFirstMessage}
              ensureConversation={ensureConversation}
              onNavigate={onNavigate}
              onOpenMobileSidebar={openMobileSidebar}
            />
          </div>
        )}
        {tab === 'documents' && (
          <DocumentsView onNavigate={onNavigate} onOpenMobileSidebar={openMobileSidebar} />
        )}
        {tab === 'admin' && <AdminView onNavigate={onNavigate} onOpenMobileSidebar={openMobileSidebar} />}
      </div>
    </div>
  )
}

// Uygulama backend'e hiç ulaşamadığında sessizce boş ekran göstermek yerine
// sebebi ve çözümü anlatır; en sık sebep VITE_API_KEY'in backend'deki API_KEY
// ile eşleşmemesidir.
function StartupError({ error }: { error: unknown }) {
  const authFailed = error instanceof ApiError && error.isAuthError
  return (
    <div className="flex h-screen w-screen items-center justify-center bg-surface-container-lowest p-6 text-on-surface">
      <div className="max-w-md rounded-xl bg-surface-container p-6">
        <h1 className="mb-2 text-lg font-semibold">
          {authFailed ? 'API anahtarı geçersiz' : 'Backend’e ulaşılamıyor'}
        </h1>
        <p className="text-sm text-on-surface-variant">
          {authFailed ? (
            <>
              Frontend’deki <code>VITE_API_KEY</code> değeri backend’deki{' '}
              <code>API_KEY</code> ile aynı olmalı. <code>frontend/.env</code> ve{' '}
              <code>backend/.env</code> dosyalarını karşılaştırıp uygulamayı yeniden başlatın.
            </>
          ) : (
            <>
              Backend çalışıyor mu ve <code>VITE_API_BASE_URL</code> doğru mu kontrol edin.
            </>
          )}
        </p>
        <p className="mt-3 break-words text-xs text-on-surface-variant opacity-70">
          {error instanceof Error ? error.message : String(error)}
        </p>
      </div>
    </div>
  )
}
