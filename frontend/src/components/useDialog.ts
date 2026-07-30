import { useEffect, useRef } from 'react'

/**
 * Drives a native `<dialog>` from React state.
 *
 * `showModal()` is used deliberately rather than a hand-rolled overlay: the
 * platform already gives us the focus trap, the inert background, Escape-to-
 * dismiss and the `::backdrop` element that Doc 04 asks for on modals and
 * drawers, with none of the code.
 *
 * ponytail: no exit animation — that needs a delayed unmount. Entrances are
 * what Doc 04 actually specifies; add the close transition if it reads abrupt.
 */
export function useDialog(open: boolean, onClose: () => void) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    else if (!open && dialog.open) dialog.close()
  }, [open])

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    // Fires for Escape and for programmatic close(); keeps React state in step.
    const onNativeClose = () => onClose()
    // A click that lands on the dialog element itself is a backdrop click —
    // the content sits in a child, so it never registers as the target.
    const onClick = (e: MouseEvent) => {
      if (e.target === dialog) onClose()
    }
    dialog.addEventListener('close', onNativeClose)
    dialog.addEventListener('click', onClick)
    return () => {
      dialog.removeEventListener('close', onNativeClose)
      dialog.removeEventListener('click', onClick)
    }
  }, [onClose])

  return ref
}
