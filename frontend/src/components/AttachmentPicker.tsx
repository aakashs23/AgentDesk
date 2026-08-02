import { AlertCircle, Check, Paperclip, RotateCcw, X } from 'lucide-react'
import { useId, useRef } from 'react'

import { ALLOWED_MIME_TYPES, MAX_ATTACHMENT_BYTES } from '../lib/attachments'
import { cn, focusRing, formatBytes, tapTarget } from '../lib/ui'

export type QueuedStatus = 'queued' | 'uploading' | 'done' | 'error'

export interface QueuedFile {
  /** Client-side key; the server id only exists once uploaded. */
  key: string
  file: File
  status: QueuedStatus
  progress: number
  error?: string
}

export function AttachmentPicker({
  files,
  onAdd,
  onRemove,
  onRetry,
  disabled,
}: {
  files: QueuedFile[]
  onAdd: (files: File[]) => void
  onRemove: (key: string) => void
  onRetry?: (key: string) => void
  disabled?: boolean
}) {
  const inputId = useId()
  const input = useRef<HTMLInputElement>(null)

  return (
    <div className="flex flex-col gap-8">
      <span className="text-body-sm text-muted font-medium">Attachments (optional)</span>

      <input
        ref={input}
        id={inputId}
        type="file"
        multiple
        className="sr-only"
        disabled={disabled}
        accept={[...ALLOWED_MIME_TYPES, 'image/*'].join(',')}
        onChange={(e) => {
          onAdd(Array.from(e.target.files ?? []))
          // Reset so re-picking the same file still fires a change event.
          e.target.value = ''
        }}
      />
      <label
        htmlFor={inputId}
        className={cn(
          'rounded-control border-border text-body text-muted hover:text-ink',
          'flex cursor-pointer items-center gap-8 border border-dashed px-16 py-16',
          'transition-colors duration-micro',
          disabled && 'pointer-events-none opacity-40',
        )}
      >
        <Paperclip aria-hidden size={16} strokeWidth={1.5} />
        Choose files — images, PDF, or Office documents up to {MAX_ATTACHMENT_BYTES / (1024 * 1024)}
        MB
      </label>

      {files.length > 0 && (
        <ul className="flex flex-col gap-8">
          {files.map((queued) => (
            <li
              key={queued.key}
              className="rounded-control border-border flex items-center gap-12 border p-12"
            >
              <div className="min-w-0 flex-1">
                <p className="text-body-sm text-ink truncate">{queued.file.name}</p>
                <p className="text-caption text-muted">
                  {queued.status === 'error' ? queued.error : formatBytes(queued.file.size)}
                </p>
                {queued.status === 'uploading' && (
                  <div
                    role="progressbar"
                    aria-valuenow={Math.round(queued.progress * 100)}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label={`Uploading ${queued.file.name}`}
                    className="bg-surface mt-8 h-1 w-full overflow-hidden rounded-pill"
                  >
                    <div
                      className="bg-primary h-full transition-[width] duration-micro"
                      style={{ width: `${queued.progress * 100}%` }}
                    />
                  </div>
                )}
              </div>

              {queued.status === 'done' && (
                <Check aria-label="Uploaded" size={16} strokeWidth={1.5} className="text-success" />
              )}
              {queued.status === 'error' && (
                <>
                  <AlertCircle aria-hidden size={16} strokeWidth={1.5} className="text-critical" />
                  {onRetry && (
                    <button
                      type="button"
                      onClick={() => onRetry(queued.key)}
                      aria-label={`Retry ${queued.file.name}`}
                      className={cn('text-muted hover:text-ink cursor-pointer', focusRing)}
                    >
                      <RotateCcw size={16} strokeWidth={1.5} />
                    </button>
                  )}
                </>
              )}
              <button
                type="button"
                onClick={() => onRemove(queued.key)}
                aria-label={`Remove ${queued.file.name}`}
                className={cn(
                  'text-muted hover:text-ink flex cursor-pointer items-center justify-center',
                  tapTarget,
                  focusRing,
                )}
              >
                <X size={16} strokeWidth={1.5} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
