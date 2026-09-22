import { useEffect, useRef, useState } from 'react'
import type { ConversationSummary, Project } from '../lib/api'
import { ConfirmDialog } from './ConfirmDialog'
import { Icon } from './Icon'
import { SettingsModal } from './SettingsModal'
import { applyTheme, getStoredTheme, setStoredTheme, type ThemeChoice } from '../lib/theme'

interface Props {
  conversations: ConversationSummary[]
  projects: Project[]
  activeId: string | undefined
  onSelect: (id: string) => void
  onNew: () => void
  onDelete: (id: string) => void
  onRename: (id: string, title: string) => void
  onTogglePin: (id: string, pinned: boolean) => void
  onMoveToProject: (id: string, projectId: string | null) => void
  onCreateProject: (name: string) => Promise<Project>
  onRenameProject: (id: string, name: string) => void
  onDeleteProject: (id: string) => void
  collapsed: boolean
  onToggleCollapse: () => void
  mobileOpen: boolean
  onCloseMobile: () => void
}

export function ConversationSidebar({
  conversations,
  projects,
  activeId,
  onSelect,
  onNew,
  onDelete,
  onRename,
  onTogglePin,
  onMoveToProject,
  onCreateProject,
  onRenameProject,
  onDeleteProject,
  collapsed,
  onToggleCollapse,
  mobileOpen,
  onCloseMobile,
}: Props) {
  const [search, setSearch] = useState('')
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [theme, setTheme] = useState<ThemeChoice>(getStoredTheme)
  const [menuOpenId, setMenuOpenId] = useState<string>()
  const [renamingId, setRenamingId] = useState<string>()
  const [renameValue, setRenameValue] = useState('')
  const [confirmDelete, setConfirmDelete] = useState<ConversationSummary>()
  const [confirmDeleteProject, setConfirmDeleteProject] = useState<Project>()
  const [renamingProjectId, setRenamingProjectId] = useState<string>()
  const [renameProjectValue, setRenameProjectValue] = useState('')
  const [movePickerId, setMovePickerId] = useState<string>()
  const [creatingProject, setCreatingProject] = useState(false)
  const [newProjectName, setNewProjectName] = useState('')
  const [creatingSidebarProject, setCreatingSidebarProject] = useState(false)
  const [newSidebarProjectName, setNewSidebarProjectName] = useState('')
  const [expandedProjectIds, setExpandedProjectIds] = useState<Set<string>>(new Set())
  const [recentsExpanded, setRecentsExpanded] = useState(true)
  const [projectsSectionExpanded, setProjectsSectionExpanded] = useState(true)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  useEffect(() => {
    if (!menuOpenId) return
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        closeMenu()
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [menuOpenId])

  function closeMenu() {
    setMenuOpenId(undefined)
    setMovePickerId(undefined)
    setCreatingProject(false)
    setNewProjectName('')
  }

  function startRename(c: ConversationSummary) {
    closeMenu()
    setRenamingId(c.id)
    setRenameValue(c.title ?? 'Yeni Sohbet')
  }

  function commitRename(id: string) {
    const trimmed = renameValue.trim()
    setRenamingId(undefined)
    if (trimmed) onRename(id, trimmed)
  }

  function startRenameProject(p: Project) {
    setRenamingProjectId(p.id)
    setRenameProjectValue(p.name)
  }

  function commitRenameProject(id: string) {
    const trimmed = renameProjectValue.trim()
    setRenamingProjectId(undefined)
    if (trimmed) onRenameProject(id, trimmed)
  }

  async function commitNewProject(conversationId: string) {
    const trimmed = newProjectName.trim()
    if (!trimmed) {
      setCreatingProject(false)
      return
    }
    const project = await onCreateProject(trimmed)
    onMoveToProject(conversationId, project.id)
    closeMenu()
  }

  async function commitSidebarNewProject() {
    const trimmed = newSidebarProjectName.trim()
    setCreatingSidebarProject(false)
    setNewSidebarProjectName('')
    if (!trimmed) return
    const project = await onCreateProject(trimmed)
    setExpandedProjectIds((prev) => new Set(prev).add(project.id))
  }

  function toggleProjectExpanded(projectId: string) {
    setExpandedProjectIds((prev) => {
      const next = new Set(prev)
      if (next.has(projectId)) next.delete(projectId)
      else next.add(projectId)
      return next
    })
  }

  const filtered = conversations.filter((c) =>
    (c.title ?? 'Yeni Sohbet').toLowerCase().includes(search.toLowerCase()),
  )
  // Sabitlenenler tüm sabitli sohbetleri kapsar (projeli olsa bile) — projedeki
  // bir sohbet sabitlenince hem kendi projesinde hem burada (kopya) görünür.
  const pinnedList = filtered.filter((c) => c.pinned)
  const unassignedList = filtered.filter((c) => !c.pinned && !c.project_id)
  const conversationsForProject = (projectId: string) =>
    filtered.filter((c) => c.project_id === projectId)

  function renderRow(c: ConversationSummary) {
    const active = c.id === activeId
    const isRenaming = renamingId === c.id
    const isMenuOpen = menuOpenId === c.id
    return (
      <div
        key={c.id}
        className={
          'group relative flex cursor-pointer items-center gap-3 border-l-2 px-4 py-2 transition-colors duration-200 ' +
          (active
            ? 'border-primary bg-surface-container text-primary'
            : 'border-transparent text-on-surface-variant hover:bg-surface-container-high')
        }
        onClick={() => !isRenaming && onSelect(c.id)}
        title={c.title ?? 'Yeni Sohbet'}
      >
        {collapsed && (
          <Icon name={c.pinned ? 'push_pin' : 'chat_bubble'} filled={active || c.pinned} className="shrink-0" />
        )}
        {!collapsed && (
          <>
            {isRenaming ? (
              <input
                autoFocus
                value={renameValue}
                onChange={(e) => setRenameValue(e.target.value)}
                onClick={(e) => e.stopPropagation()}
                onBlur={() => commitRename(c.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') commitRename(c.id)
                  if (e.key === 'Escape') setRenamingId(undefined)
                }}
                className="flex-1 truncate rounded border border-primary/50 bg-surface-container px-1 py-0.5 text-[14px]/[22px] text-on-surface outline-none"
              />
            ) : (
              <span className="flex-1 truncate text-[14px]/[22px] group-hover:text-on-surface">
                {c.title ?? 'Yeni Sohbet'}
              </span>
            )}
            <button
              className={
                'shrink-0 text-on-surface-variant hover:text-primary ' +
                (c.pinned ? 'block' : 'hidden group-hover:block')
              }
              onClick={(e) => {
                e.stopPropagation()
                onTogglePin(c.id, !c.pinned)
              }}
              title={c.pinned ? 'Sabit Kaldır' : 'Sabitle'}
            >
              <Icon name={c.pinned ? 'keep_off' : 'push_pin'} className="text-[16px]" />
            </button>
            <div className="relative shrink-0">
              <button
                className={
                  'shrink-0 text-on-surface-variant hover:text-on-surface ' +
                  (isMenuOpen ? 'block' : 'hidden group-hover:block')
                }
                onClick={(e) => {
                  e.stopPropagation()
                  if (isMenuOpen) closeMenu()
                  else setMenuOpenId(c.id)
                }}
                title="Seçenekler"
              >
                <Icon name="more_vert" className="text-[18px]" />
              </button>
              {isMenuOpen && (
                <div
                  ref={menuRef}
                  className="absolute right-0 top-full z-50 mt-1 w-48 overflow-hidden rounded-lg border border-outline-variant/20 bg-surface-container-high shadow-lg"
                  onClick={(e) => e.stopPropagation()}
                >
                  {movePickerId === c.id ? (
                    <>
                      <button
                        className="flex w-full items-center gap-2 border-b border-outline-variant/10 px-3 py-2 text-left text-[12px]/[16px] text-on-surface-variant hover:bg-surface-container-highest"
                        onClick={() => setMovePickerId(undefined)}
                      >
                        <Icon name="arrow_back" className="text-[16px]" />
                        Geri
                      </button>
                      <div className="max-h-48 overflow-y-auto">
                        {c.project_id && (
                          <button
                            className="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px]/[20px] text-on-surface hover:bg-surface-container-highest"
                            onClick={() => {
                              onMoveToProject(c.id, null)
                              closeMenu()
                            }}
                          >
                            <Icon name="chat_bubble" className="text-[16px]" />
                            Projesiz
                          </button>
                        )}
                        {projects.map((p) => (
                          <button
                            key={p.id}
                            className="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px]/[20px] text-on-surface hover:bg-surface-container-highest"
                            onClick={() => {
                              onMoveToProject(c.id, p.id)
                              closeMenu()
                            }}
                          >
                            <Icon name="folder" className="text-[16px]" />
                            <span className="truncate">{p.name}</span>
                            {c.project_id === p.id && (
                              <Icon name="check" className="ml-auto shrink-0 text-[16px]" />
                            )}
                          </button>
                        ))}
                      </div>
                      <div className="border-t border-outline-variant/10 p-2">
                        {creatingProject ? (
                          <input
                            autoFocus
                            value={newProjectName}
                            onChange={(e) => setNewProjectName(e.target.value)}
                            onBlur={() => commitNewProject(c.id)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') commitNewProject(c.id)
                              if (e.key === 'Escape') setCreatingProject(false)
                            }}
                            placeholder="Proje adı…"
                            className="w-full rounded border border-primary/50 bg-surface-container px-2 py-1 text-[13px]/[20px] text-on-surface outline-none"
                          />
                        ) : (
                          <button
                            className="flex w-full items-center gap-2 rounded px-1 py-1 text-left text-[13px]/[20px] text-primary hover:bg-surface-container-highest"
                            onClick={() => setCreatingProject(true)}
                          >
                            <Icon name="add" className="text-[16px]" />
                            Yeni Proje
                          </button>
                        )}
                      </div>
                    </>
                  ) : (
                    <>
                      <button
                        className="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px]/[20px] text-on-surface hover:bg-surface-container-highest"
                        onClick={() => setMovePickerId(c.id)}
                      >
                        <Icon name="drive_file_move" className="text-[16px]" />
                        Taşı
                      </button>
                      <button
                        className="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px]/[20px] text-on-surface hover:bg-surface-container-highest"
                        onClick={() => startRename(c)}
                      >
                        <Icon name="edit" className="text-[16px]" />
                        Yeniden Adlandır
                      </button>
                      <button
                        className="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px]/[20px] text-error hover:bg-surface-container-highest"
                        onClick={() => {
                          closeMenu()
                          setConfirmDelete(c)
                        }}
                      >
                        <Icon name="delete" className="text-[16px]" />
                        Sil
                      </button>
                    </>
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    )
  }

  return (
    <>
      {mobileOpen && (
        <div className="fixed inset-0 z-40 bg-black/50 md:hidden" onClick={onCloseMobile} />
      )}
      <aside
        className={
          'fixed left-0 top-0 z-50 flex h-full flex-col border-r border-outline-variant/10 bg-surface-container-high transition-all duration-200 ' +
          (collapsed ? 'w-sidebar-collapsed' : 'w-sidebar-width') +
          ' ' +
          (mobileOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0')
        }
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-outline-variant/10 p-4">
          {!collapsed && (
            <h1 className="truncate text-[16px]/[24px] font-semibold text-heading">AI Bilgi Asistanı</h1>
          )}
          <button
            className="p-1 text-on-surface-variant transition-colors hover:text-primary md:hidden"
            onClick={onCloseMobile}
          >
            <Icon name="close" />
          </button>
          <button
            className="hidden p-1 text-on-surface-variant transition-colors hover:text-primary md:block"
            onClick={onToggleCollapse}
            title={collapsed ? 'Genişlet' : 'Daralt'}
          >
            <Icon name={collapsed ? 'menu' : 'menu_open'} />
          </button>
        </div>

        {/* Yeni sohbet */}
        <div className="p-4">
          <button
            onClick={onNew}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-[14px]/[22px] font-medium text-on-primary shadow-sm transition-colors hover:bg-primary-fixed"
          >
            <Icon name="add" />
            {!collapsed && <span>Yeni Sohbet</span>}
          </button>
        </div>

        {!collapsed && (
          <div className="px-4 pb-2">
            <div className="relative flex items-center">
              <Icon name="search" className="absolute left-3 z-10 text-primary" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Sohbetlerde ara…"
                className="w-full rounded-lg border border-outline-variant/20 bg-surface-container py-2 pl-10 pr-4 text-[14px]/[22px] text-on-surface outline-none transition-colors placeholder:text-on-surface-variant/50 focus:border-primary/50"
              />
            </div>
          </div>
        )}

        {/* Sohbet listesi */}
        <div className="flex-1 overflow-y-auto py-2">
          {pinnedList.length > 0 && (
            <>
              {!collapsed && (
                <div className="px-4 pb-2">
                  <span className="text-[12px]/[16px] font-medium uppercase tracking-wider text-on-surface-variant">
                    Sabitlenenler
                  </span>
                </div>
              )}
              <nav className="mb-2 flex flex-col gap-1">{pinnedList.map(renderRow)}</nav>
            </>
          )}

          {!collapsed && (
            <div
              className="flex cursor-pointer items-center justify-between px-4 pb-2"
              onClick={() => setProjectsSectionExpanded((v) => !v)}
            >
              <span className="flex items-center gap-1.5 text-[12px]/[16px] font-medium uppercase tracking-wider text-on-surface-variant">
                <Icon
                  name={projectsSectionExpanded ? 'expand_more' : 'chevron_right'}
                  className="shrink-0 text-[16px] normal-case"
                />
                Projeler
              </span>
              <button
                className="text-on-surface-variant hover:text-primary"
                onClick={(e) => {
                  e.stopPropagation()
                  setProjectsSectionExpanded(true)
                  setCreatingSidebarProject(true)
                }}
                title="Yeni Proje"
              >
                <Icon name="add" className="text-[16px]" />
              </button>
            </div>
          )}
          {projectsSectionExpanded && creatingSidebarProject && !collapsed && (
            <div className="px-4 pb-2">
              <input
                autoFocus
                value={newSidebarProjectName}
                onChange={(e) => setNewSidebarProjectName(e.target.value)}
                onBlur={commitSidebarNewProject}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') commitSidebarNewProject()
                  if (e.key === 'Escape') {
                    setCreatingSidebarProject(false)
                    setNewSidebarProjectName('')
                  }
                }}
                placeholder="Proje adı…"
                className="w-full rounded-lg border border-primary/50 bg-surface-container px-2 py-1.5 text-[13px]/[20px] text-on-surface outline-none"
              />
            </div>
          )}
          {projectsSectionExpanded && projects.length === 0 && !collapsed && !creatingSidebarProject && (
            <p className="px-4 pb-2 text-[12px] text-on-surface-variant/50">Henüz proje yok.</p>
          )}
          {projectsSectionExpanded && projects.map((p) => {
            const list = conversationsForProject(p.id)
            const expanded = expandedProjectIds.has(p.id)
            return (
              <div key={p.id} className="mb-1">
                {!collapsed && renamingProjectId === p.id ? (
                  <div className="px-4 py-1" onClick={(e) => e.stopPropagation()}>
                    <input
                      autoFocus
                      value={renameProjectValue}
                      onChange={(e) => setRenameProjectValue(e.target.value)}
                      onBlur={() => commitRenameProject(p.id)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') commitRenameProject(p.id)
                        if (e.key === 'Escape') setRenamingProjectId(undefined)
                      }}
                      className="w-full rounded-lg border border-primary/50 bg-surface-container px-2 py-1 text-[13px]/[20px] text-on-surface outline-none"
                    />
                  </div>
                ) : (
                  !collapsed && (
                    <div
                      className="group flex cursor-pointer items-center justify-between px-4 py-1.5 hover:bg-surface-container-high"
                      onClick={() => toggleProjectExpanded(p.id)}
                    >
                      <span className="flex min-w-0 items-center gap-1.5 text-[13px]/[20px] font-medium text-on-surface-variant">
                        <Icon
                          name={expanded ? 'expand_more' : 'chevron_right'}
                          className="shrink-0 text-[16px]"
                        />
                        <Icon name="folder" className="shrink-0 text-[16px]" />
                        <span className="truncate">{p.name}</span>
                        <span className="shrink-0 text-[11px] text-on-surface-variant/50">
                          {list.length > 0 ? list.length : ''}
                        </span>
                      </span>
                      <span className="hidden shrink-0 items-center gap-1 group-hover:flex">
                        <button
                          className="text-on-surface-variant hover:text-primary"
                          onClick={(e) => {
                            e.stopPropagation()
                            startRenameProject(p)
                          }}
                          title="Adını değiştir"
                        >
                          <Icon name="edit" className="text-[14px]" />
                        </button>
                        <button
                          className="text-on-surface-variant hover:text-error"
                          onClick={(e) => {
                            e.stopPropagation()
                            setConfirmDeleteProject(p)
                          }}
                          title="Projeyi sil"
                        >
                          <Icon name="delete" className="text-[14px]" />
                        </button>
                      </span>
                    </div>
                  )
                )}
                {expanded && (
                  <nav className="flex flex-col gap-1">
                    {list.map(renderRow)}
                    {list.length === 0 && !collapsed && (
                      <p className="px-4 pb-1 text-[12px] text-on-surface-variant/50">
                        Bu projede sohbet yok.
                      </p>
                    )}
                  </nav>
                )}
              </div>
            )
          })}

          {!collapsed && (
            <div
              className="flex cursor-pointer items-center gap-1.5 px-4 pb-2"
              onClick={() => setRecentsExpanded((v) => !v)}
            >
              <Icon
                name={recentsExpanded ? 'expand_more' : 'chevron_right'}
                className="shrink-0 text-[16px] text-on-surface-variant"
              />
              <span className="text-[12px]/[16px] font-medium uppercase tracking-wider text-on-surface-variant">
                Son Sohbetler
              </span>
            </div>
          )}
          {(recentsExpanded || collapsed) && (
            <nav className="flex flex-col gap-1">
              {unassignedList.map(renderRow)}
              {filtered.length === 0 && !collapsed && (
                <p className="px-4 py-2 text-[12px] text-on-surface-variant/60">Sohbet bulunamadı.</p>
              )}
            </nav>
          )}
        </div>

        {/* Ayarlar */}
        <div className="border-t border-outline-variant/10 p-4">
          <button
            onClick={() => setSettingsOpen(true)}
            className="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-on-surface-variant transition-colors hover:bg-surface-container-high hover:text-on-surface"
          >
            <Icon name="settings" className="shrink-0" />
            {!collapsed && <span className="text-[14px]/[22px]">Ayarlar</span>}
          </button>
        </div>
      </aside>

      <SettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        theme={theme}
        onThemeChange={(t) => {
          setTheme(t)
          setStoredTheme(t)
        }}
      />

      <ConfirmDialog
        open={confirmDelete !== undefined}
        title="Sohbeti sil"
        message={`"${confirmDelete?.title ?? 'Yeni Sohbet'}" kalıcı olarak silinecek. Bu işlem geri alınamaz.`}
        onCancel={() => setConfirmDelete(undefined)}
        onConfirm={() => {
          if (confirmDelete) onDelete(confirmDelete.id)
          setConfirmDelete(undefined)
        }}
      />

      <ConfirmDialog
        open={confirmDeleteProject !== undefined}
        title="Projeyi sil"
        message={`"${confirmDeleteProject?.name}" silinecek. İçindeki sohbetler silinmez, yalnızca projeden çıkarılır.`}
        onCancel={() => setConfirmDeleteProject(undefined)}
        onConfirm={() => {
          if (confirmDeleteProject) onDeleteProject(confirmDeleteProject.id)
          setConfirmDeleteProject(undefined)
        }}
      />
    </>
  )
}
