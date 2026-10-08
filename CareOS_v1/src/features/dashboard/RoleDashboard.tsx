import { useEffect, useState, type ReactNode } from "react";
import {
  Activity,
  ArrowRight,
  CalendarDays,
  Clock3,
  FileText,
  Plus,
  ShieldCheck,
  Users,
} from "lucide-react";
import {
  getAuditEvents,
  getDashboard,
  getTeam,
  type AuthUser,
  type DashboardContract,
} from "../../api";
import { PageHeading } from "../../components/PageHeading";
import type { TranslationKey } from "../../i18n";
import type { AppView } from "../../app/routes";
import type { Role } from "../workspace/navigation";

type Translator = (key: TranslationKey) => string;
type Props = {
  onNavigate: (view: AppView) => void;
  doctorName: string;
  t: Translator;
  role: Role;
  department: string;
  project: string;
};
type AuditEvent = { action: string; resource: string; created_at: string };

export function RoleDashboard({
  onNavigate,
  doctorName,
  t,
  role,
  department,
  project,
}: Props) {
  const [data, setData] = useState<DashboardContract | null>(null);
  const [team, setTeam] = useState<AuthUser[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const isItAdmin = role === "it_admin";
  const isDirector = role === "hospital_director";
  const isAdmin = role === "admin";
  const isClinical = role === "doctor" || role === "nurse";
  const isOperations =
    role === "receptionist" || role === "administrative_staff";
  const canSeeTeam = isAdmin || isDirector || isItAdmin;
  const locale = t("workspace") === "مساحة العمل" ? "ar-EG" : "en-US";
  const translateRole = (memberRole: string) => {
    const roleKeys: Record<string, TranslationKey> = {
      admin: "roleAdminLabel",
      doctor: "roleDoctorLabel",
      physician: "roleDoctorLabel",
      nurse: "roleNurseLabel",
      receptionist: "roleReceptionistLabel",
      hospital_director: "roleDirectorLabel",
      it_admin: "roleItAdminLabel",
      administrative_staff: "roleStaffLabel",
      patient: "rolePatientLabel",
    };
    const key = roleKeys[memberRole];
    return key ? t(key) : memberRole.replaceAll("_", " ");
  };
  const translateAppointmentStatus = (status: string) => {
    const statusKeys: Record<string, TranslationKey> = {
      confirmed: "confirmed",
      arrived: "arrived",
      pending: "pending",
      cancelled: "cancelled",
    };
    const key = statusKeys[status.toLowerCase()];
    return key ? t(key) : status;
  };

  useEffect(() => {
    const requests: Array<Promise<void>> = [];
    if (!isItAdmin)
      requests.push(
        getDashboard()
          .then(setData)
          .catch(() => setData(null)),
      );
    if (canSeeTeam)
      requests.push(
        getTeam()
          .then(setTeam)
          .catch(() => setTeam([])),
      );
    if (isAdmin || isDirector || isItAdmin)
      requests.push(
        getAuditEvents()
          .then(setAuditEvents)
          .catch(() => setAuditEvents([])),
      );
    void Promise.all(requests);
  }, [canSeeTeam, isAdmin, isDirector, isItAdmin]);

  if (isItAdmin) {
    return (
      <>
        <PageHeading
          eyebrow={t("itAdministrationLabel")}
          title={`${t("morning")}, ${doctorName}`}
          detail={t("identityAccessSecurity")}
        />
        <section className="stat-grid">
          <StatCard
            icon={<Users />}
            label={t("activeUsersLabel")}
            value={team.length}
            tone="blue"
          />
          <StatCard
            icon={<ShieldCheck />}
            label={t("auditEventsLabel")}
            value={auditEvents.length}
            tone="rose"
          />
          <StatCard
            icon={<Activity />}
            label={t("securityStatusLabel")}
            value={t("operationalStatus")}
            tone="green"
          />
        </section>
        <div className="dashboard-grid">
          <DashboardPanel
            title={t("recentAccessEvents")}
            detail={t("organizationSecurityActivity")}
          >
            {auditEvents.slice(0, 5).map((event) => (
              <Record
                key={`${event.created_at}-${event.resource}`}
                icon={<ShieldCheck size={16} />}
                title={event.action}
                detail={event.resource}
                meta={new Date(event.created_at).toLocaleString()}
              />
            ))}
            {auditEvents.length === 0 && (
              <div className="empty-state">{t("dashboardNoAudit")}</div>
            )}
          </DashboardPanel>
          <DashboardPanel
            title={t("userAdministration")}
            detail={t("manageAccountsRolesInvitations")}
          >
            <Record
              icon={<Users size={16} />}
              title={t("usersLabel")}
              detail={`${team.length} ${t("organizationUsers")}`}
              action={
                <button
                  className="text-btn"
                  onClick={() => onNavigate("teamAudit")}
                >
                  {t("open")}
                </button>
              }
            />
          </DashboardPanel>
        </div>
      </>
    );
  }

  const patients = data?.patient_count ?? 0;
  const appointments = data?.upcoming_appointments?.length ?? 0;
  const followups = data?.followups?.length ?? 0;
  const title = isDirector
    ? t("hospitalOverview")
    : isOperations
      ? t("operationsOverview")
      : isAdmin
        ? t("workspaceOverview")
        : `${t("morning")}, ${doctorName}`;
  const stats = isDirector
    ? [
        {
          icon: <Users />,
          label: t("activePatients"),
          value: patients,
          tone: "blue",
        },
        {
          icon: <CalendarDays />,
          label: t("appointments"),
          value: appointments,
          tone: "green",
        },
        {
          icon: <Users />,
          label: t("staffMembers"),
          value: team.length,
          tone: "rose",
        },
      ]
    : isAdmin
      ? [
          {
            icon: <Users />,
            label: t("activePatients"),
            value: patients,
            tone: "blue",
          },
          {
            icon: <CalendarDays />,
            label: t("appointments"),
            value: appointments,
            tone: "green",
          },
          {
            icon: <Users />,
            label: t("teamMembersLabel"),
            value: team.length,
            tone: "rose",
          },
        ]
      : isOperations
        ? [
            {
              icon: <CalendarDays />,
              label: t("appointments"),
              value: appointments,
              tone: "green",
            },
            {
              icon: <Users />,
              label: t("activePatients"),
              value: patients,
              tone: "blue",
            },
          ]
        : [
            {
              icon: <Users />,
              label: t("activePatients"),
              value: patients,
              tone: "blue",
            },
            {
              icon: <CalendarDays />,
              label: t("appointments"),
              value: appointments,
              tone: "green",
            },
            {
              icon: <Clock3 />,
              label: t("followUps"),
              value: followups,
              tone: "orange",
            },
            ...(role === "doctor"
              ? [
                  {
                    icon: <Activity />,
                    label: t("aiReviewRate"),
                    value: t("notAvailable"),
                    tone: "rose",
                  },
                ]
              : []),
          ];

  return (
    <>
      <PageHeading
        eyebrow={isDirector ? t("directorOverview") : t("todayOverview")}
        title={title}
        detail={
          isDirector || isOperations
            ? t("organizationScopedMetrics")
            : t("todayOverview")
        }
        action={
          !isDirector && (
            <button
              className="primary-btn"
              onClick={() => onNavigate("appointments")}
            >
              <Plus size={16} /> {t("newAppointment")}
            </button>
          )
        }
      />
      <div className="scope-strip">
        <span>{t("department")}: {department === "General Medicine" ? t("internalMedicine") : department}</span>
        <span>{t("projectLabel")}: {project === "Outpatient" ? t("outpatient") : project}</span>
      </div>
      <section className="stat-grid">
        {stats.map((stat) => (
          <StatCard
            key={stat.label}
            icon={stat.icon}
            label={stat.label}
            value={stat.value}
            tone={stat.tone}
          />
        ))}
      </section>
      <div className="dashboard-grid">
        <DashboardPanel
          title={t("upcomingAppointments")}
          detail={t("scheduleDetail")}
          action={
            <button
              className="text-btn"
              onClick={() => onNavigate("appointments")}
            >
              {t("viewAll")} <ArrowRight size={14} />
            </button>
          }
        >
          {(data?.upcoming_appointments ?? [])
            .slice(0, 4)
            .map((appointment) => (
              <Record
                key={appointment.id}
                icon={<CalendarDays size={16} />}
                title={new Date(appointment.starts_at).toLocaleTimeString(locale, {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
                detail={appointment.reason}
                meta={translateAppointmentStatus(appointment.status)}
              />
            ))}
          {!data?.upcoming_appointments?.length && (
            <div className="empty-state">{t("noAppointments")}</div>
          )}
        </DashboardPanel>
        {canSeeTeam ? (
          <DashboardPanel
            title={isDirector ? t("staffAndDepartments") : t("teamAndAudit")}
            detail={t("organizationAdministration")}
          >
            {team.slice(0, 5).map((member) => (
              <Record
                key={member.id}
                icon={<Users size={16} />}
                title={member.full_name}
                detail={translateRole(member.role)}
              />
            ))}
            <button
              className="text-btn"
              onClick={() => onNavigate("teamAudit")}
            >
              {t("open")}
            </button>
          </DashboardPanel>
        ) : (
          <DashboardPanel
            title={isClinical ? t("clinicalWorkspace") : t("frontDeskWorkflow")}
            detail={isClinical ? t("reviewAi") : t("scheduleDetail")}
          >
            <Record
              icon={
                isClinical ? <FileText size={16} /> : <CalendarDays size={16} />
              }
              title={isClinical ? t("clinicalNotes") : t("appointments")}
              detail={
                isClinical
                  ? t("createReviewDocumentation")
                  : t("manageDailyPatientSchedule")
              }
              action={
                <button
                  className="text-btn"
                  onClick={() =>
                    onNavigate(isClinical ? "notes" : "appointments")
                  }
                >
                  {t("open")}
                </button>
              }
            />
            {isClinical && role === "doctor" && (
              <Record
                icon={<Activity size={16} />}
                title={t("assistant")}
                detail={t("assistantReady")}
                action={
                  <button
                    className="text-btn"
                    onClick={() => onNavigate("assistant")}
                  >
                    {t("open")}
                  </button>
                }
              />
            )}
          </DashboardPanel>
        )}
      </div>
    </>
  );
}

function StatCard({
  icon,
  label,
  value,
  tone,
}: {
  icon: ReactNode;
  label: string;
  value: number | string;
  tone: string;
}) {
  return (
    <div className="stat-card">
      <div className={`stat-icon ${tone}`}>{icon}</div>
      <span className="stat-label">{label}</span>
      <strong className="stat-value">{value}</strong>
    </div>
  );
}
function DashboardPanel({
  title,
  detail,
  action,
  children,
}: {
  title: string;
  detail: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>{title}</h2>
          <p>{detail}</p>
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
function Record({
  icon,
  title,
  detail,
  meta,
  action,
}: {
  icon: ReactNode;
  title: string;
  detail: string;
  meta?: string;
  action?: ReactNode;
}) {
  return (
    <div className="record-item">
      <div className="record-date">{icon}</div>
      <div>
        <strong>{title}</strong>
        <p>{detail}</p>
      </div>
      {meta && <span className="status confirmed">{meta}</span>}
      {action}
    </div>
  );
}
