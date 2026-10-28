import { useEffect, useId, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import {
  Boxes,
  FolderKanban,
  LayoutDashboard,
  LogOut,
  Menu,
  ScrollText,
  Settings,
  UserRound,
  Users,
  CheckCheck,
  X,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../../lib/auth-context'
import { useToast } from '../../lib/toast-context'
import { cn } from '../../lib/utils'
import { LanguageSwitcher } from '../LanguageSwitcher'
import { Button } from '../ui/Button'

interface NavItem {
  to: string
  labelKey: string
  icon: LucideIcon
  end?: boolean
  adminOnly?: boolean
  operatorOnly?: boolean
}

const NAV_ITEMS: NavItem[] = [
  { to: '/', labelKey: 'nav.dashboard', icon: LayoutDashboard, end: true },
  { to: '/projects', labelKey: 'nav.projects', icon: FolderKanban },
  { to: '/approvals', labelKey: 'nav.approvals', icon: CheckCheck, operatorOnly: true },
  { to: '/users', labelKey: 'nav.users', icon: Users, adminOnly: true },
  { to: '/audit', labelKey: 'nav.audit', icon: ScrollText },
  { to: '/settings', labelKey: 'nav.settings', icon: Settings },
]

function Brand({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation()
  return (
    <Link
      to="/"
      onClick={onNavigate}
      aria-label={t('nav.brandHome')}
      className="flex items-center gap-3 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400"
    >
      <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 via-brand-600 to-accent-700 shadow-glow">
        <Boxes className="h-5 w-5 text-white" aria-hidden="true" />
      </span>
      <span className="min-w-0">
        <span className="block truncate text-sm font-semibold text-white">{t('app.name')}</span>
        <span className="block truncate text-[11px] text-slate-500">{t('app.tagline')}</span>
      </span>
    </Link>
  )
}

function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation()
  const { user } = useAuth()
  const items = NAV_ITEMS.filter(
    (item) =>
      (!item.adminOnly || user?.role === 'admin') &&
      (!item.operatorOnly || user?.role === 'admin' || user?.role === 'operator'),
  )
  return (
    <nav aria-label={t('nav.primary')} className="flex flex-1 flex-col gap-1 px-3 py-4">
      {items.map((item) => {
        const Icon = item.icon
        return (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                'group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400',
                isActive
                  ? 'bg-accent-900/50 text-white ring-1 ring-inset ring-accent-500/30'
                  : 'text-slate-400 hover:bg-surface-raised hover:text-slate-100',
              )
            }
          >
            {({ isActive }) => (
              <>
                <Icon
                  className={cn('h-4 w-4 shrink-0', isActive ? 'text-accent-300' : 'text-slate-500')}
                  aria-hidden="true"
                />
                <span className="truncate">{t(item.labelKey)}</span>
              </>
            )}
          </NavLink>
        )
      })}
    </nav>
  )
}

function MobileDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation()
  const panelRef = useRef<HTMLDivElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const titleId = useId()
  const closeRefState = useRef(onClose)

  useEffect(() => {
    closeRefState.current = onClose
  }, [onClose])

  useEffect(() => {
    if (!open) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.setTimeout(() => closeRef.current?.focus(), 0)
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        closeRefState.current()
        return
      }
      if (event.key !== 'Tab' || !panelRef.current) return
      const focusable = [
        ...panelRef.current.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      ].filter((element) => element.offsetParent !== null)
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (!first || !last) return
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [open])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-40 lg:hidden">
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] animate-slide-in-left flex-col border-r border-edge bg-surface shadow-2xl"
      >
        <div className="flex items-center justify-between gap-3 border-b border-edge-muted px-4 py-3">
          <span id={titleId} className="text-sm font-semibold text-white">
            {t('nav.primary')}
          </span>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label={t('nav.closeMenu')}
            className="rounded-md p-2 text-slate-400 hover:bg-surface-raised hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        <div className="border-b border-edge-muted px-4 py-3">
          <Brand onNavigate={onClose} />
        </div>
        <SidebarNav onNavigate={onClose} />
      </div>
    </div>
  )
}

export function AppShell() {
  const { t } = useTranslation()
  const { user, logout } = useAuth()
  const { pushToast } = useToast()
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    setMenuOpen(false)
  }, [location.pathname])

  return (
    <div className="min-h-screen bg-canvas text-slate-200">
      <a
        href="#main-content"
        className="sr-only z-[70] rounded-md bg-accent-600 px-3 py-2 text-sm text-white focus:not-sr-only focus:fixed focus:left-4 focus:top-4"
      >
        {t('nav.skipToContent')}
      </a>

      <aside className="fixed inset-y-0 left-0 z-20 hidden w-64 flex-col border-r border-edge bg-surface-muted lg:flex">
        <div className="border-b border-edge-muted px-4 py-4">
          <Brand />
        </div>
        <SidebarNav />
        <div className="border-t border-edge-muted px-4 py-3 text-[11px] text-slate-500">
          <p className="font-medium text-slate-400">Kizuku</p>
          <p>{t('app.description')}</p>
        </div>
      </aside>

      <div className="lg:pl-64">
        <header className="sticky top-0 z-30 border-b border-edge bg-canvas/85 backdrop-blur">
          <div className="flex h-16 items-center justify-between gap-3 px-4 sm:px-6 lg:px-8">
            <div className="flex min-w-0 items-center gap-3">
              <Button
                variant="ghost"
                size="icon"
                className="lg:hidden"
                onClick={() => setMenuOpen(true)}
                aria-label={t('nav.openMenu')}
              >
                <Menu className="h-4 w-4" aria-hidden="true" />
              </Button>
              <div className="lg:hidden">
                <Brand />
              </div>
              <p className="hidden truncate text-xs uppercase tracking-[0.16em] text-slate-500 lg:block">
                {t('app.tagline')}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2 sm:gap-3">
              <LanguageSwitcher />
              <div className="hidden h-6 w-px bg-edge sm:block" aria-hidden="true" />
              <div className="hidden items-center gap-2 rounded-lg border border-edge bg-surface-raised px-2.5 py-1.5 sm:flex">
                <UserRound className="h-3.5 w-3.5 text-slate-400" aria-hidden="true" />
                <span className="max-w-[10rem] truncate text-xs font-medium text-slate-200">
                  {user?.username ?? t('auth.userFallback')}
                </span>
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => {
                  logout()
                  pushToast({ title: t('auth.signedOut'), variant: 'info' })
                }}
                aria-label={t('common.logout')}
                title={t('common.logout')}
              >
                <LogOut className="h-4 w-4" aria-hidden="true" />
              </Button>
            </div>
          </div>
        </header>

        <main id="main-content" className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <Outlet />
        </main>
      </div>

      <MobileDrawer open={menuOpen} onClose={() => setMenuOpen(false)} />
    </div>
  )
}
