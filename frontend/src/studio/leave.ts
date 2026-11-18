import { useEffect } from 'react'

// Studio runs on its own document: browser Back, reload, tab close and the
// workbench link all use the same native unsaved-work guard.
export function useUnsavedWarning(dirty: boolean) {
  useEffect(() => {
    if (!dirty) return
    const guard = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', guard)
    return () => window.removeEventListener('beforeunload', guard)
  }, [dirty])
}
