import type { ButtonHTMLAttributes, ReactNode } from 'react'

import { cn, focusRing } from '../lib/ui'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'sm' | 'md'

const VARIANTS: Record<Variant, string> = {
  // The brand gradient on a primary CTA is one of Doc 04's four permitted uses,
  // and the low-opacity glow behind it is the one place a glow is earned.
  primary: 'bg-linear-to-r from-brand-start to-brand-end text-white shadow-glow',
  secondary: 'border border-border text-ink',
  ghost: 'text-muted enabled:hover:text-ink',
  danger: 'bg-critical text-white',
}

const SIZES: Record<Size, string> = {
  sm: 'h-[36px] px-12 text-body-sm', // dense/inline only — below the touch minimum
  md: 'h-[44px] px-16 text-body', // the Doc 04 minimum tap target
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
        'transition-[filter,background-color,color] duration-button ease-in-out',
        // Doc 04 Component Behavior: +8% on hover, -5% on press, 40% when disabled.
        'enabled:hover:brightness-108 enabled:active:brightness-95',
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
