import type { ButtonHTMLAttributes, ReactNode } from 'react'

import { cn, focusRing } from '../lib/ui'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'sm' | 'md'

const VARIANTS: Record<Variant, string> = {
  // Doc 07 §11. Flat fill, no gradient and no glow — the gradient went with
  // Doc 04, and colour on a CTA is now the same blue as every other action.
  primary: 'bg-primary-fill enabled:hover:bg-primary-hover text-white',
  secondary: 'border border-border text-ink enabled:hover:bg-sunken',
  ghost: 'text-muted enabled:hover:text-ink enabled:hover:bg-sunken',
  danger: 'bg-critical-fill text-white',
}

const SIZES: Record<Size, string> = {
  sm: 'h-[36px] px-12 text-body-sm', // Doc 07 standard; dense/inline only
  md: 'h-[44px] px-16 text-body', // Doc 07 large, and the iOS tap minimum
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  icon?: ReactNode
}

export function Button({
  variant = 'secondary',
  size = 'md',
  icon,
  className,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      {...props}
      className={cn(
        'rounded-control inline-flex cursor-pointer items-center justify-center gap-8 font-medium',
        'transition-[filter,background-color,color,border-color] duration-button ease-out',
        // Doc 07 §11 gives each variant its own hover fill, so the only global
        // effects left are the press dim and the disabled state.
        'enabled:active:brightness-95',
        'disabled:cursor-not-allowed disabled:opacity-40',
        VARIANTS[variant],
        SIZES[size],
        focusRing,
        className,
      )}
    >
      {icon}
      {children}
    </button>
  )
}
