import { useEffect, useRef, useState } from "react";
import { Bot, MessageCircle, Send, X } from "lucide-react";
import { askGeneralChat } from "../../api/chat";
import type { TranslationKey } from "../../i18n";

type Translator = (key: TranslationKey) => string;
type ChatMessage = { id: string; role: "user" | "assistant"; text: string };

export function GlobalChat({ t }: { t: Translator }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const endOfMessages = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) endOfMessages.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading, open]);

  if (!localStorage.getItem("careos-access-token")) return null;

  const send = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const message = draft.trim();
    if (!message || loading) return;
    setDraft("");
    setError("");
    setMessages((current) => [
      ...current,
      { id: `user-${Date.now()}`, role: "user", text: message },
    ]);
    setLoading(true);
    try {
      const response = await askGeneralChat(message);
      setMessages((current) => [
        ...current,
        { id: `assistant-${Date.now()}`, role: "assistant", text: response.answer },
      ]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("generalChatError"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="global-chat">
      {open && (
        <section className="global-chat-panel" role="dialog" aria-label={t("generalChatTitle")}>
          <header className="global-chat-header">
            <div className="global-chat-identity">
              <span className="global-chat-avatar"><Bot size={17} /></span>
              <div>
                <strong>{t("generalChatTitle")}</strong>
                <span>{t("generalChatPrivacy")}</span>
              </div>
            </div>
            <button type="button" className="icon-btn" aria-label={t("closeChat")} onClick={() => setOpen(false)}>
              <X size={17} />
            </button>
          </header>
          <div className="global-chat-messages" aria-live="polite">
            {messages.length === 0 && <p className="global-chat-welcome">{t("generalChatWelcome")}</p>}
            {messages.map((message) => (
              <div className={`global-chat-message ${message.role}`} key={message.id}>
                {message.text}
              </div>
            ))}
            {loading && <div className="global-chat-message assistant">{t("generalChatThinking")}</div>}
            {error && <div className="global-chat-error" role="alert">{error}</div>}
            <div ref={endOfMessages} />
          </div>
          <form className="global-chat-compose" onSubmit={(event) => void send(event)}>
            <input
              aria-label={t("generalChatInput")}
              placeholder={t("generalChatPlaceholder")}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              autoComplete="off"
            />
            <button type="submit" aria-label={t("sendGeneralChat")} disabled={!draft.trim() || loading}>
              <Send size={16} />
            </button>
          </form>
        </section>
      )}
      <button
        type="button"
        className={`global-chat-toggle ${open ? "is-open" : ""}`}
        aria-label={open ? t("closeChat") : t("openChat")}
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        {open ? <X size={20} /> : <MessageCircle size={20} />}
      </button>
    </div>
  );
}
