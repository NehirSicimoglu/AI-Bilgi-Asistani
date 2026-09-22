import { Icon } from './Icon'
import type { ThemeChoice } from '../lib/theme'

interface Props {
  open: boolean
  onClose: () => void
  theme: ThemeChoice
  onThemeChange: (t: ThemeChoice) => void
}

export function SettingsModal({ open, onClose, theme, onThemeChange }: Props) {
  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm rounded-2xl border border-outline-variant/10 bg-surface-container-high p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-[16px]/[24px] font-semibold text-on-surface">Ayarlar</h2>
          <button className="text-on-surface-variant hover:text-primary" onClick={onClose}>
            <Icon name="close" />
          </button>
        </div>

        <p className="mt-5 text-[12px]/[16px] font-medium uppercase tracking-wider text-on-surface-variant">
          Görünüm
        </p>
        <div className="mt-2 grid grid-cols-2 gap-2">
          <button
            onClick={() => onThemeChange('dark')}
            className={
              'flex flex-col items-center gap-1.5 rounded-lg border px-3 py-3 text-[14px]/[22px] transition-colors ' +
              (theme === 'dark'
                ? 'border-primary bg-surface-container text-primary'
                : 'border-outline-variant/20 text-on-surface-variant hover:bg-surface-container')
            }
          >
            <Icon name="dark_mode" />
            Koyu
          </button>
          <button
            onClick={() => onThemeChange('light')}
            className={
              'flex flex-col items-center gap-1.5 rounded-lg border px-3 py-3 text-[14px]/[22px] transition-colors ' +
              (theme === 'light'
                ? 'border-primary bg-surface-container text-primary'
                : 'border-outline-variant/20 text-on-surface-variant hover:bg-surface-container')
            }
          >
            <Icon name="light_mode" />
            Açık
          </button>
        </div>
      </div>
    </div>
  )
}
