import { FormEvent, useEffect, useState } from "react";
import { CalendarDays, FileText, MessageCircle, Send } from "lucide-react";
import { PageHeading } from "../../components/PageHeading";
import { PanelHeading } from "../../components/PanelHeading";
import type { TranslationKey } from "../../i18n";
import { navigateToView, viewFromLocation } from "../../app/routes";
import {
  downloadPortalDocument,
  getPortalOverview,
  sendPortalMessage,
  type PortalOverview,
} from "../../api/portal";

type Translator = (key: TranslationKey) => string;
export function PatientPortal({ t }: { t: Translator }) {
  const [tab, setTab] = useState<
    "Overview" | "Appointments" | "Messages" | "Documents"
  >("Overview");
  const [overview, setOverview] = useState<PortalOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const tabs = [
    { id: "Overview", label: t("overview") },
    { id: "Appointments", label: t("appointments") },
    { id: "Messages", label: t("messagesTitle") },
    { id: "Documents", label: t("documentation") },
  ] as const;
  useEffect(() => {
    let active = true;
    setLoading(true);
    getPortalOverview()
      .then((result) => {
        if (active) {
          setOverview(result);
          setError(null);
        }
      })
      .catch((reason: unknown) => {
        if (active)
          setError(
            reason instanceof Error
              ? reason.message
              : "Could not load your health information.",
          );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    const syncTabToRoute = () => {
      const route = viewFromLocation();
      if (route === "appointments") setTab("Appointments");
      else if (route === "messages") setTab("Messages");
      else if (route === "portal") setTab("Overview");
    };
    window.addEventListener("popstate", syncTabToRoute);
    window.addEventListener("hashchange", syncTabToRoute);
    return () => {
      window.removeEventListener("popstate", syncTabToRoute);
      window.removeEventListener("hashchange", syncTabToRoute);
    };
  }, []);

  const submitMessage = async (event: FormEvent) => {
    event.preventDefault();
    if (!subject.trim() || !body.trim()) return;
    setSending(true);
    try {
      const message = await sendPortalMessage({
        subject: subject.trim(),
        body: body.trim(),
      });
      setOverview((current) =>
        current
          ? { ...current, messages: [message, ...current.messages] }
          : current,
      );
      setSubject("");
      setBody("");
    } catch (reason: unknown) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Could not send your message.",
      );
    } finally {
      setSending(false);
    }
  };
  const downloadDocument = async (documentId: string, filename: string) => {
    try {
      const blob = await downloadPortalDocument(documentId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (reason: unknown) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Could not download document.",
      );
    }
  };
  const appointmentRows = overview?.appointments ?? [];
  const messageRows = overview?.messages ?? [];
  const documentRows = overview?.documents ?? [];
  const formatDate = (value: string) =>
    new Date(value).toLocaleString([], {
      dateStyle: "medium",
      timeStyle: "short",
    });

  return (
    <>
      <PageHeading
        eyebrow={t("patientPortal")}
        title={
          overview?.patient
            ? `${overview.patient.given_name} ${overview.patient.family_name}`
            : t("patientPortal")
        }
        detail={t("portalDetail")}
      />
      {overview?.patient && (
        <div className="portal-patient-id">
          <span>{t("patientCode")}</span>
          <code>{overview.patient.patient_code}</code>
        </div>
      )}
      <div className="tabs portal-tabs">
        {tabs.map((item) => (
          <button
            key={item.id}
            type="button"
            className={tab === item.id ? "active" : ""}
            aria-current={tab === item.id ? "page" : undefined}
            onClick={() => {
              setTab(item.id);
              if (item.id === "Overview") navigateToView("portal");
              else if (item.id === "Appointments")
                navigateToView("appointments");
              else if (item.id === "Messages") navigateToView("messages");
            }}
          >
            {item.label}
          </button>
        ))}
      </div>
      {loading && (
        <section className="panel">
          <div className="loading-state">
            Loading your health information...
          </div>
        </section>
      )}
      {!loading && error && (
        <section className="panel">
          <div className="error-state" role="alert">
            {error}
          </div>
        </section>
      )}
      {!loading && !error && overview && (
        <>
          {tab === "Overview" && (
            <div className="portal-grid">
              <PortalAppointments
                appointments={appointmentRows}
                formatDate={formatDate}
                emptyLabel="No appointments available."
              />
              <PortalMessages
                messages={messageRows}
                detail={t("messagesDetail")}
                emptyLabel="No messages yet."
              />
            </div>
          )}
          {tab === "Appointments" && (
            <section className="panel portal-section">
              <PanelHeading
                title={t("appointments")}
                detail={t("scheduleDetail")}
              />
              {appointmentRows.length ? (
                appointmentRows.map((appointment) => (
                  <div className="record-item" key={appointment.id}>
                    <div className="record-date">
                      <CalendarDays size={18} />
                    </div>
                    <div>
                      <strong>{formatDate(appointment.starts_at)}</strong>
                      <p>{appointment.reason}</p>
                    </div>
                    <span className="status confirmed">
                      {appointment.status}
                    </span>
                  </div>
                ))
              ) : (
                <div className="empty-state">No appointments available.</div>
              )}
            </section>
          )}
          {tab === "Messages" && (
            <section className="panel portal-section">
              <PanelHeading
                title={t("messagesTitle")}
                detail={t("messagesDetail")}
              />
              {messageRows.length ? (
                messageRows.map((message) => (
                  <div className="message-bubble received" key={message.id}>
                    <strong>{message.subject}</strong>
                    <br />
                    {message.body}
                    <small>{formatDate(message.created_at)}</small>
                  </div>
                ))
              ) : (
                <div className="empty-state">No messages yet.</div>
              )}
              <form className="portal-compose" onSubmit={submitMessage}>
                <input
                  required
                  value={subject}
                  onChange={(event) => setSubject(event.target.value)}
                  placeholder="Subject"
                  aria-label="Message subject"
                />
                <textarea
                  required
                  value={body}
                  onChange={(event) => setBody(event.target.value)}
                  placeholder="Type a message"
                  aria-label="Message body"
                />
                <button className="primary-btn small" disabled={sending}>
                  <Send size={14} /> {sending ? "Sending..." : t("reply")}
                </button>
              </form>
            </section>
          )}
          {tab === "Documents" && (
            <section className="panel portal-section">
              <PanelHeading
                title="Documents"
                detail="Approved records shared with you"
              />
              {documentRows.length ? (
                documentRows.map((document) => (
                  <div className="record-item" key={document.id}>
                    <div className="record-date">
                      <FileText size={18} />
                    </div>
                    <div>
                      <strong>{document.filename}</strong>
                      <p>
                        {document.ocr_status} ·{" "}
                        {formatDate(document.created_at)}
                      </p>
                    </div>
                    {document.download_url && (
                      <button
                        className="text-btn"
                        onClick={() =>
                          downloadDocument(document.id, document.filename)
                        }
                      >
                        Download
                      </button>
                    )}
                  </div>
                ))
              ) : (
                <div className="empty-state">No documents available.</div>
              )}
            </section>
          )}
        </>
      )}
    </>
  );
}

function PortalAppointments({
  appointments,
  formatDate,
  emptyLabel,
}: {
  appointments: PortalOverview["appointments"];
  formatDate: (value: string) => string;
  emptyLabel: string;
}) {
  return (
    <section className="panel">
      <PanelHeading
        title="Appointments"
        detail="Your upcoming and recent visits"
      />
      {appointments.slice(0, 4).map((appointment) => (
        <div className="record-item" key={appointment.id}>
          <div className="record-date">
            <CalendarDays size={18} />
          </div>
          <div>
            <strong>{formatDate(appointment.starts_at)}</strong>
            <p>{appointment.reason}</p>
          </div>
          <span className="status confirmed">{appointment.status}</span>
        </div>
      ))}
      {appointments.length === 0 && (
        <div className="empty-state">{emptyLabel}</div>
      )}
    </section>
  );
}
function PortalMessages({
  messages,
  detail,
  emptyLabel,
}: {
  messages: PortalOverview["messages"];
  detail: string;
  emptyLabel: string;
}) {
  return (
    <section className="panel">
      <PanelHeading title="Messages" detail={detail} />
      {messages.slice(0, 4).map((message) => (
        <div className="record-item" key={message.id}>
          <div className="record-date">
            <MessageCircle size={18} />
          </div>
          <div>
            <strong>{message.subject}</strong>
            <p>{message.body}</p>
          </div>
        </div>
      ))}
      {messages.length === 0 && <div className="empty-state">{emptyLabel}</div>}
    </section>
  );
}
