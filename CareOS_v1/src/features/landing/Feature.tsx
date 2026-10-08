import { ArrowRight } from "lucide-react";
import type { ReactNode } from "react";

export function Feature({ step, icon, title, detail }: { step: string; icon: ReactNode; title: string; detail: string }) {
  return (
    <article className="landing-feature">
      <div className="feature-topline"><span className="feature-step">{step}</span><span className="feature-rule" /></div>
      <div className="feature-icon">{icon}</div>
      <h3>{title}</h3>
      <p>{detail}</p>
      <span className="feature-arrow"><ArrowRight size={15} /></span>
    </article>
  );
}
