const THEME_KEY = 'rag_theme'

export type ThemeChoice = 'dark' | 'light'

export function getStoredTheme(): ThemeChoice {
  return localStorage.getItem(THEME_KEY) === 'light' ? 'light' : 'dark'
}

export function setStoredTheme(theme: ThemeChoice): void {
  localStorage.setItem(THEME_KEY, theme)
}

export function applyTheme(theme: ThemeChoice): void {
  document.documentElement.setAttribute('data-theme', theme)
}
