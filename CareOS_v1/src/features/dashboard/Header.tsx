import { useEffect, useState } from "react";
import { Bell, ChevronRight, CircleHelp, Menu, Moon, Sun } from "lucide-react";
import {
  getNotifications,
  markNotificationRead,
} from "../../api/notifications";
import { GlobalChat } from "../chat/GlobalChat";
import { navItems } from "../workspace/navigation";
import type { AppView } from "../../app/routes";
import { viewFromLocation } from "../../app/routes";
import type { Language, TranslationKey } from "../../i18n";

type Theme = "light" | "dark";
type Translator = (key: TranslationKey) => string;

type HeaderProps = {
  view: AppView;
  language: Language;
  setLanguage: (language: Language) => void;
  setMobileNav: (open: boolean) => void;
  showNotifications: boolean;
  setShowNotifications: (show: boolean) => void;
  theme: Theme;
  setTheme: (theme: Theme) => void;
  onHelp: () => void;
  onAccount: () => void;
  t: Translator;
};

export function Header({
  view,
  language,
  setLanguage,
  setMobileNav,
  showNotifications,
  setShowNotifications,
  theme,
  setTheme,
  onHelp,
  onAccount,
  t,
}: HeaderProps) {
  const routeView = viewFromLocation();
  const displayedView =
    view === "portal" &&
    (routeView === "appointments" || routeView === "messages")
      ? routeView
      : view;
  const current = navItems.find((item) => item.id === displayedView) ?? navItems[0];
  const [notifications, setNotifications] = useState<
    Array<{ id: string; title: string; body: string; read: boolean }>
  >([]);

  useEffect(() => {
    getNotifications()
      .then((items) => setNotifications(items.slice(0, 5)))
      .catch(() => setNotifications([]));
  }, [showNotifications]);

  return (
    <header className="topbar">
      <button
        className="icon-btn menu-btn"
        onClick={() => setMobileNav(true)}
        aria-label={t("openNavigation")}
      >
        <Menu size={20} />
      </button>
      <div className="breadcrumb">
        <span>{t("workspace")}</span>
        <ChevronRight size={14} />
        <strong>{t(current.label)}</strong>
      </div>
      <div className="top-actions">
        <button
          type="button"
          className="glass-control-btn glass-icon-btn"
          aria-label={theme === "light" ? t("darkMode") : t("lightMode")}
          onClick={() => setTheme(theme === "light" ? "dark" : "light")}
        >
          {theme === "light" ? <Moon size={17} /> : <Sun size={17} />}
        </button>
        <button
          type="button"
          className="glass-control-btn glass-icon-btn"
          onClick={() => setLanguage(language === "en" ? "ar" : "en")}
          aria-label={
            language === "en" ? "Switch to Arabic" : "Switch to English"
          }
        >
          {language === "en" ? "AR" : "EN"}
        </button>
        <button
          type="button"
          className="icon-btn"
          aria-label={t("help")}
          onClick={onHelp}
        >
          <CircleHelp size={19} />
        </button>
        <div className="notification-wrap">
          <button
            className="icon-btn notification"
            aria-label={t("notificationLabel")}
            onClick={() => setShowNotifications(!showNotifications)}
          >
            <Bell size={19} />
            <i />
          </button>
          {showNotifications && (
            <div className="notification-popover">
              <strong>{t("notifications")}</strong>
              {notifications.length > 0 ? (
                notifications.map((notification) => (
                  <button
                    className="notification-item"
                    key={notification.id}
                    onClick={async () => {
                      if (!notification.read) {
                        await markNotificationRead(notification.id).catch(
                          () => undefined,
                        );
                        setNotifications((current) =>
                          current.map((item) =>
                            item.id === notification.id
                              ? { ...item, read: true }
                              : item,
                          ),
                        );
                      }
                    }}
                  >
                    <b>{notification.title}</b>
                    <br />
                    {notification.body}
                  </button>
                ))
              ) : (
                <p>
                  {language === "ar"
                    ? "لا توجد إشعارات جديدة"
                    : "No new notifications"}
                </p>
              )}
            </div>
          )}
        </div>
        <button
          className="top-avatar"
          onClick={onAccount}
          aria-label="Open account"
        >
          DR
        </button>
      </div>
    <GlobalChat t={t} />
    </header>
  );
}
