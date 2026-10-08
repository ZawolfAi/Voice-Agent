import { useEffect, useState } from "react";
import { FileText, ShieldCheck } from "lucide-react";
import { PageHeading } from "../../components/PageHeading";
import { getSystemStatus, type SystemStatus } from "../../api";

type Integration = {
  name: string;
  adapter: string;
  state: string;
  next: string;
};

function PanelHeading({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="panel-heading">
      <div>
        <h3>{title}</h3>
        <p>{detail}</p>
      </div>
    </div>
  );
}

export function IntegrationHub() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  useEffect(() => {
    getSystemStatus()
      .then(setStatus)
      .catch(() => setStatus(null));
  }, []);
  const providerState = (key: string, fallback: string) =>
    status?.providers?.[key]?.configured ? "Configured" : fallback;
  const integrations: Integration[] = [
    {
      name: "Clinical summary",
      adapter: "ClinicalSummaryProvider",
      state: providerState("ai", "Not configured"),
      next: "Configure an approved server-side LLM and evaluation dataset.",
    },
    {
      name: "Clinical RAG",
      adapter: "RagProvider",
      state: "Not configured",
      next: "Connect pgvector/Qdrant and an approved protocol library with page citations.",
    },
    {
      name: "Document OCR",
      adapter: "OcrProvider",
      state: "Not configured",
      next: "Connect an approved OCR vendor plus private object storage.",
    },
    {
      name: "Patient reminders",
      adapter: "NotificationProvider",
      state: providerState("smtp", "Queue only"),
      next: "Connect SMS/WhatsApp/email provider and background worker; obtain patient consent.",
    },
    {
      name: "Hospital EHR/HIS",
      adapter: "EhrConnector",
      state: "Not configured",
      next: "Agree FHIR/HL7 contract, credentials, field mapping, and audit requirements with the hospital.",
    },
  ];

  return (
    <>
      <PageHeading
        eyebrow="DELIVERY FOUNDATION"
        title="Integration hub"
        detail="Safe handoff points for services that are not yet connected. No production credentials are stored here."
      />
      <section className="panel">
        <PanelHeading
          title="Provider adapters"
          detail="Backend adapters live in backend/app/integrations.py"
        />
        {integrations.map((item) => (
          <div className="data-row" key={item.adapter}>
            <div>
              <strong>{item.name}</strong>
              <span>{item.adapter}</span>
            </div>
            <span className="status pending">{item.state}</span>
            <span style={{ maxWidth: 360 }}>{item.next}</span>
          </div>
        ))}
      </section>
      <section className="panel" style={{ marginTop: 20 }}>
        <PanelHeading
          title="Connection checklist"
          detail="Required before turning on real patient data"
        />
        <div className="record-item">
          <div className="record-date">
            <ShieldCheck size={18} />
          </div>
          <div>
            <strong>Secrets and approval</strong>
            <p>
              Store provider credentials in deployment secrets; never use VITE_*
              variables for secrets or PHI.
            </p>
          </div>
        </div>
        <div className="record-item">
          <div className="record-date">
            <FileText size={18} />
          </div>
          <div>
            <strong>Validation and audit</strong>
            <p>
              Enable a provider only after clinical review, test coverage,
              consent, and audit events are in place.
            </p>
          </div>
        </div>
      </section>
    </>
  );
}
