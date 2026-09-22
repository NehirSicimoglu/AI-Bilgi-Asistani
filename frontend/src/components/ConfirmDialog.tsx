import { Icon } from './Icon'

interface Props {
  open: boolean
  title: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Sil',
  cancelLabel = 'Vazgeç',
  onConfirm,
  onCancel,
}: Props) {
  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4"
      onClick={onCancel}
    >
      <div
        className="w-full max-w-sm rounded-2xl border border-outline-variant/10 bg-surface-container-high p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-error/10 text-error">
            <Icon name="warning" className="text-[20px]" />
          </div>
          <div className="min-w-0 flex-1">
            <h2 className="break-words text-[16px]/[24px] font-semibold text-on-surface">{title}</h2>
            <p className="mt-1 break-words text-[13px]/[20px] text-on-surface-variant">{message}</p>
          </div>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button
            className="rounded-lg px-4 py-2 text-[13px]/[20px] font-medium text-on-surface-variant transition-colors hover:bg-surface-container"
            onClick={onCancel}
          >
            {cancelLabel}
          </button>
          <button
            className="rounded-lg bg-error px-4 py-2 text-[13px]/[20px] font-medium text-on-error transition-colors hover:opacity-90"
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
