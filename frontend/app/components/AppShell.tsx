import Link from "next/link";
import type { ReactNode } from "react";
import {
  Activity,
  ChevronDown,
  CircleHelp,
  Clock3,
  Files,
  LayoutDashboard,
  ListChecks,
  BadgePercent,
  ScanLine,
  ShieldCheck,
  TrendingUp,
} from "lucide-react";

type NavKey = "overview" | "score" | "offers" | "operator" | "offerManagement" | "commercial" | "batches" | "history" | "model";

const publicNavigation = [
  { key: "overview", href: "/", label: "Главная", icon: LayoutDashboard },
  { key: "score", href: "/score", label: "Калькулятор", icon: ScanLine },
  { key: "offers", href: "/offers", label: "Подбор предложений", icon: BadgePercent },
] as const;

const operatorNavigation = [
  { key: "operator", href: "/operator", label: "Обзор бизнеса", icon: LayoutDashboard },
  { key: "commercial", href: "/commercial", label: "Партнёрские переходы", icon: TrendingUp },
  { key: "offerManagement", href: "/operator/offers", label: "Офферы", icon: ListChecks },
  { key: "history", href: "/history", label: "Заявки и подборы", icon: Clock3 },
  { key: "batches", href: "/batches", label: "Импорт и задачи", icon: Files },
  { key: "score", href: "/operator/score", label: "Расчётный модуль", icon: ScanLine },
  { key: "model", href: "/operator/system", label: "Состояние системы", icon: ShieldCheck },
] as const;

interface AppShellProps {
  active: NavKey;
  eyebrow: string;
  title: string;
  children: ReactNode;
  operator?: boolean;
}

export function AppShell({ active, eyebrow, title, children, operator = false }: AppShellProps) {
  const navigation = operator ? operatorNavigation : publicNavigation;
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
          <p className="nav-caption">{operator ? "Внутренний контур" : "Публичный сервис"}</p>
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
            <strong>{operator ? "Контур наблюдаем" : "Минимум данных"}</strong>
            <span>{operator ? "Доступ только для сотрудников" : "Без паспорта, телефона и БКИ"}</span>
          </div>
        </div>

        <Link className="help-link" href={operator ? "/operator/system" : "/offers"}>
          <CircleHelp size={18} aria-hidden="true" />
          {operator ? "Помощь по системе" : "Как работает подбор"}
        </Link>
      </aside>

      <div className="app-surface">
        <header className="topbar">
          <div>
            <span className="eyebrow">{eyebrow}</span>
            <h1>{title}</h1>
          </div>
          <button className="profile-button" type="button" aria-label={operator ? "Кабинет оператора" : "Личный кабинет Riskline"}>
            <span className="profile-avatar">RL</span>
            <span className="profile-copy">
              <strong>{operator ? "Кабинет оператора" : "Riskline"}</strong>
              <small>{operator ? "внутренний кабинет" : "личный кабинет"}</small>
            </span>
            <ChevronDown size={16} aria-hidden="true" />
          </button>
        </header>

        <main className="workspace">{children}</main>

        <nav className="mobile-nav" aria-label="Мобильная навигация">
          {navigation.slice(0, 5).map((item) => {
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
