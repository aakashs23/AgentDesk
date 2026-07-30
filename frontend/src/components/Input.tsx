import { Check } from 'lucide-react'
import { useId, useState, type InputHTMLAttributes } from 'react'

import { cn, focusRing } from '../lib/ui'

export interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'onBlur'> {
  label: string
  hint?: string
  /** Server-side or form-level error, shown regardless of blur state. */
  error?: string
  /**
   * Doc 04: validation is inline **on blur**, never on every keystroke. Return
   * a short, specific message — never a vague "invalid input" — or null to pass.
   * Passing this is what earns the success checkmark.
   */
  validate?: (value: string) => string | null
}

export function Input({ label, hint, error, validate, className, id, ...props }: InputProps) {
  const generatedId = useId()
  const inputId = id ?? generatedId
  const [blurError, setBlurError] = useState<string | null>(null)
  const [valid, setValid] = useState(false)

  const shown = error ?? blurError
  const messageId = `${inputId}-message`

  return (
    <div className="flex flex-col gap-8">
      <label htmlFor={inputId} className="text-body-sm text-muted font-medium">
        {label}
      </label>
      <div className="relative">
        <input
          {...props}
          id={inputId}
          aria-invalid={shown ? true : undefined}
          aria-describedby={shown || hint ? messageId : undefined}
          onBlur={(e) => {
            if (!validate) return
            const message = validate(e.target.value)
            setBlurError(message)
            setValid(!message && e.target.value !== '')
          }}
          onChange={(e) => {
            // Clear a stale blur error as soon as the user starts fixing it,
            // but don't re-validate until the next blur.
            if (blurError) setBlurError(null)
            if (valid) setValid(false)
            props.onChange?.(e)
          }}
          className={cn(
            'rounded-control bg-canvas text-ink h-[44px] w-full border px-12',
            'placeholder:text-muted transition-colors duration-micro',
            shown ? 'border-critical' : 'border-border focus:border-brand-start',
            'disabled:cursor-not-allowed disabled:opacity-40',
            valid && 'pr-32', // room for the success checkmark
            focusRing,
            className,
          )}
        />
        {valid && !shown && (
          <Check
            aria-hidden
            size={16}
            strokeWidth={1.5}
            className="text-success absolute top-1/2 right-12 -translate-y-1/2"
          />
        )}
      </div>
      {(shown || hint) && (
        <p
          id={messageId}
          className={cn('text-body-sm', shown ? 'text-critical' : 'text-muted')}
          role={shown ? 'alert' : undefined}
        >
          {shown ?? hint}
        </p>
      )}
    </div>
  )
}
