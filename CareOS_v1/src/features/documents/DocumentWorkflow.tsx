import { useEffect, useState } from "react";
import { Check, Database, FileText, Plus } from "lucide-react";
import {
  reviewPatientDocument,
  uploadPatientDocument,
} from "../../api/documents";
import { getPatients } from "../../api/patients";
import { PageHeading } from "../../components/PageHeading";
import { PanelHeading } from "../../components/PanelHeading";
import type { TranslationKey } from "../../i18n";

type Translator = (key: TranslationKey) => string;
type DocumentItem = {
  id: string;
  name: string;
  type: string;
  status: "ocrReady" | "verified";
  confidence: number;
  summary: string;
  extracted: string[];
  uploadedAt: string;
  downloadUrl?: string;
};

function initialDocuments(t: Translator): DocumentItem[] {
  return [
    {
      id: "doc-1",
      name: "Lab_Report_2026-09-12.pdf",
      type: "PDF",
      status: "ocrReady",
      confidence: 97,
      summary: t("demoLabSummary"),
      extracted: [
        t("demoLabFindingBilirubin"),
        t("demoLabFindingTroponin"),
        t("demoLabFindingGfr"),
      ],
      uploadedAt: t("todayAt"),
    },
    {
      id: "doc-2",
      name: "ECG_Review.jpeg",
      type: "Image",
      status: "verified",
      confidence: 94,
      summary: t("demoEcgSummary"),
      extracted: [t("sinusRhythm"), t("noAcuteIschemia"), t("followUpEcg")],
      uploadedAt: t("todayAt"),
    },
  ];
}

export function DocumentWorkflow({ t }: { t: Translator }) {
  const locale = t("workspace");
  const [documents, setDocuments] = useState<DocumentItem[]>(() =>
    initialDocuments(t),
  );
  const [selectedId, setSelectedId] = useState("doc-1");
  const [uploading, setUploading] = useState(false);
  const [approved, setApproved] = useState(false);
  const [patientId, setPatientId] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const selectedDocument =
    documents.find((item) => item.id === selectedId) ?? documents[0];
  const documentStatus = (status: DocumentItem["status"]) =>
    t(status === "verified" ? "documentStatusVerified" : "documentStatusOcrReady");

  useEffect(() => {
    getPatients()
      .then((records) => setPatientId(records[0]?.id ?? null))
      .catch(() => setPatientId(null));
  }, []);

  useEffect(() => {
    const localizedSamples = initialDocuments(t);
    setDocuments((current) =>
      current.map((document) =>
        localizedSamples.find((sample) => sample.id === document.id) ?? document,
      ),
    );
  }, [locale]);

  const onFileSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const allowedTypes = [
      "application/pdf",
      "image/jpeg",
      "image/png",
      "image/tiff",
    ];
    if (!allowedTypes.includes(file.type)) {
      setUploadError(t("invalidDocumentType"));
      event.target.value = "";
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setUploadError(t("documentSizeLimit"));
      event.target.value = "";
      return;
    }
    setUploading(true);
    setUploadError(null);
    try {
      if (!patientId) throw new Error(t("apiPatientRequired"));
      const uploaded = await uploadPatientDocument(patientId, file);
      const extracted =
        typeof uploaded.extracted_text === "string" &&
        uploaded.extracted_text.trim()
          ? uploaded.extracted_text
              .split(/(?<=[.?!])\s+/)
              .filter(Boolean)
              .slice(0, 3)
          : [
              t("clinicalFindingExtracted"),
              t("followUpReviewRequired"),
              t("evidenceSavedToChart"),
            ];
      const document: DocumentItem = {
        id: String(uploaded.id ?? `doc-${Date.now()}`),
        name: uploaded.filename || file.name,
        type: file.type.includes("pdf") ? "PDF" : "Image",
        status: uploaded.ocr_status === "completed" ? "verified" : "ocrReady",
        confidence: uploaded.ocr_status === "completed" ? 96 : 72,
        summary:
          uploaded.extracted_text ||
          `${t("documentSummaryFallback")} (${file.name})`,
        extracted,
        uploadedAt: t("uploadedJustNow"),
        downloadUrl: uploaded.download_url,
      };
      setDocuments((current) => [document, ...current]);
      setSelectedId(document.id);
      setApproved(false);
    } catch (error) {
      setUploadError(
        error instanceof Error ? error.message : t("couldNotUploadDocument"),
      );
    } finally {
      setUploading(false);
      event.target.value = "";
    }
  };

  if (!selectedDocument) return null;
  return (
    <>
      <PageHeading
        eyebrow={t("documentIntakeEyebrow")}
        title={t("documentIntakeTitle")}
        detail={t("documentIntakeDetail")}
        action={
          <button
            className="primary-btn"
            onClick={() =>
              window.dispatchEvent(
                new CustomEvent("careos:toast", {
                  detail: t("documentReviewQueued"),
                }),
              )
            }
          >
            <Plus size={17} /> {t("queueReview")}
          </button>
        }
      />
      <div className="documents-shell">
        <section className="panel documents-panel">
          <PanelHeading
            title={t("documentQueue")}
            detail={t("latestUploadsOcr")}
          />
          <label className="dropzone">
            <input
              type="file"
              onChange={onFileSelect}
              style={{ display: "none" }}
            />
            <div className="dropzone-body">
              <Database size={18} />
              <strong>
                {uploading ? t("processingDocument") : t("addReportScan")}
              </strong>
              <span>{t("supportedUploadFormats")}</span>
            </div>
          </label>
          {uploadError && (
            <div className="inline-error" role="alert">
              {uploadError}
            </div>
          )}
          <div className="document-list">
            {documents.map((document) => (
              <button
                key={document.id}
                className={`document-item ${selectedId === document.id ? "active" : ""}`}
                onClick={() => {
                  setSelectedId(document.id);
                  setApproved(false);
                }}
                type="button"
              >
                <div className="document-icon">
                  <FileText size={16} />
                </div>
                <div className="document-meta">
                  <strong>{document.name}</strong>
                  <span>
                    {document.type} · {document.uploadedAt}
                  </span>
                </div>
                <span
                  className={`status ${document.status === "verified" ? "confirmed" : "pending"}`}
                >
                  {documentStatus(document.status)}
                </span>
              </button>
            ))}
          </div>
        </section>
        <section className="panel documents-detail-panel">
          <PanelHeading
            title={t("aiFindings")}
            detail={`${t("confidenceLabel")} ${selectedDocument.confidence}% · ${selectedDocument.type}`}
          />
          <div className="document-summary">
            <div className="detail-header-row">
              <div>
                <span className="eyebrow">{t("selectedDocumentLabel")}</span>
                <h3>{selectedDocument.name}</h3>
              </div>
              <span className={`status ${approved ? "confirmed" : "pending"}`}>
                {approved ? t("statusApproved") : documentStatus(selectedDocument.status)}
              </span>
            </div>
            <p>{selectedDocument.summary}</p>
            <div className="extracted-list">
              {selectedDocument.extracted.map((entry) => (
                <div key={entry} className="extract-row">
                  <Check size={14} />
                  <span>{entry}</span>
                </div>
              ))}
            </div>
            <div className="document-actions">
              {selectedDocument.downloadUrl && (
                <a
                  className="outline-btn"
                  href={selectedDocument.downloadUrl}
                  target="_blank"
                  rel="noreferrer"
                >
                  {t("downloadDocument")}
                </a>
              )}
              <button
                className="outline-btn"
                onClick={() =>
                  window.dispatchEvent(
                    new CustomEvent("careos:toast", {
                      detail: t("ocrReviewCorrected"),
                    }),
                  )
                }
              >
                {t("editFindings")}
              </button>
              <button
                className="primary-btn"
                onClick={async () => {
                  if (!patientId || selectedDocument.id.startsWith("doc-")) {
                    setApproved(true);
                    return;
                  }
                  try {
                    await reviewPatientDocument(
                      patientId,
                      selectedDocument.id,
                      "approved",
                    );
                    setApproved(true);
                  } catch (error) {
                    window.dispatchEvent(
                      new CustomEvent("careos:toast", {
                        detail:
                          error instanceof Error
                            ? error.message
                            : t("couldNotApproveDocument"),
                      }),
                    );
                  }
                }}
              >
                {approved ? t("statusApproved") : t("approveOcr")}
              </button>
            </div>
          </div>
        </section>
      </div>
      <section className="panel" style={{ marginTop: 20 }}>
        <PanelHeading
          title={t("clinicalEvidenceChain")}
          detail={t("evidenceTraceability")}
        />
        <div className="data-row">
          <strong>{t("sourceLabel")}</strong>
          <span>{t("extractedFact")}</span>
          <span>{t("confidenceLabel")}</span>
          <span>{t("reviewLabel")}</span>
          <span />
        </div>
        {documents.map((document) => (
          <div className="data-row" key={`${document.id}-evidence`}>
            <strong>{document.name}</strong>
            <span>{document.extracted[0]}</span>
            <span className="status confirmed">{document.confidence}%</span>
            <span
              className={
                document.status === "verified"
                  ? "status confirmed"
                  : "status pending"
              }
            >
              {documentStatus(document.status)}
            </span>
            <button
              className="text-btn"
              onClick={() => setSelectedId(document.id)}
            >
              {t("open")}
            </button>
          </div>
        ))}
      </section>
    </>
  );
}
