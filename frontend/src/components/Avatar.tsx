import { cn, initials } from '../lib/ui'

// Doc 04/05: no photo uploads in the prototype, deliberately — there is no
// avatar column in the schema, so every user renders identically.
const FILLS = ['bg-avatar-1', 'bg-avatar-2', 'bg-avatar-3', 'bg-avatar-4', 'bg-avatar-5'] as const

// Explicit px: bare `size-8` would resolve against the spacing scale (8px),
// not Tailwind's default rem step. Type sizes stay on the Doc 04 scale.
const SIZES = {
  sm: 'size-[24px] text-caption',
  md: 'size-[32px] text-body-sm',
  lg: 'size-[48px] text-body',
} as const

export interface AvatarProps {
  name: string
  /** Stable key for colour selection — the user id, so the same person always
   *  gets the same fill even if their display name changes. */
  seed?: string
  size?: keyof typeof SIZES
  className?: string
}

export function Avatar({ name, seed, size = 'md', className }: AvatarProps) {
  const key = seed ?? name
  let hash = 0
  for (let i = 0; i < key.length; i++) hash = (hash * 31 + key.charCodeAt(i)) >>> 0

  return (
    <span
      aria-label={name}
      title={name}
      className={cn(
        'rounded-pill inline-flex shrink-0 items-center justify-center font-medium text-white',
        FILLS[hash % FILLS.length],
        SIZES[size],
        className,
      )}
    >
      {initials(name)}
    </span>
  )
}
