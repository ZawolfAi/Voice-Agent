import { useEffect, useState } from "react";
import {
  Bell,
  Check,
  LogOut,
  Moon,
  ShieldCheck,
  SlidersHorizontal,
  Sun,
  UserRound,
} from "lucide-react";
import {
  enrollMfa,
  getCurrentUser,
  getNotifications,
  markNotificationRead,
  regenerateMfaRecoveryCodes,
  verifyMfa,
} from "../../api";
import { completeOrganization, getOrganization } from "../../api/workspace";
import { PageHeading } from "../../components/PageHeading";
import { PanelHeading } from "../../components/PanelHeading";
import type { Language, TranslationKey } from "../../i18n";

type Translator = (key: TranslationKey) => string;
type Theme = "light" | "dark";
type SettingsSection = "profile" | "preferences" | "security" | "notifications";
type NotificationItem = Awaited<ReturnType<typeof getNotifications>>[number];
type Props = {
  language: Language;
  setLanguage: (language: Language) => void;
  theme: Theme;
  setTheme: (theme: Theme) => void;
  doctorName: string;
  setDoctorName: (name: string) => void;
  onLogout: () => void;
  t: Translator;
};

export function SettingsPage({
  language,
  setLanguage,
  theme,
  setTheme,
  doctorName,
  setDoctorName,
  onLogout,
  t,
}: Props) {
  const [organizationName, setOrganizationName] = useState("");
  const [organizationDepartment, setOrganizationDepartment] =
    useState("Clinical care");
  const [organizationTimezone, setOrganizationTimezone] =
    useState("Africa/Cairo");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [activeSection, setActiveSection] = useState<SettingsSection>("profile");
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [notificationsLoading, setNotificationsLoading] = useState(false);
  const [mfaEnabled, setMfaEnabled] = useState<boolean | null>(null);
  const [mfaSecret, setMfaSecret] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [actionError, setActionError] = useState<string | null>(null);
  useEffect(() => {
    getOrganization()
      .then((organization) => {
        setOrganizationName(organization.name);
        setOrganizationDepartment(organization.department || "Clinical care");
        setOrganizationTimezone(organization.timezone || "Africa/Cairo");
      })
      .catch(() => undefined)
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => {
    getCurrentUser()
      .then((user) => setMfaEnabled(Boolean(user.mfa_enabled)))
      .catch((error: unknown) =>
        setActionError(error instanceof Error ? error.message : t("securityLoadFailed")),
      );
  }, []);
  useEffect(() => {
    if (activeSection !== "notifications") return;
    setNotificationsLoading(true);
    getNotifications()
      .then(setNotifications)
      .catch((error: unknown) =>
        setActionError(error instanceof Error ? error.message : t("notificationLoadFailed")),
      )
      .finally(() => setNotificationsLoading(false));
  }, [activeSection]);

  const loadRecoveryCodes = async () => {
    setActionError(null);
    try {
      const result = await regenerateMfaRecoveryCodes();
      setRecoveryCodes(result.recovery_codes);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : t("securityActionFailed"));
    }
  };

  const markRead = async (notification: NotificationItem) => {
    if (notification.read) return;
    setActionError(null);
    try {
      await markNotificationRead(notification.id);
      setNotifications((current) =>
        current.map((item) =>
          item.id === notification.id ? { ...item, read: true } : item,
        ),
      );
    } catch (error) {
      setActionError(error instanceof Error ? error.message : t("notificationActionFailed"));
    }
  };

  const settingsSections = [
    { id: "profile" as const, label: t("profile"), icon: <UserRound size={16} /> },
    { id: "preferences" as const, label: t("preferences"), icon: <SlidersHorizontal size={16} /> },
    { id: "security" as const, label: t("security"), icon: <ShieldCheck size={16} /> },
    { id: "notifications" as const, label: t("notificationsSetting"), icon: <Bell size={16} /> },
  ];
  return (
    <>
      <PageHeading
        eyebrow={t("workspace")}
        title={t("settingsTitle")}
        detail={t("settingsDetail")}
      />
      <div className="settings-layout">
        <nav className="panel settings-nav" aria-label={t("settingsTitle")}>
          {settingsSections.map((section) => (
            <button
              key={section.id}
              type="button"
              className={activeSection === section.id ? "active" : ""}
              aria-current={activeSection === section.id ? "page" : undefined}
              onClick={() => {
                setActiveSection(section.id);
                setActionError(null);
              }}
            >
              {section.icon} {section.label}
            </button>
          ))}
        </nav>
        <section className="panel settings-form" aria-live="polite">
          {activeSection === "profile" && (
            <>
              <PanelHeading title={t("profile")} detail={t("demoProfile")} />
              <label>
                {t("displayName")}
                <input value={doctorName} onChange={(event) => setDoctorName(event.target.value)} />
              </label>
              <label>
                {t("specialtyLabel")}
                <input defaultValue={t("internalMedicine")} />
              </label>
              <label>
                {t("organizationName")}
                <input value={organizationName} disabled={loading} onChange={(event) => setOrganizationName(event.target.value)} />
              </label>
              <label>
                Department
                <input value={organizationDepartment} disabled={loading} onChange={(event) => setOrganizationDepartment(event.target.value)} />
              </label>
              <label>
                Timezone
                <select value={organizationTimezone} disabled={loading} onChange={(event) => setOrganizationTimezone(event.target.value)}>
                  <option value="Africa/Cairo">Africa/Cairo</option>
                  <option value="UTC">UTC</option>
                  <option value="Europe/London">Europe/London</option>
                </select>
              </label>
              <div className="settings-actions">
                <button
                  className="primary-btn"
                  disabled={saving || !organizationName.trim()}
                  onClick={async () => {
                    setSaving(true);
                    try {
                      await completeOrganization(organizationName.trim(), organizationDepartment.trim() || "Clinical care", organizationTimezone);
                      window.dispatchEvent(new CustomEvent("careos:toast", { detail: t("savedChanges") }));
                    } catch (error) {
                      window.dispatchEvent(new CustomEvent("careos:toast", { detail: error instanceof Error ? error.message : "Could not save organization" }));
                    } finally {
                      setSaving(false);
                    }
                  }}
                >
                  {saving ? t("working") : t("saveChanges")}
                </button>
                <button className="danger-btn" onClick={onLogout}>
                  <LogOut size={15} /> {t("signOut")}
                </button>
              </div>
            </>
          )}
          {activeSection === "preferences" && (
            <>
              <PanelHeading title={t("preferences")} detail={t("preferencesDetail")} />
              <label>
                {t("languageSetting")}
                <select value={language} onChange={(event) => setLanguage(event.target.value as Language)}>
                  <option value="en">English</option>
                  <option value="ar">العربية</option>
                </select>
              </label>
              <div className="theme-setting">
                <span>{t("themeSetting")}</span>
                <div className="settings-theme-options">
                  <button type="button" className={theme === "light" ? "active" : ""} aria-pressed={theme === "light"} onClick={() => setTheme("light")}>
                    <Sun size={15} /> {t("lightMode")}
                  </button>
                  <button type="button" className={theme === "dark" ? "active" : ""} aria-pressed={theme === "dark"} onClick={() => setTheme("dark")}>
                    <Moon size={15} /> {t("darkMode")}
                  </button>
                </div>
              </div>
            </>
          )}
          {activeSection === "security" && (
            <>
              <PanelHeading title={t("security")} detail={t("securityDetail")} />
              <div className="settings-security-status">
                <span>{t("mfaStatus")}</span>
                <strong>{mfaEnabled === null ? t("working") : mfaEnabled ? t("mfaEnabled") : t("mfaDisabled")}</strong>
              </div>
              {mfaEnabled === false && !mfaSecret && (
                <div className="settings-section-content">
                  <p>{t("mfaSetupInstructions")}</p>
                  <button className="primary-btn" type="button" onClick={async () => {
                    setActionError(null);
                    try {
                      const result = await enrollMfa();
                      setMfaSecret(result.secret);
                    } catch (error) {
                      setActionError(error instanceof Error ? error.message : t("securityActionFailed"));
                    }
                  }}>
                    <ShieldCheck size={16} /> {t("enableMfa")}
                  </button>
                </div>
              )}
              {mfaSecret && (
                <div className="settings-section-content">
                  <p>{t("mfaSecretInstructions")}</p>
                  <code className="mfa-secret">{mfaSecret}</code>
                  <label>
                    {t("verificationCode")}
                    <input inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={mfaCode} onChange={(event) => setMfaCode(event.target.value.replace(/\D/g, "").slice(0, 6))} />
                  </label>
                  <button className="primary-btn" type="button" disabled={mfaCode.length !== 6} onClick={async () => {
                    setActionError(null);
                    try {
                      const result = await verifyMfa(mfaCode);
                      setMfaEnabled(result.enabled);
                      setRecoveryCodes(result.recovery_codes);
                      setMfaSecret("");
                      setMfaCode("");
                    } catch (error) {
                      setActionError(error instanceof Error ? error.message : t("securityActionFailed"));
                    }
                  }}>
                    <Check size={16} /> {t("verifyMfa")}
                  </button>
                </div>
              )}
              {mfaEnabled && (
                <div className="settings-section-content">
                  <button className="outline-btn" type="button" onClick={() => void loadRecoveryCodes()}>
                    {t("regenerateRecoveryCodes")}
                  </button>
                </div>
              )}
              {recoveryCodes.length > 0 && (
                <div className="recovery-codes" aria-live="polite">
                  <strong>{t("recoveryCodes")}</strong>
                  <p>{t("recoveryCodesWarning")}</p>
                  <ul>{recoveryCodes.map((code) => <li key={code}><code>{code}</code></li>)}</ul>
                </div>
              )}
            </>
          )}
          {activeSection === "notifications" && (
            <>
              <PanelHeading title={t("notificationsSetting")} detail={t("notificationsDetail")} />
              {notificationsLoading ? (
                <div className="loading-state">{t("working")}</div>
              ) : notifications.length ? (
                <div className="settings-notification-list">
                  {notifications.map((notification) => (
                    <article className={notification.read ? "read" : "unread"} key={notification.id}>
                      <div>
                        <strong>{notification.title}</strong>
                        <p>{notification.body}</p>
                        <time dateTime={notification.created_at}>{new Date(notification.created_at).toLocaleString(language === "ar" ? "ar-EG" : "en-US")}</time>
                      </div>
                      <button className="outline-btn" type="button" disabled={notification.read} onClick={() => void markRead(notification)}>
                        {notification.read ? t("read") : t("markRead")}
                      </button>
                    </article>
                  ))}
                </div>
              ) : (
                <div className="empty-state">{t("noNotifications")}</div>
              )}
            </>
          )}
          {actionError && <div className="inline-error settings-error" role="alert">{actionError}</div>}
        </section>
      </div>
    </>
  );
}
