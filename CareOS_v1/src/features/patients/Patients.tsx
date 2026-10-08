import { useEffect, useState } from "react";
import { ChevronRight, Plus, Search } from "lucide-react";
import { createEncounter } from "../../api/encounters";
import { getPatients } from "../../api/patients";
import type { ApiPatient } from "../../api";
import { PageHeading } from "../../components/PageHeading";
import type { TranslationKey } from "../../i18n";
import { navigateToView } from "../../app/routes";

type Translator = (key: TranslationKey) => string;
export function Patients({
  t,
  department,
  project,
  onNavigate,
}: {
  t: Translator;
  department: string;
  project: string;
  onNavigate?: (view: "notes") => void;
}) {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<ApiPatient[]>([]);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [startingEncounter, setStartingEncounter] = useState<string | null>(
    null,
  );
  const pageSize = 25;
  useEffect(() => {
    setLoading(true);
    getPatients(query, page, pageSize)
      .then((records) => {
        setItems(records);
        setError(null);
      })
      .catch((reason: unknown) =>
        setError(
          reason instanceof Error
            ? reason.message === "Insufficient permissions"
              ? t("permissionDenied")
              : reason.message
            : "Could not load patients.",
        ),
      )
      .finally(() => setLoading(false));
  }, [query, page]);
  useEffect(() => {
    setPage(1);
  }, [query]);
  const startEncounter = async (patientId: string) => {
    setStartingEncounter(patientId);
    try {
      const encounter = await createEncounter(patientId);
      localStorage.setItem("careos-active-encounter-id", encounter.id);
      window.dispatchEvent(
        new CustomEvent("careos:toast", { detail: "Encounter started." }),
      );
      if (onNavigate) onNavigate("notes");
      else navigateToView("notes");
    } catch (reason: unknown) {
      setError(
        reason instanceof Error ? reason.message : "Could not start encounter.",
      );
    } finally {
      setStartingEncounter(null);
    }
  };
  return (
    <>
      <PageHeading
        eyebrow={t("careDirectory")}
        title={t("patients")}
        detail={t("searchManage")}
        action={
          <button className="primary-btn">
            <Plus size={17} /> {t("addPatient")}
          </button>
        }
      />
      <div className="toolbar">
        <div className="search-box">
          <Search size={17} />
          <input
            placeholder={t("searchPatients")}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        <span className="scope-pill">{t("searchCriteria")}</span>
        <span className="scope-pill">
          {t("departmentScope")}: {department}
        </span>
        <span className="scope-pill">
          {t("projectScope")}: {project}
        </span>
      </div>
      <section className="panel table-panel">
        <div className="table-header">
          <span>{t("patient")}</span>
          <span>{t("condition")}</span>
          <span>{t("careStatus")}</span>
          <span />
        </div>
        {loading && <div className="loading-state">{t("loadingPatients")}</div>}
        {!loading && error && (
          <div className="error-state" role="alert">
            {error}
          </div>
        )}
        {!loading &&
          !error &&
          items.map((patient) => (
            <div className="patient-table-row" key={patient.id}>
              <div className="patient-cell">
                <div
                  className="patient-avatar"
                  style={{ background: "#8db4ad" }}
                >{`${patient.given_name[0] || "P"}${patient.family_name[0] || ""}`}</div>
                <div>
                  <strong>
                    {patient.given_name} {patient.family_name}
                  </strong>
                  <span>
                    <span className="patient-code-label">
                      {t("patientCode")}: <code className="patient-code">{patient.patient_code}</code>
                    </span>
                    {" · "}
                    {patient.medical_record_number} ·{" "}
                    {new Date().getFullYear() -
                      new Date(patient.date_of_birth).getFullYear()}{" "}
                    {t("years")}
                  </span>
                </div>
              </div>
              <span>{patient.condition || t("notRecorded")}</span>
              <span className="status confirmed">{patient.care_status}</span>
              <button
                className="outline-btn"
                disabled={startingEncounter === patient.id}
                onClick={() => void startEncounter(patient.id)}
              >
                {startingEncounter === patient.id
                  ? t("startingEncounter")
                  : t("startEncounter")}
              </button>
              <ChevronRight size={17} />
            </div>
          ))}
        {!loading && !error && items.length === 0 && (
          <div className="empty-state">{t("noPatients")}</div>
        )}
        <div className="pagination-controls">
          <button
            className="outline-btn"
            disabled={loading || page === 1}
            onClick={() => setPage((value) => value - 1)}
          >
            {t("previous")}
          </button>
          <span>
            {t("page")} {page}
          </span>
          <button
            className="outline-btn"
            disabled={loading || items.length < pageSize}
            onClick={() => setPage((value) => value + 1)}
          >
            {t("next")}
          </button>
        </div>
      </section>
    </>
  );
}
