/**
 * Client-side attachment rules, mirroring app/tickets/service.py (TRD §8).
 *
 * This is a courtesy check that keeps the form responsive — the server still
 * re-validates every upload, including the magic-byte sniff the browser cannot
 * do. Never treat passing this as proof a file is acceptable.
 */

export const ALLOWED_MIME_TYPES = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
]

export const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024

export function isMimeAllowed(mime: string) {
  return mime.startsWith('image/') || ALLOWED_MIME_TYPES.includes(mime)
}

/** Doc 03 §13 steps 2–5: type first, then size; a rejection names the reason. */
export function validateFile(file: { name: string; type: string; size: number }): string | null {
  if (!isMimeAllowed(file.type)) return `${file.name}: unsupported file type`
  if (file.size > MAX_ATTACHMENT_BYTES) {
    return `${file.name}: exceeds the ${MAX_ATTACHMENT_BYTES / (1024 * 1024)}MB limit`
  }
  return null
}
