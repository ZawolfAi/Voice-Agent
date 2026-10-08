import { useState } from "react";
import {
  ArrowUpRight,
  ChevronLeft,
  Eye,
  EyeOff,
  HeartPulse,
  Home,
  Stethoscope,
} from "lucide-react";
import type { Language, TranslationKey } from "../../i18n";
import type { Role } from "../workspace/navigation";

type Translator = (key: TranslationKey) => string;
type Payload = {
  mode: "signin" | "signup";
  email: string;
  password: string;
  fullName: string;
  organizationName: string;
  authMethod: "email" | "sso";
  role: Role;
  department?: string;
  project?: string;
};
export type DemoAccount = {
  role: Role;
  title: string;
  username: string;
  password: string;
};
export const demoAccounts: DemoAccount[] = [
  {
    role: "admin",
    title: "Admin",
    username: "admin.demo",
    password: "Admin@123",
  },
  {
    role: "doctor",
    title: "Doctor",
    username: "doctor.demo",
    password: "Doctor@123",
  },
  {
    role: "nurse",
    title: "Nurse",
    username: "nurse.demo",
    password: "Nurse@123",
  },
  {
    role: "receptionist",
    title: "Receptionist",
    username: "reception.demo",
    password: "Reception@123",
  },
  {
    role: "hospital_director",
    title: "Hospital Director",
    username: "director.demo",
    password: "Director@123",
  },
  {
    role: "it_admin",
    title: "IT Admin",
    username: "itadmin.demo",
    password: "ITAdmin@123",
  },
  {
    role: "administrative_staff",
    title: "Administrative Staff",
    username: "staff.demo",
    password: "Staff@123",
  },
  {
    role: "patient",
    title: "Patient",
    username: "patient.demo",
    password: "Patient@123",
  },
];
const demoRoleTranslation: Record<Role, TranslationKey> = {
  admin: "roleAdminLabel",
  doctor: "roleDoctorLabel",
  nurse: "roleNurseLabel",
  receptionist: "roleReceptionistLabel",
  hospital_director: "roleDirectorLabel",
  it_admin: "roleItAdminLabel",
  administrative_staff: "roleStaffLabel",
  patient: "rolePatientLabel",
};
type Props = {
  onLogin: (payload: Payload) => void;
  onDemoLogin?: (account: DemoAccount) => void;
  language: Language;
  setLanguage: (language: Language) => void;
  t: Translator;
  initialMode?: "signin" | "signup";
  initialAccessMethod?: "email" | "sso";
  onBackHome: () => void;
};

export function LoginRoute({
  onLogin,
  onDemoLogin,
  language,
  setLanguage,
  t,
  initialMode = "signin",
  initialAccessMethod = "email",
  onBackHome,
}: Props) {
  const [mode, setMode] = useState(initialMode);
  const [accessMethod, setAccessMethod] = useState(initialAccessMethod);
  const [role, setRole] = useState<Role>("doctor");
  const [email, setEmail] = useState("dr.rana@citycare.org");
  const [password, setPassword] = useState("password123");
  const [fullName, setFullName] = useState("");
  const [organizationName, setOrganizationName] = useState("CityCare");
  const [department, setDepartment] = useState("General Medicine");
  const [project, setProject] = useState("Outpatient");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [showRecovery, setShowRecovery] = useState(false);
  const [recoveryEmail, setRecoveryEmail] = useState(email);
  const [recoverySent, setRecoverySent] = useState(false);
  const isSignUp = mode === "signup";
  const demoRoleLabel = (demoRole: Role) => t(demoRoleTranslation[demoRole]);

  const handleRecoverySubmit = () => {
    setRecoverySent(true);
  };

  return (
    <div className="login-screen" dir={language === "ar" ? "rtl" : "ltr"}>
      <div className="login-art">
        <button
          className="login-home-button"
          onClick={onBackHome}
          aria-label={t("backToHome")}
        >
          <Home size={16} />
        </button>
        <div className="login-brand">
          <div className="brand-mark">
            <HeartPulse size={19} />
          </div>
          <span>
            care<span>os</span>
          </span>
        </div>
        <div className="login-quote">
          <span>{t("loginEyebrow")}</span>
          <h1>
            {t("loginQuoteFirst")}
            <br />
            <em>{t("loginQuoteSecond")}</em>
          </h1>
          <p>{t("loginArtDetail")}</p>
        </div>
      </div>

      <div className="login-form-wrap">
        <div className="login-mobile-header" aria-hidden="true" />

        {showRecovery ? (
          <div className="login-form recovery-form">
            <div className="login-form-top recovery-top">
              <button
                className="back-link"
                onClick={() => {
                  setShowRecovery(false);
                  setRecoverySent(false);
                }}
              >
                <ChevronLeft size={14} /> {t("backToSignIn")}
              </button>
            </div>

            <div className="eyebrow">{t("accountRecovery")}</div>
            <h2>{t("resetPassword")}</h2>
            <p>
              {t("resetLinkDetail")}
            </p>

            <label>
              {t("emailAddress")}
              <input
                type="email"
                value={recoveryEmail}
                onChange={(event) => setRecoveryEmail(event.target.value)}
                placeholder="name@citycare.org"
              />
            </label>

            {recoverySent && (
              <div className="recovery-success">
                {t("resetLinkSent")} {recoveryEmail}.
              </div>
            )}

            <button
              className="primary-btn login-button"
              onClick={handleRecoverySubmit}
            >
              {t("sendResetLink")} <ArrowUpRight size={16} />
            </button>
          </div>
        ) : (
          <div className="login-form">
            <div className="login-form-top">
              <button className="back-link" onClick={onBackHome}>
                <ChevronLeft size={14} />{" "}
                {language === "ar" ? "العودة للرئيسية" : "Back to Home"}
              </button>
              <button
                className="glass-control-btn"
                onClick={() => setLanguage(language === "en" ? "ar" : "en")}
                aria-label={
                  language === "en" ? "Switch to Arabic" : "Switch to English"
                }
              >
                {language === "en" ? "AR" : "EN"}
              </button>
            </div>

            <div className="auth-tabs" role="tablist">
              <button
                role="tab"
                aria-selected={!isSignUp}
                className={!isSignUp ? "active" : ""}
                onClick={() => {
                  setMode("signin");
                  setAccessMethod("email");
                }}
              >
                {t("signIn")}
              </button>
              <button
                role="tab"
                aria-selected={isSignUp}
                className={isSignUp ? "active" : ""}
                onClick={() => {
                  setMode("signup");
                  setAccessMethod("email");
                }}
              >
                {t("createAccount")}
              </button>
            </div>

            {!isSignUp && (
              <>
                <div className="mobile-signin-label">{t("signInWith")}</div>
                <div className="access-method-panel">
                  <button
                    className={`access-method-button ${accessMethod === "email" ? "active" : ""}`}
                    onClick={() => setAccessMethod("email")}
                  >
                    {t("emailPassword")}
                  </button>
                  <button
                    className={`access-method-button ${accessMethod === "sso" ? "active" : ""}`}
                    onClick={() => setAccessMethod("sso")}
                  >
                    {t("hospitalSso")}
                  </button>
                </div>
              </>
            )}

            <div className="eyebrow">
              {isSignUp ? t("createAccountEyebrow") : t("welcome")}
            </div>
            <h2>{isSignUp ? t("createAccount") : t("signIn")}</h2>
            <p>{isSignUp ? t("createAccountDetail") : t("signInDetail")}</p>

            {!isSignUp && accessMethod === "sso" ? (
              <div className="sso-provider-panel">
                <div className="sso-provider-title">
                  <Stethoscope size={17} /> {t("hospitalSso")}
                </div>
                <div className="sso-provider-detail">
                  {t("ssoProviderDetail")}
                </div>
                <div className="sso-provider-detail">
                  {t("hospitalSsoRouteDetail")}
                </div>
                <button
                  className="primary-btn login-button"
                  onClick={() =>
                    onLogin({
                      mode: "signin",
                      email: "dr.rana@citycare.org",
                      password: "password123",
                      fullName: "Dr. Rana Samir",
                      organizationName: "CityCare",
                      authMethod: "sso",
                      role,
                    })
                  }
                >
                  {t("continueWithSso")} <ArrowUpRight size={16} />
                </button>
              </div>
            ) : (
              <>
                {isSignUp && (
                  <>
                    <label>
                      {t("fullName")}
                      <input
                        value={fullName}
                        onChange={(event) => setFullName(event.target.value)}
                      />
                    </label>
                    <label>
                      {t("organizationName")}
                      <input
                        value={organizationName}
                        onChange={(event) =>
                          setOrganizationName(event.target.value)
                        }
                      />
                    </label>
                  </>
                )}

                {accessMethod === "email" && (
                  <>
                    <label>
                      {t("email")}
                      <input
                        type="email"
                        value={email}
                        onChange={(event) => setEmail(event.target.value)}
                      />
                    </label>

                    <label>
                      {t("password")}
                      <div className="password-input-wrap">
                        <input
                          type={showPassword ? "text" : "password"}
                          value={password}
                          onChange={(event) => setPassword(event.target.value)}
                        />
                        <button
                          type="button"
                          className="password-visibility-button"
                          onClick={() => setShowPassword((current) => !current)}
                          aria-label={
                            showPassword ? t("hidePassword") : t("showPassword")
                          }
                          title={
                            showPassword ? t("hidePassword") : t("showPassword")
                          }
                        >
                          {showPassword ? (
                            <EyeOff size={16} />
                          ) : (
                            <Eye size={16} />
                          )}
                        </button>
                      </div>
                    </label>

                    {isSignUp && (
                      <label>
                        {t("confirmPassword")}
                        <div className="password-input-wrap">
                          <input
                            type={showConfirmPassword ? "text" : "password"}
                            value={confirmPassword}
                            onChange={(event) =>
                              setConfirmPassword(event.target.value)
                            }
                          />
                          <button
                            type="button"
                            className="password-visibility-button"
                            onClick={() =>
                              setShowConfirmPassword((current) => !current)
                            }
                            aria-label={
                              showConfirmPassword
                                ? t("hideConfirmPassword")
                                : t("showConfirmPassword")
                            }
                            title={
                              showConfirmPassword
                                ? t("hideConfirmPassword")
                                : t("showConfirmPassword")
                            }
                          >
                            {showConfirmPassword ? (
                              <EyeOff size={16} />
                            ) : (
                              <Eye size={16} />
                            )}
                          </button>
                        </div>
                      </label>
                    )}

                    <a
                      href="#"
                      className="forgot-password"
                      onClick={(event) => {
                        event.preventDefault();
                        setShowRecovery(true);
                      }}
                    >
                      {t("forgotPassword")}
                    </a>
                    <button
                      className="primary-btn login-button"
                      disabled={
                        isSignUp && (!fullName || password !== confirmPassword)
                      }
                      onClick={() =>
                        onLogin({
                          mode,
                          email,
                          password,
                          fullName,
                          organizationName,
                          authMethod: "email",
                          role,
                          department,
                          project,
                        })
                      }
                    >
                      {isSignUp ? t("createWorkspace") : t("signIn")}{" "}
                      <ArrowUpRight size={16} />
                    </button>
                  </>
                )}
              </>
            )}
            {import.meta.env.DEV && onDemoLogin && !isSignUp && (
              <div className="demo-login-panel">
                <div className="eyebrow">{t("demoAccountsTitle")}</div>
                <p>
                  {t("demoAccountsDetail")}
                </p>
                <div className="demo-login-grid">
                  {demoAccounts.map((account) => (
                    <article className="demo-account-card" key={account.role}>
                      <strong>{demoRoleLabel(account.role)}</strong>
                      <span>{t("usernameLabel")}: {account.username}</span>
                      <span>{t("passwordLabel")}: {account.password}</span>
                      <button
                        type="button"
                        className="outline-btn"
                        onClick={() => onDemoLogin(account)}
                      >
                        {t("loginAs")} {demoRoleLabel(account.role)}
                      </button>
                    </article>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
