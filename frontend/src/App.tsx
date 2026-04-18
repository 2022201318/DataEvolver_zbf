import { useEffect } from 'react'
import { MainLayout } from './layouts/MainLayout'
import { Toast } from './components/Toast'
import { useAppStore } from './stores/appStore'

export default function App() {
  const toast = useAppStore((s) => s.toast)
  const setToast = useAppStore((s) => s.setToast)
  const themeMode = useAppStore((s) => s.themeMode)

  useEffect(() => {
    const root = document.documentElement
    root.classList.remove('theme-light', 'theme-dark')
    root.classList.add(themeMode === 'light' ? 'theme-light' : 'theme-dark')
  }, [themeMode])

  return (
    <>
      <MainLayout />
      {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}
    </>
  )
}
