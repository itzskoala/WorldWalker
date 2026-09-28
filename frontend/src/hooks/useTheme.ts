// Port of web/static/js/app.js's theme toggle. index.html's own inline
// <head> script (see frontend/index.html) sets data-theme before first
// paint from the same "ww-theme" localStorage key, so there's no flash;
// this hook just reads that starting value and persists changes.

import { useCallback, useState } from 'react'

export type Theme = 'light' | 'dark'
const STORAGE_KEY = 'ww-theme'

function currentTheme(): Theme {
  return document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark'
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(currentTheme)

  const toggleTheme = useCallback(() => {
    const next: Theme = theme === 'light' ? 'dark' : 'light'
    document.documentElement.setAttribute('data-theme', next)
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // Private browsing / storage disabled - theme just won't persist.
    }
    setTheme(next)
  }, [theme])

  return { theme, toggleTheme }
}
