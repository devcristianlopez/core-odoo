import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertTriangle, RotateCw } from 'lucide-react'
import i18n from '../lib/i18n'

interface ErrorBoundaryState {
  hasError: boolean
}

export class ErrorBoundary extends Component<{ children: ReactNode }, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false }

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('Mission Control crashed', error, info)
  }

  render(): ReactNode {
    if (!this.state.hasError) return this.props.children
    return (
      <div className="flex min-h-screen items-center justify-center bg-canvas p-6">
        <div role="alert" className="w-full max-w-md rounded-xl border border-danger-500/30 bg-surface p-6 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-danger-900/60 text-danger-400">
            <AlertTriangle className="h-6 w-6" aria-hidden="true" />
          </div>
          <h1 className="text-lg font-semibold text-white">{i18n.t('errors.generic')}</h1>
          <p className="mt-1 text-sm text-slate-400">{i18n.t('errors.loadFailedHint')}</p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="mt-5 inline-flex h-10 items-center gap-2 rounded-lg bg-accent-600 px-4 text-sm font-medium text-white hover:bg-accent-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400"
          >
            <RotateCw className="h-4 w-4" aria-hidden="true" />
            {i18n.t('common.retry')}
          </button>
        </div>
      </div>
    )
  }
}
