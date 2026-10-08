import {
  BarChart3,
  Building2,
  CalendarDays,
  Database,
  FileBarChart,
  FileText,
  LayoutDashboard,
  MessageCircle,
  ShieldCheck,
  Stethoscope,
  UserRound,
  Users,
  type LucideIcon,
} from "lucide-react";
import type { TranslationKey } from "../../i18n";
import type { AppView } from "../../app/routes";

export type Role =
  | "admin"
  | "doctor"
  | "nurse"
  | "receptionist"
  | "patient"
  | "hospital_director"
  | "it_admin"
  | "administrative_staff";

export type NavItem = {
  id: AppView;
  label: TranslationKey;
  icon: LucideIcon;
};

export const navItems: NavItem[] = [
  { id: "dashboard", label: "overview", icon: LayoutDashboard },
  { id: "patients", label: "patients", icon: Users },
  { id: "assistant", label: "assistant", icon: Stethoscope },
  { id: "notes", label: "notes", icon: FileText },
  { id: "documents", label: "documentation", icon: Database },
  { id: "appointments", label: "appointments", icon: CalendarDays },
  { id: "messages", label: "messages", icon: MessageCircle },
  { id: "portal", label: "patientPortal", icon: UserRound },
  { id: "analytics", label: "analytics", icon: BarChart3 },
  { id: "departments", label: "departments", icon: Building2 },
  { id: "reports", label: "reports", icon: FileBarChart },
  { id: "teamAudit", label: "teamAudit", icon: ShieldCheck },
];

export const roleNavMap: Record<Role, AppView[]> = {
  admin: ["dashboard", "patients", "documents", "appointments", "analytics", "departments", "reports", "teamAudit", "settings"],
  doctor: ["dashboard", "patients", "assistant", "notes", "documents", "appointments", "analytics", "messages"],
  nurse: ["dashboard", "patients", "notes", "documents", "appointments", "messages", "analytics"],
  receptionist: ["dashboard", "patients", "documents", "appointments", "messages", "analytics"],
  patient: ["portal", "appointments", "messages"],
  hospital_director: ["dashboard", "patients", "appointments", "analytics", "departments", "reports", "teamAudit", "settings"],
  it_admin: ["dashboard", "integrations", "teamAudit"],
  administrative_staff: ["dashboard", "patients", "appointments", "documents", "departments", "reports"],
};

export const rolePermissions: Record<Role, string[]> = {
  admin: ["dashboard.read", "patient.read", "patient.write", "appointment.read", "appointment.write", "clinical.note", "analytics.read", "team.read", "team.invite", "hospital.settings.view", "hospital.settings.manage"],
  doctor: ["dashboard.read", "patient.read", "patient.write", "appointment.read", "appointment.write", "clinical.note", "analytics.read"],
  nurse: ["dashboard.read", "patient.read", "patient.write", "appointment.read", "clinical.note"],
  receptionist: ["dashboard.read", "patient.read", "appointment.read", "appointment.write"],
  patient: ["dashboard.read", "patient.read", "appointment.read"],
  hospital_director: ["dashboard.read", "users.view", "hospital.view", "hospital.settings.view", "hospital.settings.manage", "departments.view", "reports.view", "analytics.view", "audit_logs.view", "team.read", "patients.view", "patients.search", "patient.read"],
  it_admin: ["dashboard.read", "users.view", "roles.view", "permissions.view", "sso.view", "sso.manage", "audit_logs.view"],
  administrative_staff: ["dashboard.read", "patients.search", "patients.demographics.view", "appointments.view", "appointments.create", "appointments.update", "checkin.view", "departments.view", "reports.operational.view"],
};

export const viewPermissions: Record<AppView, string[]> = {
  dashboard: ["dashboard.read"],
  patients: ["patient.read", "patients.view", "patients.demographics.view"],
  assistant: ["clinical.note", "clinical_notes.create"],
  notes: ["clinical.note", "clinical_notes.view"],
  documents: ["patient.read", "documents.view", "documents.create"],
  appointments: ["appointment.read", "appointments.view"],
  portal: ["patient.read", "patient.self.view"],
  analytics: ["analytics.read", "analytics.view"],
  messages: ["patient.read", "messages.self.view"],
  departments: ["team.read", "departments.view"],
  reports: ["analytics.read", "reports.view", "reports.operational.view"],
  settings: ["hospital.settings.view", "hospital.settings.manage"],
  integrations: ["dashboard.read", "sso.view", "sso.manage"],
  account: ["dashboard.read"],
  teamAudit: ["team.read", "users.view", "audit.read", "audit_logs.view"],
};

export const roleAccessWarning: Partial<Record<Role, string>> = {
  patient: "Patient accounts can view their care information and appointments, but not clinical admin or team management screens.",
  receptionist: "Receptionists can manage scheduling and patient check-in, but not clinical notes or staff audit screens.",
  nurse: "Nurses can access the patient queue and notes, but not staff-level admin or audit settings.",
};

const roleAliases: Record<string, Role> = {
  administrator: "admin",
  physician: "doctor",
  director: "hospital_director",
  it_administrator: "it_admin",
  staff: "administrative_staff",
};

export function normalizeFrontendRole(role: string | null | undefined): Role {
  const normalized = String(role || "").trim().toLowerCase().replaceAll(" ", "_");
  const canonical = roleAliases[normalized] ?? normalized;
  return (Object.hasOwn(roleNavMap, canonical) ? canonical : "receptionist") as Role;
}

export function permissionsForRole(role: Role): string[] {
  return rolePermissions[role] ?? [];
}

export function canAccessView(role: Role, view: AppView, permissions?: readonly string[]): boolean {
  if (view === "portal") return role === "patient" && (!permissions || permissions.length === 0);
  const required = viewPermissions[view] ?? ["dashboard.read"];
  const effectivePermissions = permissions && permissions.length > 0 ? permissions : permissionsForRole(role);
  return required.some((permission) => effectivePermissions.includes(permission));
}

export function firstAllowedView(role: Role, permissions?: readonly string[]): AppView {
  const candidates = roleNavMap[role] ?? roleNavMap.receptionist;
  return candidates.find((candidate) => canAccessView(role, candidate, permissions)) ?? "dashboard";
}
