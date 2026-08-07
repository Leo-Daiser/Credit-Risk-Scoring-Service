import Link from "next/link";
import type { ReactNode } from "react";
import {
  Activity,
  ChevronDown,
  CircleHelp,
  Clock3,
  Files,
  LayoutDashboard,
  ScanLine,
  ShieldCheck,
} from "lucide-react";

type NavKey = "overview" | "score" | "batches" | "history" | "model";

const navigation = [
  { key: "overview", href: "/", label: "Обзор", icon: LayoutDashboard },
  { key: "score", href: "/score", label: "Новая оценка", icon: ScanLine },
  { key: "batches", href: "/batches", label: "Пакетный скоринг", icon: Files },
  { key: "history", href: "/history", label: "История", icon: Clock3 },
  { key: "model", href: "/model", label: "Модель и контур", icon: ShieldCheck },
] as const;

interface AppShellProps {
  active: NavKey;
  eyebrow: string;
  title: string;
  children: ReactNode;
}

export function AppShell({ active, eyebrow, title, children }: AppShellProps) {
  return (
    <div className="app-frame">
      <aside className="sidebar">
        <Link className="brand" href="/" aria-label="Riskline — на главную">
          <span className="brand-mark" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          <span>riskline</span>
        </Link>

        <nav className="side-nav" aria-label="Основная навигация">
          <p className="nav-caption">Рабочее пространство</p>
          {navigation.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.key}
                className={`nav-link ${active === item.key ? "is-active" : ""}`}
                href={item.href}
                aria-current={active === item.key ? "page" : undefined}
              >
                <Icon size={19} strokeWidth={1.9} aria-hidden="true" />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="sidebar-note">
          <div className="note-icon" aria-hidden="true">
            <Activity size={18} />
          </div>
          <div>
            <strong>Контур наблюдаем</strong>
            <span>API, worker и PostgreSQL</span>
          </div>
        </div>

        <Link className="help-link" href="/model#contract">
          <CircleHelp size={18} aria-hidden="true" />
          Как подготовить данные
        </Link>
      </aside>

      <div className="app-surface">
        <header className="topbar">
          <div>
            <span className="eyebrow">{eyebrow}</span>
            <h1>{title}</h1>
          </div>
          <button className="profile-button" type="button" aria-label="Профиль среды portfolio">
            <span className="profile-avatar">ML</span>
            <span className="profile-copy">
              <strong>Portfolio workspace</strong>
              <small>внутренний контур</small>
            </span>
            <ChevronDown size={16} aria-hidden="true" />
          </button>
        </header>

        <main className="workspace">{children}</main>

        <nav className="mobile-nav" aria-label="Мобильная навигация">
          {navigation.slice(0, 4).map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.key}
                className={active === item.key ? "is-active" : ""}
                href={item.href}
                aria-label={item.label}
              >
                <Icon size={21} aria-hidden="true" />
                <span>{item.label.split(" ")[0]}</span>
              </Link>
            );
          })}
        </nav>
      </div>
    </div>
  );
}
