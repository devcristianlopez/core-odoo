import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AlertTriangle } from 'lucide-react'
import { Button } from './Button'
import { Modal } from './Modal'
import { Input } from './Input'

export interface ConfirmDialogProps {
  open: boolean
  onClose: () => void
  onConfirm: () => void
  title: string
  description: string
  warning?: string
  confirmLabel: string
  cancelLabel?: string
  destructive?: boolean
  loading?: boolean
  requireText?: string
  requireTextHint?: string
}

export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  description,
  warning,
  confirmLabel,
  cancelLabel,
  destructive = false,
  loading = false,
  requireText,
  requireTextHint,
}: ConfirmDialogProps) {
  const { t } = useTranslation()
  const [typed, setTyped] = useState('')

  useEffect(() => {
    if (open) setTyped('')
  }, [open])

  const blocked = Boolean(requireText) && typed !== requireText
  return (
    <Modal
      open={open}
      onClose={loading ? () => undefined : onClose}
      title={title}
      description={description}
      size="sm"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={loading}>
            {cancelLabel ?? t('common.cancel')}
          </Button>
          <Button
            variant={destructive ? 'danger' : 'primary'}
            onClick={onConfirm}
            loading={loading}
            disabled={blocked}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      {requireText ? (
        <div className="mb-3 space-y-1.5">
          <label htmlFor="confirm-dialog-text" className="text-xs font-medium text-slate-300">
            {requireTextHint ?? t('common.confirmValue', { value: requireText })}
          </label>
          <Input
            id="confirm-dialog-text"
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
            placeholder={requireText}
            autoComplete="off"
          />
        </div>
      ) : null}
      {warning ? (
        <div className="flex gap-3 rounded-lg border border-danger-500/30 bg-danger-900/30 px-4 py-3 text-sm text-danger-400">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <p>{warning}</p>
        </div>
      ) : null}
    </Modal>
  )
}
