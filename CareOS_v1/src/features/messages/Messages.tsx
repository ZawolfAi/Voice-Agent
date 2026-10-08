import { useEffect, useState } from "react";
import { MessageCircle, Send } from "lucide-react";
import {
  createMessage,
  getMessages,
  markMessageRead,
} from "../../api/messages";
import { PageHeading } from "../../components/PageHeading";
import { PanelHeading } from "../../components/PanelHeading";
import type { TranslationKey } from "../../i18n";

type Translator = (key: TranslationKey) => string;
type Thread = {
  id?: string;
  patientId?: string;
  name: string;
  subject: string;
  text: string;
  unread: boolean;
};
export function Messages({ t }: { t: Translator }) {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(0);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    getMessages()
      .then((records) => {
        if (!active) return;
        setThreads(
          records
            .slice(0, 4)
            .map((item, index) => ({
              id: item.id,
              patientId: item.patient_id,
              name: index % 2 ? "Clinical lead" : "Care team",
              subject: item.subject || "Patient message",
              text: item.body,
              unread: !item.read,
            })),
        );
        setError("");
      })
      .catch((reason) => {
        if (active)
          setError(
            reason instanceof Error ? reason.message : t("messagesUnavailable"),
          );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [t]);
  const thread = threads[selected] ??
    threads[0] ?? {
      name: "Care team",
      subject: "Patient message",
      text: t("labReadyMessage"),
      unread: false,
    };
  const send = async () => {
    if (!draft.trim() || !thread.patientId) return;
    try {
      await createMessage({
        patient_id: thread.patientId,
        subject: thread.subject,
        body: draft.trim(),
        sender_type: "care_team",
        direction: "outbound",
      });
      setThreads((items) =>
        items.map((item, index) =>
          index === selected ? { ...item, text: draft.trim() } : item,
        ),
      );
      setDraft("");
      setError("");
      window.dispatchEvent(
        new CustomEvent("careos:toast", { detail: t("messageSent") }),
      );
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : t("messageSendFailed"),
      );
    }
  };
  return (
    <>
      <PageHeading
        eyebrow={t("communication")}
        title={t("messagesTitle")}
        detail={t("messagesDetail")}
        action={
          <button
            className="primary-btn"
            onClick={() => setError(t("newMessageRequiresPatient"))}
          >
            <MessageCircle size={16} /> {t("newMessage")}
          </button>
        }
      />
      {loading ? (
        <div className="empty-state">Loading messages...</div>
      ) : error ? (
        <div className="empty-state error-state">{error}</div>
      ) : threads.length === 0 ? (
        <div className="empty-state">{t("noMessages")}</div>
      ) : (
        <div className="messages-layout">
          <section className="panel thread-list">
            {threads.map((item, index) => (
              <button
                className={`thread ${selected === index ? "active" : ""}`}
                key={item.subject}
                onClick={async () => {
                  setSelected(index);
                  if (item.id && item.unread) {
                    try {
                      await markMessageRead(item.id);
                      setThreads((current) =>
                        current.map((entry) =>
                          entry.id === item.id
                            ? { ...entry, unread: false }
                            : entry,
                        ),
                      );
                    } catch (reason) {
                      setError(
                        reason instanceof Error
                          ? reason.message
                          : t("messagesUnavailable"),
                      );
                    }
                  }
                }}
              >
                <div className="avatar avatar-doctor">
                  {item.name
                    .split(" ")
                    .map((part) => part[0])
                    .join("")
                    .slice(0, 2)}
                </div>
                <div>
                  <strong>{item.name}</strong>
                  <b>{item.subject}</b>
                  <span>{item.text}</span>
                </div>
                {item.unread && <i />}
              </button>
            ))}
          </section>
          <section className="panel message-view">
            <PanelHeading title={thread.subject} detail={thread.name} />
            <div className="message-bubble received">
              {thread.text}
              <small>09:42</small>
            </div>
            <div className="message-compose">
              <input
                placeholder={t("secureMessagePlaceholder")}
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
              />
              <button
                className="primary-btn small"
                disabled={!draft.trim() || !thread.patientId}
                onClick={send}
              >
                <Send size={14} /> {t("reply")}
              </button>
            </div>
          </section>
        </div>
      )}
    </>
  );
}
