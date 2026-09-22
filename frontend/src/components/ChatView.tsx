import { Fragment, useEffect, useRef, useState, type ReactNode } from 'react'
import { getConversation, streamChat, uploadDocument, type Source } from '../lib/api'
import { Icon } from './Icon'

// LLM cevaplarında geçen basit markdown'ı (kalın/italik/kod) JSX'e çevirir —
// tam bir markdown kütüphanesi gerekmiyor, yalnızca bu birkaç işaret görülüyor.
const MARKDOWN_TOKEN_RE = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g

function renderInlineMarkdown(text: string, keyPrefix: string): ReactNode {
  return text.split(MARKDOWN_TOKEN_RE).map((token, i) => {
    const key = `${keyPrefix}-${i}`
    if (token.startsWith('**') && token.endsWith('**')) {
      return <strong key={key}>{token.slice(2, -2)}</strong>
    }
    if (token.startsWith('`') && token.endsWith('`')) {
      return (
        <code key={key} className="rounded bg-surface-container-high px-1 py-0.5 text-[13px]">
          {token.slice(1, -1)}
        </code>
      )
    }
    if (token.startsWith('*') && token.endsWith('*')) {
      return <em key={key}>{token.slice(1, -1)}</em>
    }
    return <Fragment key={key}>{token}</Fragment>
  })
}

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  citations: Source[]
  error?: string
}

// Aynı dokümandan birden çok chunk atıf gösterebilir; kullanıcıya kaynağı
// belge bazında (ilk/en üst sıradaki geçişini koruyarak) tekilleştirip gösteririz.
function uniqueByDocument(sources: Source[]): Source[] {
  const seen = new Set<string>()
  const result: Source[] = []
  for (const s of sources) {
    if (seen.has(s.document_name)) continue
    seen.add(s.document_name)
    result.push(s)
  }
  return result
}

function formatSessionTime(iso: string) {
  return new Date(iso).toLocaleString('tr-TR', {
    day: 'numeric',
    month: 'long',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const NAV_ITEMS: { id: 'chat' | 'documents' | 'admin'; label: string }[] = [
  { id: 'chat', label: 'Sohbet' },
  { id: 'documents', label: 'Dokümanlar' },
  { id: 'admin', label: 'Admin' },
]

interface Props {
  // undefined = henüz backend'de oluşturulmamış "taslak" sohbet (ilk mesajda oluşturulur).
  conversationId: string | undefined
  title: string | null
  onFirstMessage: (conversationId: string, title: string) => void
  ensureConversation: () => Promise<string>
  onNavigate: (tab: 'chat' | 'documents' | 'admin') => void
  onOpenMobileSidebar: () => void
}

export function ChatView({
  conversationId,
  title,
  onFirstMessage,
  ensureConversation,
  onNavigate,
  onOpenMobileSidebar,
}: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  // Taslak (henüz kaydedilmemiş) sohbette gösterilecek başlangıç değeri "şimdi"dir;
  // var olan bir sohbet açıldığında aşağıdaki effect bunu gerçek created_at ile değiştirir.
  const [sessionStarted, setSessionStarted] = useState(() => formatSessionTime(new Date().toISOString()))
  const [attachOpen, setAttachOpen] = useState(false)
  const [dragActive, setDragActive] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadStatus, setUploadStatus] = useState<{ type: 'success' | 'error'; message: string }>()
  const [copiedIndex, setCopiedIndex] = useState<number>()
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const attachRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!attachOpen) return
    function handleClickOutside(e: MouseEvent) {
      if (attachRef.current && !attachRef.current.contains(e.target as Node)) {
        setAttachOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [attachOpen])

  // Yalnızca mount'ta çalışır (ebeveyn, sohbet değişiminde bileşeni `key` ile
  // yeniden mount eder) — taslaktan gerçek id'ye geçişte gereksiz yeniden
  // yüklemeyi ve akış sırasında yarış durumunu önler.
  useEffect(() => {
    if (!conversationId) return
    getConversation(conversationId)
      .then((c) => {
        setMessages(
          c.messages.map((m) => ({ role: m.role, content: m.content, citations: m.citations })),
        )
        setSessionStarted(formatSessionTime(c.created_at))
      })
      // Sohbet başka bir sekmede silinmiş olabilir; boş geçmişle devam etmek
      // kullanıcıyı engellemez, yeni mesaj yazmaya açık kalır.
      .catch(() => setMessages([]))
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function runQuery(query: string, targetIndex: number, isFirst: boolean) {
    setBusy(true)
    const updateAt = (fn: (m: ChatMessage) => ChatMessage) =>
      setMessages((prev) => {
        const next = [...prev]
        next[targetIndex] = fn(next[targetIndex])
        return next
      })

    const id = conversationId ?? (await ensureConversation())
    await streamChat(query, id, {
      onToken: (text) => updateAt((m) => ({ ...m, content: m.content + text })),
      onCitations: (citations) => updateAt((m) => ({ ...m, citations })),
      onError: (message) => updateAt((m) => ({ ...m, error: message })),
    })
    setBusy(false)
    if (isFirst) onFirstMessage(id, query.slice(0, 60))
  }

  async function send() {
    const query = input.trim()
    if (!query || busy) return
    setInput('')
    if (textareaRef.current) textareaRef.current.style.height = '56px'
    const isFirst = messages.length === 0
    const targetIndex = messages.length + 1
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: query, citations: [] },
      { role: 'assistant', content: '', citations: [] },
    ])
    await runQuery(query, targetIndex, isFirst)
  }

  async function retry(index: number) {
    if (busy) return
    const query = messages[index - 1]?.content
    if (!query) return
    setMessages((prev) => {
      const next = [...prev]
      next[index] = { role: 'assistant', content: '', citations: [] }
      return next
    })
    await runQuery(query, index, false)
  }

  async function handleCopy(index: number, content: string) {
    await navigator.clipboard.writeText(content)
    setCopiedIndex(index)
    setTimeout(() => setCopiedIndex((v) => (v === index ? undefined : v)), 1500)
  }

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return
    setUploading(true)
    setUploadStatus(undefined)
    let successCount = 0
    let errorMsg: string | undefined
    for (const file of Array.from(files)) {
      try {
        await uploadDocument(file)
        successCount++
      } catch (e) {
        errorMsg = e instanceof Error ? e.message : 'Yükleme başarısız.'
      }
    }
    setUploading(false)
    if (fileInputRef.current) fileInputRef.current.value = ''
    if (errorMsg) {
      setUploadStatus({ type: 'error', message: errorMsg })
    } else if (successCount > 0) {
      setUploadStatus({
        type: 'success',
        message: successCount === 1 ? 'Doküman yüklendi.' : `${successCount} doküman yüklendi.`,
      })
      setTimeout(() => setAttachOpen(false), 1200)
    }
  }

  return (
    <main className="relative flex h-full w-full flex-1 flex-col">
      {/* Üst bar */}
      <header className="sticky top-0 z-30 flex h-16 w-full items-center justify-between border-b border-outline-variant/5 bg-surface-container-lowest/80 px-4 backdrop-blur-xl sm:px-gutter">
        <div className="flex items-center gap-4">
          <button
            className="flex items-center justify-center p-1 text-on-surface-variant transition-colors hover:text-primary md:hidden"
            onClick={onOpenMobileSidebar}
          >
            <Icon name="menu" />
          </button>
          <h1 className="truncate text-[20px]/[28px] font-semibold tracking-tight text-heading">
            {title ?? 'Yeni Sohbet'}
          </h1>
        </div>
        <nav className="flex items-center gap-1">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              onClick={() => onNavigate(item.id)}
              className={
                'rounded-lg px-3 py-1.5 text-[14px]/[22px] font-medium transition-colors ' +
                (item.id === 'chat'
                  ? 'bg-primary text-on-primary'
                  : 'text-on-surface-variant hover:bg-surface-container-high hover:text-primary')
              }
            >
              {item.label}
            </button>
          ))}
        </nav>
      </header>

      {/* Mesaj akışı */}
      <div className="flex-1 overflow-y-auto p-4 pb-40 sm:px-gutter sm:pt-gutter">
        <div className="mx-auto flex max-w-chat-max-width flex-col gap-6">
          {messages.length === 0 ? (
            <p className="text-[14px]/[22px] text-on-surface-variant">
              Bilgi tabanındaki dokümanlarla ilgili bir soru sorarak başla.
            </p>
          ) : (
            <div className="my-4 flex items-center justify-center">
              <span className="rounded-full border border-outline-variant/10 bg-surface-container-low px-3 py-1 text-[12px]/[16px] tracking-wider text-on-surface-variant">
                {sessionStarted}
              </span>
            </div>
          )}

          {messages.map((m, i) => (
            <div
              key={i}
              className={'group flex w-full flex-col ' + (m.role === 'user' ? 'items-end' : 'items-start')}
            >
              <div
                className={
                  'max-w-[85%] rounded-2xl px-4 py-3 text-[14px]/[22px] ' +
                  (m.role === 'user' ? 'bg-surface-container-high text-heading' : 'text-heading')
                }
              >
                {m.content ? (
                  <p className="whitespace-pre-wrap">{renderInlineMarkdown(m.content, `msg-${i}`)}</p>
                ) : m.role === 'assistant' && busy ? (
                  <span className="flex items-center gap-1 py-1">
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-on-surface-variant [animation-delay:0ms]" />
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-on-surface-variant [animation-delay:150ms]" />
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-on-surface-variant [animation-delay:300ms]" />
                  </span>
                ) : null}
                {m.error && (
                  <div className="mt-1 flex flex-wrap items-center gap-2">
                    <p className="text-[12px] text-error">Hata: {m.error}</p>
                    <button
                      className="flex items-center gap-1 rounded-lg px-2 py-0.5 text-[12px] font-medium text-primary transition-colors hover:bg-primary/10 disabled:opacity-50"
                      onClick={() => retry(i)}
                      disabled={busy}
                      title="Tekrar dene"
                    >
                      <Icon name="refresh" className="text-[14px]" />
                      Tekrar Dene
                    </button>
                  </div>
                )}
              </div>
              {m.role === 'assistant' && m.citations.length > 0 && (
                <div className="mt-2 flex max-w-[85%] flex-col gap-1.5">
                  <p className="text-[11px]/[16px] font-medium uppercase tracking-wider text-on-surface-variant/70">
                    Kaynaklar
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {uniqueByDocument(m.citations).map((c, ci) => (
                      <span
                        key={ci}
                        title={c.snippet}
                        className="inline-flex items-center gap-1 rounded-lg border border-outline-variant/20 bg-surface-container-low px-2 py-1 text-[12px]/[16px] text-on-surface-variant"
                      >
                        <Icon name="description" className="text-[14px] text-primary" />
                        <span className="max-w-[220px] truncate">{c.document_name}</span>
                        {c.page != null && (
                          <span className="text-on-surface-variant/60">· s.{c.page}</span>
                        )}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {m.role === 'assistant' && m.content && (!busy || i !== messages.length - 1) && (
                <button
                  className="mt-1 flex items-center gap-1 rounded-lg px-2 py-1 text-[12px] text-on-surface-variant opacity-0 transition-opacity hover:text-on-surface group-hover:opacity-100"
                  onClick={() => handleCopy(i, m.content)}
                  title="Kopyala"
                >
                  <Icon name={copiedIndex === i ? 'check' : 'content_copy'} className="text-[14px]" />
                  {copiedIndex === i ? 'Kopyalandı' : 'Kopyala'}
                </button>
              )}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Giriş alanı */}
      <div className="absolute bottom-0 left-0 w-full border-t border-outline-variant/10 bg-surface-container-lowest/80 px-4 pb-6 pt-4 backdrop-blur-xl sm:px-gutter">
        <div className="mx-auto max-w-chat-max-width">
          <div className="relative rounded-2xl border border-outline-variant/30 bg-surface-container-low shadow-lg transition-all focus-within:border-primary-container/50 focus-within:ring-1 focus-within:ring-primary-container/50">
            <textarea
              ref={textareaRef}
              className="max-h-[200px] min-h-[56px] w-full resize-none rounded-t-2xl border-none bg-transparent px-4 pb-2 pt-4 text-[16px]/[26px] text-on-surface placeholder:text-on-surface-variant/50 focus:ring-0"
              placeholder="Bir soru sor…"
              rows={1}
              value={input}
              disabled={busy}
              onChange={(e) => {
                setInput(e.target.value)
                e.target.style.height = ''
                e.target.style.height = Math.min(e.target.scrollHeight, 200) + 'px'
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  send()
                }
              }}
            />
            <div className="flex items-center justify-between px-3 pb-3 pt-1">
              <div className="relative" ref={attachRef}>
                <button
                  className="flex items-center justify-center rounded-full p-2 text-on-surface-variant transition-colors hover:bg-surface-container-high hover:text-on-surface"
                  title="Doküman yükle"
                  onClick={() =>
                    setAttachOpen((o) => {
                      if (!o) setUploadStatus(undefined)
                      return !o
                    })
                  }
                >
                  <Icon name="attach_file" className="text-[20px]" />
                </button>
                {attachOpen && (
                  <div
                    className={
                      'absolute bottom-full left-0 z-20 mb-2 w-72 rounded-xl border p-4 shadow-lg transition-colors ' +
                      (dragActive
                        ? 'border-primary/70 bg-surface-container'
                        : 'border-outline-variant/20 bg-surface-container-high')
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
                    <div className="mb-3 flex items-center justify-between">
                      <p className="text-[13px]/[18px] font-medium text-on-surface">Doküman Ekle</p>
                      <button
                        className="text-on-surface-variant transition-colors hover:text-on-surface"
                        onClick={() => setAttachOpen(false)}
                      >
                        <Icon name="close" className="text-[16px]" />
                      </button>
                    </div>
                    <div className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-outline-variant/30 p-4 text-center">
                      <Icon name="cloud_upload" className="mb-2 text-2xl text-primary" />
                      <p className="mb-3 text-[12px]/[18px] text-on-surface-variant">
                        Sürükle bırak veya dosya seç
                      </p>
                      <button
                        className="rounded-lg bg-primary px-3 py-1.5 text-[12px]/[16px] font-medium text-on-primary transition-colors hover:bg-primary-fixed disabled:opacity-50"
                        onClick={() => fileInputRef.current?.click()}
                        disabled={uploading}
                      >
                        {uploading ? 'Yükleniyor…' : 'Dosya Seç'}
                      </button>
                      <input
                        ref={fileInputRef}
                        type="file"
                        multiple
                        accept=".pdf,.docx,.xlsx,.txt,.md"
                        className="hidden"
                        onChange={(e) => handleFiles(e.target.files)}
                      />
                    </div>
                    {uploadStatus && (
                      <p
                        className={
                          'mt-2 text-[12px]/[16px] ' +
                          (uploadStatus.type === 'success' ? 'text-emerald-400' : 'text-error')
                        }
                      >
                        {uploadStatus.message}
                      </p>
                    )}
                  </div>
                )}
              </div>
              <button
                className="flex items-center justify-center rounded-xl bg-primary p-2 text-on-primary shadow-sm transition-colors hover:bg-primary-fixed disabled:bg-surface-container-highest disabled:text-on-surface-variant disabled:opacity-50"
                onClick={send}
                disabled={busy || !input.trim()}
              >
                <Icon name="send" className="text-[20px]" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </main>
  )
}
