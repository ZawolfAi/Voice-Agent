import { portalRequest, request } from "./api/client";
import { demoAccounts } from "./features/auth/LoginRoute";

export type AuthUser = {
  id: string;
  organization_id: string;
  workspace_id?: string | null;
  department?: string;
  project?: string;
  email: string;
  full_name: string;
  role: string;
  permissions?: string[];
  onboarding_complete: boolean;
  mfa_enabled?: boolean;
};

export type Organization = {
  id: string;
  name: string;
  department: string;
  timezone: string;
  onboarding_complete?: boolean;
};

export type Workspace = {
  id: string;
  organization_id: string;
  name: string;
  department: string;
  timezone: string;
  onboarding_complete?: boolean;
};

export type DashboardContract = {
  patient_count: number;
  upcoming_appointments: ApiAppointment[];
  followups: ApiPatient[];
  kpi?: Record<string, number | string>;
};

export type SSOStartResponse = {
  provider: string;
  redirect_url: string;
  state: string;
  nonce: string;
};

export type ApiPatient = {
  id: string; patient_code: string; medical_record_number: string; given_name: string; family_name: string;
  department?: string; project?: string;
  date_of_birth: string; gender: string; condition: string; care_status: string;
};
export type SystemStatus = { app: string; environment: string; deployment: string; metrics_enabled: boolean; sso_ready: boolean; providers?: Record<string, { configured: boolean; provider?: string; backend?: string }> };
export type ApiAppointment = { id: string; patient_id: string; starts_at: string; reason: string; status: string; reminder_status: string };
export type ApiNote = { id: string; patient_id: string; encounter_id?: string | null; body: string; ai_draft: string | null; status: string; signed_at: string | null };
export type ApiEncounter = { id: string; organization_id: string; patient_id: string; clinician_id: string; encounter_type: string; status: string; started_at: string; ended_at: string | null };
export type ApiTranscript = { id: string; encounter_id: string; audio_file_id: string; provider: string; language: string; dialect: string; transcript_text: string | null; status: string; confidence: number | null; error_code: string | null; created_at: string; completed_at: string | null };
export type ApiMessage = {
  id: string;
  patient_id: string;
  subject: string;
  body: string;
  sender_type: string;
  direction: string;
  read: boolean;
  created_at: string;
};
export type PortalPatientResponse = {
  patient: ApiPatient;
  messages: Array<{ id: string; subject: string; body: string; direction: string; sender_type: string; read: boolean; created_at: string }>;
  documents: Array<{ id: string; filename: string; ocr_status: string; extracted_text?: string | null; created_at: string }>;
  latest_status: string;
};
export type PortalOverview = {
  patient: ApiPatient;
  appointments: ApiAppointment[];
  messages: ApiMessage[];
  documents: Array<{ id: string; filename: string; ocr_status: string; created_at: string; download_url?: string | null }>;
};
export type PatientDetailResponse = ApiPatient & {
  notes: Array<{ id: string; body: string; ai_draft: string | null; status: string; created_at?: string }>;
  documents: Array<{ id: string; filename: string; ocr_status: string; extracted_text?: string | null }>;
};
export type AnalyticsResponse = {
  overview: { patients: number; appointments: number; follow_up_due: number; today_count: number };
  department_breakdown: Array<{ department: string; count: number }>;
  alerts: Array<{ type: string; count: number; message: string }>;
};
export type ReportsResponse = Array<{ id: string; name: string; category: string; generated_at: string; metrics: Record<string, string | number> }>;
export type TaskItem = {
  id: string;
  patient_id: string;
  title: string;
  description: string;
  assignee: string;
  priority: string;
  status: string;
  due_at: string | null;
  created_at: string;
};
export type CarePlanItem = {
  id: string;
  patient_id: string;
  title: string;
  summary: string;
  status: string;
  goals: string[];
  created_at: string;
};
export type DepartmentMetricsResponse = {
  departments: Array<{ department: string; count: number }>;
  generated_at: string;
};
export type DocumentUploadResponse = {
  id: string;
  filename: string;
  ocr_status: string;
  extracted_text?: string | null;
  storage_key?: string;
  download_url?: string;
  review_status?: string;
};

type AuthResponse = { access_token: string; token_type: string; user: AuthUser };
export type DemoAuthResponse = { demo_role: string; access_token?: string; portal_access_token?: string; token_type?: string; user: AuthUser | PortalAuthResponse["user"] };
export type PortalAuthResponse = { access_token: string; token_type: string; user: { id: string; patient_id: string; email: string; full_name: string; role: string } };

const DEMO_MODE_KEY = "careos-demo-mode";
const DEMO_USER_KEY = "careos-demo-user";

function buildDemoUser(accountRole: string): AuthUser {
  const role = accountRole === "patient" ? "patient" : accountRole;
  const baseUser: AuthUser = {
    id: `demo-${role}`,
    organization_id: "demo-org",
    workspace_id: "demo-workspace",
    department: "General Medicine",
    project: "Demo workspace",
    email: `${role === "patient" ? "patient.demo" : `${role}.demo`}@careos.demo`,
    full_name: role === "patient" ? "Mariam Hassan" : `${role === "doctor" ? "Dr. Rana Samir" : role.charAt(0).toUpperCase() + role.slice(1).replace(/_/g, " ")}`,
    role,
    permissions: role === "patient" ? [] : ["dashboard", "patients", "appointments", "messages", "analytics"],
    onboarding_complete: true,
    mfa_enabled: false,
  };

  if (role === "admin") {
    baseUser.permissions = ["dashboard", "patients", "appointments", "messages", "analytics", "settings", "teamAudit", "integrations"];
  }
  if (role === "doctor") {
    baseUser.permissions = ["dashboard", "patients", "notes", "assistant", "appointments", "messages", "analytics"];
  }
  if (role === "nurse") {
    baseUser.permissions = ["dashboard", "patients", "notes", "appointments", "messages"];
  }
  if (role === "receptionist") {
    baseUser.permissions = ["dashboard", "appointments", "messages", "analytics"];
  }
  if (role === "hospital_director") {
    baseUser.permissions = ["dashboard", "patients", "appointments", "analytics", "reports"];
  }
  if (role === "it_admin") {
    baseUser.permissions = ["dashboard", "integrations", "settings", "teamAudit"];
  }
  if (role === "administrative_staff") {
    baseUser.permissions = ["dashboard", "appointments", "messages"];
  }

  return baseUser;
}

function getDemoUser(): AuthUser | null {
  const raw = localStorage.getItem(DEMO_USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

function saveDemoSession(user: AuthUser, isPortal = false): void {
  localStorage.setItem(DEMO_MODE_KEY, "true");
  localStorage.setItem(DEMO_USER_KEY, JSON.stringify(user));
  if (isPortal) {
    localStorage.setItem("careos-portal-token", "demo-portal-token");
    localStorage.removeItem("careos-access-token");
    return;
  }
  localStorage.setItem("careos-access-token", "demo-staff-token");
  localStorage.removeItem("careos-portal-token");
}

function getDemoAccountByRole(role: string) {
  return demoAccounts.find((account) => account.role === role) ?? demoAccounts[0];
}

function isDemoRequestFailure(error: unknown): boolean {
  if (error instanceof Error) {
    const message = error.message.toLowerCase();
    if (message.includes("failed to fetch") || message.includes("network") || message.includes("offline") || message.includes("load failed")) {
      return true;
    }
  }
  return false;
}

function storeStaffToken(token: string): void {
  localStorage.setItem("careos-access-token", token);
  localStorage.removeItem("careos-portal-token");
  localStorage.setItem(DEMO_MODE_KEY, "false");
}

function storePortalToken(token: string): void {
  localStorage.setItem("careos-portal-token", token);
  localStorage.removeItem("careos-access-token");
  localStorage.setItem(DEMO_MODE_KEY, "false");
}

export async function register(email: string, password: string, fullName: string, organizationName: string, department = "", project = ""): Promise<AuthResponse> {
  const result = await request<AuthResponse>("/auth/register", { method: "POST", body: JSON.stringify({ email, password, full_name: fullName, organization_name: organizationName, department, project }) });
  storeStaffToken(result.access_token);
  return result;
}

export async function login(email: string, password: string): Promise<AuthResponse> {
  const result = await request<AuthResponse>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
  storeStaffToken(result.access_token);
  return result;
}

export async function demoLogin(role: string, username: string, password: string): Promise<DemoAuthResponse> {
  try {
    const result = await request<DemoAuthResponse>("/auth/demo-login", { method: "POST", body: JSON.stringify({ role, username, password }) });
    if (result.portal_access_token) {
      localStorage.setItem("careos-portal-token", result.portal_access_token);
      localStorage.removeItem("careos-access-token");
    } else if (result.access_token) {
      localStorage.setItem("careos-access-token", result.access_token);
      localStorage.removeItem("careos-portal-token");
    }
    return result;
  } catch (error) {
    if (!isDemoRequestFailure(error)) {
      throw error;
    }

    const account = getDemoAccountByRole(role);
    const normalizedRole = role === "patient" ? "patient" : (account?.role ?? role);
    const isPortalAccount = normalizedRole === "patient";
    const user = buildDemoUser(normalizedRole);

    if (username !== account?.username || password !== account?.password) {
      throw new Error("Demo credentials do not match the offline account list.");
    }

    saveDemoSession(user, isPortalAccount);

    return {
      demo_role: normalizedRole,
      access_token: isPortalAccount ? undefined : "demo-staff-token",
      portal_access_token: isPortalAccount ? "demo-portal-token" : undefined,
      token_type: "demo",
      user: isPortalAccount ? { id: user.id, patient_id: user.id, email: user.email, full_name: user.full_name, role: user.role } : user,
    };
  }
}

export async function loginWithSso(provider = "hospital_sso", email = "", password = ""): Promise<AuthResponse> {
  const result = await request<AuthResponse>("/auth/sso", {
    method: "POST",
    body: JSON.stringify({ provider, email, password }),
  });
  storeStaffToken(result.access_token);
  return result;
}

export async function startHospitalSso(provider = "hospital_sso", email?: string): Promise<SSOStartResponse> {
  return request<SSOStartResponse>("/auth/sso/start", {
    method: "POST",
    body: JSON.stringify({ provider, email, redirect_uri: window.location.origin }),
  });
}

export async function exchangeHospitalSso(code: string, state: string, provider = "hospital_sso"): Promise<AuthResponse> {
  const result = await request<AuthResponse>("/auth/sso/callback", {
    method: "POST",
    body: JSON.stringify({ code, state, provider }),
  });
  storeStaffToken(result.access_token);
  return result;
}

export async function getCurrentUser(): Promise<AuthUser> {
  if (localStorage.getItem(DEMO_MODE_KEY) === "true") {
    const user = getDemoUser();
    if (user) return user;
  }

  try {
    return await request<AuthUser>("/me");
  } catch (error) {
    if (!isDemoRequestFailure(error) && localStorage.getItem(DEMO_MODE_KEY) !== "true") {
      throw error;
    }
    const user = getDemoUser() ?? buildDemoUser("admin");
    saveDemoSession(user, false);
    return user;
  }
}

export async function getSystemStatus(): Promise<SystemStatus> {
  return request<SystemStatus>("/system/status");
}

export async function getOrganization(): Promise<Organization> {
  return request<Organization>("/organization");
}

export async function getOrganizationWorkspace(): Promise<Workspace> {
  return request<Workspace>("/workspace");
}

export async function completeOrganization(name: string, department: string, timezone: string): Promise<void> {
  await request("/organization", { method: "PATCH", body: JSON.stringify({ name, department, timezone }) });
}

export async function createWorkspace(name: string, department: string, timezone: string): Promise<Workspace> {
  return request<Workspace>("/workspace", { method: "POST", body: JSON.stringify({ name, department, timezone }) });
}

export async function logout(): Promise<void> {
  localStorage.removeItem("careos-access-token");
  localStorage.removeItem("careos-portal-token");
  localStorage.removeItem(DEMO_MODE_KEY);
  localStorage.removeItem(DEMO_USER_KEY);
}

export async function portalLogin(email: string, password: string): Promise<PortalAuthResponse> {
  const result = await request<PortalAuthResponse>("/patient-portal/login", { method: "POST", body: JSON.stringify({ email, password }) });
  storePortalToken(result.access_token);
  return result;
}

export function getPortalAccount(): Promise<PortalAuthResponse["user"]> {
  if (localStorage.getItem(DEMO_MODE_KEY) === "true") {
    const user = getDemoUser();
    if (user) {
      return Promise.resolve({ id: user.id, patient_id: user.id, email: user.email, full_name: user.full_name, role: user.role });
    }
  }

  return portalRequest<PortalAuthResponse["user"]>("/patient-portal/me").catch((error) => {
    if (!isDemoRequestFailure(error)) {
      throw error;
    }
    const user = getDemoUser() ?? buildDemoUser("patient");
    saveDemoSession(user, true);
    return { id: user.id, patient_id: user.id, email: user.email, full_name: user.full_name, role: user.role };
  });
}

export function getPortalOverview(): Promise<PortalOverview> {
  return portalRequest<PortalOverview>("/patient-portal/overview");
}

export function sendPortalMessage(payload: { subject: string; body: string }): Promise<ApiMessage> {
  return portalRequest<ApiMessage>("/patient-portal/messages", { method: "POST", body: JSON.stringify(payload) });
}

export async function downloadPortalDocument(documentId: string): Promise<Blob> {
  const response = await fetch(`${import.meta.env.VITE_API_URL || "/api/v1"}/patient-portal/documents/${documentId}/download`, { headers: { Authorization: `Bearer ${localStorage.getItem("careos-portal-token") || ""}` } });
  if (!response.ok) throw new Error("Could not download document");
  return response.blob();
}

export async function uploadPortalDocument(file: File): Promise<{ id: string; filename: string; download_url: string }> {
  const content = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1] || "");
    reader.onerror = () => reject(new Error("Could not read document"));
    reader.readAsDataURL(file);
  });
  return portalRequest<{ id: string; filename: string; download_url: string }>("/patient-portal/documents", { method: "POST", body: JSON.stringify({ filename: file.name, content, content_type: file.type || "application/octet-stream" }) });
}

export async function getTeam(): Promise<AuthUser[]> {
  return request<AuthUser[]>("/team");
}

export async function getDashboard(): Promise<DashboardContract> {
  return request<DashboardContract>("/dashboard");
}

export async function getNotifications(): Promise<Array<{ id: string; kind: string; title: string; body: string; read: boolean; created_at: string }>> {
  return request<Array<{ id: string; kind: string; title: string; body: string; read: boolean; created_at: string }>>("/notifications");
}
export const markNotificationRead = (id: string) => request<{ read: boolean }>(`/notifications/${id}/read`, { method: "PATCH" });

export async function enrollMfa(): Promise<{ secret: string; otpauth_uri: string; enabled: boolean }> {
  return request("/auth/mfa/enroll", { method: "POST" });
}

export async function verifyMfa(code: string): Promise<{ enabled: boolean; recovery_codes: string[] }> {
  return request("/auth/mfa/verify", { method: "POST", body: JSON.stringify({ code }) });
}

export async function regenerateMfaRecoveryCodes(): Promise<{ recovery_codes: string[] }> {
  return request("/auth/mfa/recovery-codes", { method: "POST" });
}

export async function getAuditEvents(): Promise<Array<{ action: string; resource: string; created_at: string }>> {
  return request<Array<{ action: string; resource: string; created_at: string }>>("/audit-events");
}

export async function getMessages(): Promise<ApiMessage[]> {
  return request<ApiMessage[]>("/messages");
}

export async function createMessage(payload: { patient_id: string; subject: string; body: string; sender_type?: string; direction?: string }): Promise<ApiMessage> {
  return request<ApiMessage>("/messages", { method: "POST", body: JSON.stringify(payload) });
}
export const markMessageRead = (id: string) => request<{ read: boolean }>(`/messages/${id}/read`, { method: "PATCH" });

export async function getPortalPatient(patientId: string): Promise<PortalPatientResponse> {
  return request<PortalPatientResponse>(`/portal/patients/${patientId}`);
}

export async function getAnalytics(): Promise<AnalyticsResponse> {
  return request<AnalyticsResponse>("/analytics");
}

export async function getReports(): Promise<ReportsResponse> {
  return request<ReportsResponse>("/reports");
}

export async function getTasks(): Promise<TaskItem[]> {
  return request<TaskItem[]>("/tasks");
}

export async function createTask(task: { patient_id: string; title: string; description: string; assignee?: string; priority?: string; status?: string; due_at?: string | null }): Promise<TaskItem> {
  return request<TaskItem>("/tasks", { method: "POST", body: JSON.stringify(task) });
}

export async function getCarePlans(): Promise<CarePlanItem[]> {
  return request<CarePlanItem[]>("/care-plans");
}

export async function createCarePlan(plan: { patient_id: string; title: string; summary: string; status?: string; goals?: string[] }): Promise<CarePlanItem> {
  return request<CarePlanItem>("/care-plans", { method: "POST", body: JSON.stringify(plan) });
}

export async function getDepartmentMetrics(): Promise<DepartmentMetricsResponse> {
  return request<DepartmentMetricsResponse>("/department-metrics");
}

export const getPatients = (q = "", page = 1, pageSize = 50) => {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (q.trim()) params.set("q", q.trim());
  return request<ApiPatient[]>(`/patients?${params.toString()}`);
};
export const getPatientById = (id: string) => request<PatientDetailResponse>(`/patients/${id}`);
export const createEncounter = (patientId: string, encounterType = "consultation") => request<ApiEncounter>("/encounters", { method: "POST", body: JSON.stringify({ patient_id: patientId, encounter_type: encounterType }) });
export const getEncounter = (id: string) => request<ApiEncounter>(`/encounters/${id}`);
export async function uploadEncounterRecording(encounterId: string, blob: Blob, filename = "consultation.webm"): Promise<{ id: string; encounter_id: string; patient_id: string; transcript_id: string; transcript_status: string }> {
  const content = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(",")[1] || ""); reader.onerror = () => reject(new Error("Could not read recording")); reader.readAsDataURL(blob); });
  return request(`/encounters/${encounterId}/recordings`, { method: "POST", body: JSON.stringify({ content, filename, content_type: blob.type || "audio/webm" }) });
}
export const getTranscript = (id: string) => request<ApiTranscript>(`/transcripts/${id}`);
export const transcribeRecording = (id: string) => request<{ id: string; status: string; transcript_text: string; confidence: number | null; provider: string }>(`/recordings/${id}/transcribe`, { method: "POST" });
export const reviewTranscript = (id: string, transcriptText: string) => request<{ id: string; version: number; transcript_text: string; status: string }>(`/transcripts/${id}/review`, { method: "PATCH", body: JSON.stringify({ transcript_text: transcriptText }) });
export const createPatient = (patient: Omit<ApiPatient, "id">) => request<ApiPatient>("/patients", { method: "POST", body: JSON.stringify({ ...patient, department: patient.department ?? "", project: patient.project ?? "" }) });
export const getAppointments = (filters: { status?: string; fromAt?: string; toAt?: string; page?: number; pageSize?: number } = {}) => {
  const params = new URLSearchParams({ page: String(filters.page ?? 1), page_size: String(filters.pageSize ?? 100) });
  if (filters.status) params.set("status", filters.status);
  if (filters.fromAt) params.set("from_at", filters.fromAt);
  if (filters.toAt) params.set("to_at", filters.toAt);
  return request<ApiAppointment[]>(`/appointments?${params.toString()}`);
};
export const createAppointment = (appointment: { patient_id: string; starts_at: string; reason: string; status?: string }) => request<ApiAppointment>("/appointments", { method: "POST", body: JSON.stringify(appointment) });
export const updateAppointmentStatus = (id: string, status: string) => request<ApiAppointment>(`/appointments/${id}/status?status=${encodeURIComponent(status)}`, { method: "PATCH" });
export const rescheduleAppointment = (id: string, startsAt: string, reason?: string) => request<ApiAppointment>(`/appointments/${id}`, { method: "PATCH", body: JSON.stringify({ starts_at: startsAt, ...(reason ? { reason } : {}) }) });
export const createClinicalNote = (note: { patient_id: string; encounter_id?: string; body: string; ai_draft?: string | null }) => request<ApiNote>("/clinical-notes", { method: "POST", body: JSON.stringify(note) });
export const updateClinicalNote = (id: string, note: { body: string; ai_draft?: string | null }) => request<ApiNote>(`/clinical-notes/${id}`, { method: "PATCH", body: JSON.stringify(note) });
export const getClinicalNoteVersions = (id: string) => request<Array<{ id: string; version: number; body: string; ai_draft: string | null; status: string; author_id: string; created_at: string }>>(`/clinical-notes/${id}/versions`);
export const generateClinicalSummary = (id: string) => request<ApiNote & { provider: string; summary?: string }>(`/clinical-notes/${id}/summary`, { method: "POST" });
export const signClinicalNote = (id: string) => request<ApiNote>(`/clinical-notes/${id}/sign`, { method: "POST" });
export const askAssistant = (patient_id: string, question = patient_id) => request<{ answer: string; response?: string; confidence: number; sources: Array<{ title: string; page?: string }>; provider: string }>("/assistant/query", { method: "POST", body: JSON.stringify({ patient_id, question }) });
export async function uploadPatientDocument(patientId: string, file: File): Promise<DocumentUploadResponse> {
  const content = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1] || "");
    reader.onerror = () => reject(new Error("Could not read document"));
    reader.readAsDataURL(file);
  });
  return request<DocumentUploadResponse>(`/patients/${patientId}/documents`, {
    method: "POST",
    body: JSON.stringify({ filename: file.name, content, content_type: file.type || "application/octet-stream" }),
  });
}
export const reviewPatientDocument = (patientId: string, documentId: string, status: "pending" | "approved" | "rejected") => request<{ id: string; review_status: string }>(`/patients/${patientId}/documents/${documentId}/review?status=${status}`, { method: "PATCH" });
