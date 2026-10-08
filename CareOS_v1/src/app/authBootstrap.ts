import { getCurrentUser, getPortalAccount, type AuthUser } from "../api";
import { clearSession } from "../api/client";

export async function bootstrapAuth(): Promise<AuthUser | null> {
  if (!localStorage.getItem("careos-access-token")) return null;
  try {
    return await getCurrentUser();
  } catch {
    clearSession();
    localStorage.removeItem("careos-onboarding-complete");
    return null;
  }
}

export async function bootstrapPortalAuth() {
  if (!localStorage.getItem("careos-portal-token")) return null;
  try {
    return await getPortalAccount();
  } catch {
    clearSession();
    return null;
  }
}