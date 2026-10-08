import { LogOut, ShieldCheck, UserRound } from "lucide-react";
import { PageHeading } from "../../components/PageHeading";
import type { TranslationKey } from "../../i18n";
import type { Role } from "../workspace/navigation";

type Translator = (key: TranslationKey) => string;
type AccountPageProps = {
  doctorName: string;
  role: Role;
  department: string;
  project: string;
  onLogout: () => Promise<void>;
  t: Translator;
};

export function AccountPage({
  doctorName,
  role,
  department,
  project,
  onLogout,
  t,
}: AccountPageProps) {
  const roleKeys: Partial<Record<Role, TranslationKey>> = {
    admin: "roleAdminLabel",
    doctor: "roleDoctorLabel",
    nurse: "roleNurseLabel",
    receptionist: "roleReceptionistLabel",
    hospital_director: "roleDirectorLabel",
    it_admin: "roleItAdminLabel",
    administrative_staff: "roleStaffLabel",
    patient: "rolePatientLabel",
  };
  const roleLabel = roleKeys[role] ? t(roleKeys[role]!) : role.replaceAll("_", " ");
  return (
    <>
      <PageHeading
        eyebrow={t("accountEyebrow")}
        title={doctorName}
        detail={t("accountDetail")}
      />
      <section className="account-grid">
        <div className="panel account-profile-panel">
          <div className="account-avatar">
            <UserRound size={30} />
          </div>
          <div>
            <h2>{doctorName}</h2>
            <p>{roleLabel}</p>
          </div>
          <div className="account-detail-list">
            <div>
              <span>{t("department")}</span>
              <strong>{department}</strong>
            </div>
            <div>
              <span>{t("projectLabel")}</span>
              <strong>{project}</strong>
            </div>
            <div>
              <span>{t("workspaceLabel")}</span>
              <strong>{t("demoHospitalName")}</strong>
            </div>
          </div>
        </div>
        <div className="panel account-security-panel">
          <div className="panel-heading">
            <div>
              <h2>{t("accountSecurity")}</h2>
              <p>{t("reviewSessionAccess")}</p>
            </div>
            <ShieldCheck size={22} />
          </div>
          <div className="account-security-row">
            <span>{t("roleAccess")}</span>
            <strong>{roleLabel}</strong>
          </div>
          <div className="account-security-row">
            <span>{t("sessionLabel")}</span>
            <strong>{t("activeStatus")}</strong>
          </div>
          <button
            className="outline-btn account-logout"
            onClick={() => void onLogout()}
          >
            <LogOut size={16} /> {t("signOut")}
          </button>
        </div>
      </section>
    </>
  );
}
