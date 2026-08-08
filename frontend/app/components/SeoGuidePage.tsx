import Link from "next/link";
import { ArrowRight, CheckCircle2 } from "lucide-react";
import { AppShell } from "./AppShell";

export function SeoGuidePage({ kicker, title, lead, points, cta = "Открыть калькулятор", href = "/score" }: {
  kicker: string; title: string; lead: string; points: string[]; cta?: string; href?: string;
}) {
  return (
    <AppShell active="score" eyebrow="Справочный материал" title={kicker}>
      <article className="seo-guide">
        <span className="section-kicker">{kicker}</span>
        <h2>{title}</h2>
        <p className="seo-lead">{lead}</p>
        <ul>{points.map((point) => <li key={point}><CheckCircle2 size={18} aria-hidden="true" />{point}</li>)}</ul>
        <div className="public-disclaimer"><strong>Предварительная оценка</strong><p>Материал не является обещанием одобрения. Финальное решение и индивидуальные условия определяет банк.</p></div>
        <Link className="button button-dark" href={href}>{cta}<ArrowRight size={17} aria-hidden="true" /></Link>
      </article>
    </AppShell>
  );
}
