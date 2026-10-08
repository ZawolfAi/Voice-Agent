import {
  Database,
  HeartPulse,
  MoreHorizontal,
  Settings,
  ShieldCheck,
} from "lucide-react";
import type { Language, TranslationKey } from "../../i18n";
import type { AppView } from "../../app/routes";
import { viewFromLocation } from "../../app/routes";
import { navItems, roleNavMap, type Role } from "../workspace/navigation";

type Translator = (key: TranslationKey) => string;

type SidebarProps = {
  view: AppView;
  setView: (view: AppView) => void;
  mobileNav: boolean;
  setMobileNav: (open: boolean) => void;
  language: Language;
  doctorName: string;
  role: Role;
  t: Translator;
};

export function Sidebar({ view, setView, mobileNav, setMobileNav, language, doctorName, role, t }: SidebarProps) {
  const visibleViews = roleNavMap[role] ?? roleNavMap.doctor;
  const routeView = viewFromLocation();
  const displayedView = role === "patient" && view === "portal" && (routeView === "appointments" || routeView === "messages") ? routeView : view;

  return (
    <aside className={`sidebar ${mobileNav ? "is-open" : ""}`}>
      <div className="brand">
        <div className="brand-mark"><HeartPulse size={19} /></div>
        <span>care<span>os</span></span>
      </div>
      <div className="workspace-label">{language === "ar" ? "مساحة العمل السريرية" : "CLINICAL WORKSPACE"}</div>
      <nav>
        <div className="nav-section-label">{language === "ar" ? "مساحة العمل" : "WORKSPACE"}</div>
        {navItems.filter(({ id }) => visibleViews.includes(id)).map(({ id, label, icon: Icon }) => (
          <button key={id} className={`nav-item ${displayedView === id ? "active" : ""}`} onClick={() => { setView(id); setMobileNav(false); }}>
            <Icon size={18} strokeWidth={1.8} />
            <span>{t(label)}</span>
            {id === "assistant" && <span className="new-dot" />}
          </button>
        ))}
      </nav>
      <div className="sidebar-bottom">
        {visibleViews.includes("integrations") && <button className={`nav-item ${view === "integrations" ? "active" : ""}`} onClick={() => setView("integrations")}>
          <Database size={18} />
          <span>{language === "ar" ? "التكاملات" : "Integrations"}</span>
        </button>}
        {visibleViews.includes("settings") && <button className={`nav-item ${view === "settings" ? "active" : ""}`} onClick={() => setView("settings")}>
          <Settings size={18} />
          <span>{t("settings")}</span>
        </button>}
        <div className="security-note">
          <ShieldCheck size={17} />
          <div><strong>{t("secure")}</strong><span>{t("secureDetail")}</span></div>
        </div>
        <button className={`profile-card ${view === "account" ? "active" : ""}`} onClick={() => { setView("account"); setMobileNav(false); }} aria-label="Open account">
          <div className="avatar avatar-doctor">DR</div>
          <div className="profile-copy"><strong>{doctorName}</strong><span>{t("specialty")}</span></div>
          <MoreHorizontal size={16} />
        </button>
      </div>
    </aside>
  );
}
