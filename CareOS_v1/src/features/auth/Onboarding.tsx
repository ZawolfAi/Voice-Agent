import { useState } from "react";
import { ArrowUpRight, HeartPulse } from "lucide-react";
import type { Language, TranslationKey } from "../../i18n";

type Translator = (key: TranslationKey) => string;

type OnboardingProps = {
  language: Language;
  setLanguage: (language: Language) => void;
  complete: (organizationName: string) => void;
  t: Translator;
  onBack?: () => void;
};

export function Onboarding({ language, setLanguage, complete, t, onBack }: OnboardingProps) {
  const [organizationName, setOrganizationName] = useState("");

  return (
    <div className="onboarding-screen" dir={language === "ar" ? "rtl" : "ltr"}>
      <div className="onboarding-card">
        <div className="brand"><div className="brand-mark"><HeartPulse size={19} /></div><span>care<span>os</span></span></div>
        <div className="onboarding-progress"><span style={{ width: "33.333%" }} /></div>
        <div className="eyebrow">{t("onboardingStepOne")}</div>
        <h1>{t("onboardingWelcome")}</h1>
        <p>{t("onboardingWelcomeDetail")}</p>
        <label>{t("organizationName")}<input value={organizationName} onChange={(event) => setOrganizationName(event.target.value)} placeholder={t("organizationPlaceholder")} /></label>
        <div className="onboarding-actions">
          {onBack && <button className="outline-btn onboarding-back-button" onClick={onBack}>{t("back")}</button>}
          <button className="outline-btn" onClick={() => setLanguage(language === "en" ? "ar" : "en")}>{language === "en" ? "العربية" : "English"}</button>
          <button className="primary-btn" disabled={organizationName.trim().length < 2} onClick={() => complete(organizationName)}>{t("continue")} <ArrowUpRight size={15} /></button>
        </div>
      </div>
    </div>
  );
}
