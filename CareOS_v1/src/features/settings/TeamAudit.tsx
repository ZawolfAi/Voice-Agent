import { useEffect, useState } from "react";
import { MoreHorizontal, Plus, ShieldCheck } from "lucide-react";
import { getAuditEvents, getTeam } from "../../api/team";
import type { Language, TranslationKey } from "../../i18n";
import { PageHeading } from "../../components/PageHeading";

type Translator = (key: TranslationKey) => string;

type TeamAuditProps = { t: Translator; language: Language };

export function TeamAudit({ t, language }: TeamAuditProps) {
  const [tab, setTab] = useState<"team" | "audit">("team");
  const [members, setMembers] = useState<Array<{ name: string; email: string; role: string; status: string }>>([]);
  const [events, setEvents] = useState<Array<{ action: string; resource: string; time: string }>>([]);

  useEffect(() => {
    Promise.all([getTeam(), getAuditEvents()]).then(([team, audit]) => {
      setMembers(team.map((member) => ({ name: member.full_name, email: member.email, role: member.role, status: member.onboarding_complete ? t("active") : t("invited") })));
      setEvents(audit.map((event) => ({ action: event.action, resource: event.resource, time: new Date(event.created_at).toLocaleString() })));
    }).catch(() => {
      setMembers([]);
      setEvents([]);
    });
  }, [t]);

  return (
    <>
      <PageHeading eyebrow={t("teamAuditEyebrow")} title={t("teamAuditTitle")} detail={t("teamAuditDetail")} action={<button className="primary-btn"><Plus size={16} /> {t("inviteMember")}</button>} />
      <section className="panel team-audit-panel">
        <div className="tabs team-audit-tabs">
          <button className={tab === "team" ? "active" : ""} onClick={() => setTab("team")}>{t("teamMembers")}</button>
          <button className={tab === "audit" ? "active" : ""} onClick={() => setTab("audit")}>{t("auditLog")}</button>
        </div>
        {tab === "team" ? (
          <div className="team-list">{members.map((member) => <div className="team-row" key={member.email}><div className="avatar avatar-doctor">{member.name.split(" ").map((part) => part[0]).join("").slice(0, 2)}</div><div className="team-person"><strong>{member.name}</strong><span>{member.email}</span></div><span>{member.role}</span><span className="status confirmed">{member.status}</span><button className="round-btn" aria-label={language === "ar" ? "المزيد" : "More actions"}><MoreHorizontal size={16} /></button></div>)}</div>
        ) : (
          <div className="audit-list">{events.map((event) => <div className="audit-row" key={`${event.action}-${event.resource}`}><div className="audit-icon"><ShieldCheck size={15} /></div><div><strong>{event.action}</strong><span>{event.resource}</span></div><time>{event.time}</time></div>)}</div>
        )}
      </section>
    </>
  );
}
