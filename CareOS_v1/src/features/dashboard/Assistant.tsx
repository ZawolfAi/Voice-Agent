import { useEffect, useState } from "react";
import { BookOpen, Send, Stethoscope } from "lucide-react";
import { askAssistant } from "../../api/clinical";
import { getPatients, type ApiPatient } from "../../api";
import { PageHeading } from "../../components/PageHeading";
import { PanelHeading } from "../../components/PanelHeading";
import type { TranslationKey } from "../../i18n";

type Translator = (key: TranslationKey) => string;
export function Assistant({ t }: { t: Translator }) {
  const [patients, setPatients] = useState<ApiPatient[]>([]);
  const [patientId, setPatientId] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [sources, setSources] = useState<
    Array<{ title: string; page?: string }>
  >([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingPatients, setLoadingPatients] = useState(true);
  useEffect(() => {
    getPatients()
      .then((items) => {
        setPatients(items);
        setPatientId(items[0]?.id ?? "");
      })
      .catch((reason) =>
        setError(
          reason instanceof Error ? reason.message : t("patientsUnavailable"),
        ),
      )
      .finally(() => setLoadingPatients(false));
  }, [t]);
  const ask = async () => {
    if (!question.trim() || !patientId) return;
    setLoading(true);
    setError("");
    try {
      const result = await askAssistant(patientId, question.trim());
      setAnswer(result.answer || result.response || "");
      setSources(result.sources ?? []);
      setQuestion("");
    } catch (reason) {
      setAnswer("");
      setSources([]);
      setError(
        reason instanceof Error ? reason.message : t("assistantUnavailable"),
      );
    } finally {
      setLoading(false);
    }
  };
  return (
    <>
      <PageHeading
        eyebrow={t("assistant")}
        title={t("assistant")}
        detail={t("assistantReady")}
      />
      <div className="assistant-layout">
        <section className="panel assistant-panel">
          <PanelHeading title={t("askAssistant")} detail={t("reviewAi")} />
          <div className="assistant-intro">
            <Stethoscope size={20} />
            <p>{t("assistantReady")}</p>
          </div>
          <div className="assistant-form">
            <label className="assistant-patient-field">
              {t("patient")}
              <select
                value={patientId}
                disabled={loadingPatients || !patients.length}
                onChange={(event) => setPatientId(event.target.value)}
              >
                <option value="">
                  {loadingPatients ? t("loading") : t("selectPatient")}
                </option>
                {patients.map((patient) => (
                  <option key={patient.id} value={patient.id}>
                    {patient.given_name} {patient.family_name} ·{" "}
                    {patient.patient_code}
                  </option>
                ))}
              </select>
            </label>
            <textarea
              className="assistant-question-input"
              dir="auto"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder={t("askAssistant")}
              rows={5}
            />
            <button
              type="button"
              className="primary-btn assistant-submit"
              disabled={loading || !question.trim() || !patientId}
              onClick={ask}
            >
              <Send size={15} /> {loading ? t("working") : t("askAssistant")}
            </button>
          </div>
        </section>
        <section className="panel assistant-panel">
          <PanelHeading
            title={t("sources") || "Sources"}
            detail={t("citationCoverage")}
          />
          <div
            className={`assistant-answer ${error ? "error-state" : ""}`}
          >
            <BookOpen size={18} />
            {error || answer || t("summaryEmpty")}
          </div>
          {sources.length > 0 && (
            <ul className="assistant-sources">
              {sources.map((source) => (
                <li key={`${source.title}-${source.page ?? ""}`}>
                  {source.title}
                  {source.page ? ` · ${source.page}` : ""}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </>
  );
}
