import {
  forwardRef,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
} from 'react'
import { cn } from '../../lib/utils'

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { className, invalid, ...props },
  ref,
) {
  return (
    <input
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(
        'h-10 w-full rounded-lg border border-edge bg-surface-muted px-3 text-sm text-slate-100',
        'placeholder:text-slate-500 focus:border-accent-500 focus:outline-none focus:ring-2 focus:ring-accent-500/30',
        'disabled:cursor-not-allowed disabled:opacity-60',
        invalid && 'border-danger-500/70 focus:border-danger-400 focus:ring-danger-500/30',
        className,
      )}
      {...props}
    />
  )
})

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  invalid?: boolean
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { className, invalid, children, ...props },
  ref,
) {
  return (
    <select
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(
        'h-10 w-full rounded-lg border border-edge bg-surface-muted px-3 text-sm text-slate-100',
        'focus:border-accent-500 focus:outline-none focus:ring-2 focus:ring-accent-500/30',
        'disabled:cursor-not-allowed disabled:opacity-60',
        invalid && 'border-danger-500/70',
        className,
      )}
      {...props}
    >
      {children}
    </select>
  )
})

export function Label({
  htmlFor,
  children,
  optional,
  optionalLabel,
  className,
}: {
  htmlFor: string
  children: ReactNode
  optional?: boolean
  optionalLabel?: string
  className?: string
}) {
  return (
    <label htmlFor={htmlFor} className={cn('mb-1.5 flex items-center gap-1.5 text-xs font-medium text-slate-300', className)}>
      {children}
      {optional && optionalLabel ? (
        <span className="font-normal text-slate-500">({optionalLabel})</span>
      ) : null}
    </label>
  )
}

export function FieldHint({ id, children }: { id?: string; children: ReactNode }) {
  return (
    <p id={id} className="mt-1.5 text-xs text-slate-500">
      {children}
    </p>
  )
}

export function FieldError({ id, children }: { id?: string; children: ReactNode }) {
  return (
    <p id={id} className="mt-1.5 text-xs text-danger-400" role="alert">
      {children}
    </p>
  )
}
