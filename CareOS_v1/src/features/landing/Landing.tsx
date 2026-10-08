import { useEffect, useRef, useState } from "react";
import { askGuestChat, askGuestVoice } from "../../api/chat";
import {
  ArrowRight,
  BookOpen,
  CalendarDays,
  ChevronRight,
  Database,
  FileText,
  HeartPulse,
  Mic,
  MicOff,
  MessageCircle,
  Moon,
  Plus,
  ShieldCheck,
  Sun,
  Users,
  Clock3,
  X,
} from "lucide-react";
import type { Language, TranslationKey } from "../../i18n";

type Theme = "light" | "dark";
type LandingChatMessage = { id: number; role: "user" | "assistant"; text: string };
type Translator = (key: TranslationKey) => string;
type Props = {
  language: Language;
  setLanguage: (language: Language) => void;
  onEnter: (mode?: "signin" | "signup") => void;
  t: Translator;
  theme: Theme;
  setTheme: (theme: Theme) => void;
};

export function Landing({
  language,
  setLanguage,
  onEnter,
  t,
  theme,
  setTheme,
}: Props) {
  const isArabic = language === "ar";
  const [page, setPage] = useState<
    "home" | "problem" | "features" | "assistant" | "demo" | "contact"
  >("home");
  const [assistantMode, setAssistantMode] = useState<"chat" | "voice">("chat");
  const [chatInput, setChatInput] = useState("");
  const [voiceInput, setVoiceInput] = useState("");
  const [chatMessages, setChatMessages] = useState<LandingChatMessage[]>([]);
  const [isVoiceOrbActive, setIsVoiceOrbActive] = useState(false);
  const [isVoiceRecording, setIsVoiceRecording] = useState(false);
  const [isSendingChat, setIsSendingChat] = useState(false);
  const [chatError, setChatError] = useState("");
  const [voiceStatus, setVoiceStatus] = useState("");
  const voiceRecorder = useRef<MediaRecorder | null>(null);
  const voiceStream = useRef<MediaStream | null>(null);
  const voiceChunks = useRef<Blob[]>([]);
  const voiceStartInProgress = useRef(false);
  const chatMessageId = useRef(0);
  const [demoRequested, setDemoRequested] = useState(false);
  const [isMobilePreview, setIsMobilePreview] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.innerWidth <= 900;
  });

  useEffect(() => {
    const handleResize = () => {
      setIsMobilePreview(window.innerWidth <= 900);
    };

    handleResize();
    window.addEventListener("resize", handleResize);

    return () => window.removeEventListener("resize", handleResize);
  }, []);

  useEffect(
    () => () => {
      if (voiceRecorder.current?.state === "recording") voiceRecorder.current.stop();
      voiceStream.current?.getTracks().forEach((track) => track.stop());
      window.speechSynthesis?.cancel();
    },
    [],
  );

  const sendChat = async (draft: string): Promise<string | null> => {
    const message = draft.trim();
    if (!message || isSendingChat) return null;
    chatMessageId.current += 1;
    const userMessageId = chatMessageId.current;
    setChatError("");
    setChatMessages((messages) => [
      ...messages,
      { id: userMessageId, role: "user", text: message },
    ]);
    setIsSendingChat(true);

    try {
      const response = await askGuestChat(message);
      chatMessageId.current += 1;
      setChatMessages((messages) => [
        ...messages,
        { id: chatMessageId.current, role: "assistant", text: response.answer },
      ]);
      return response.answer;
    } catch (error) {
      setChatError(error instanceof Error ? error.message : t("generalChatError"));
      return null;
    } finally {
      setIsSendingChat(false);
    }
  };

  const speakVoiceReply = (answer: string | null) => {
    if (!answer || !window.speechSynthesis) return;
    const utterance = new SpeechSynthesisUtterance(answer);
    utterance.lang = isArabic ? "ar-EG" : "en-US";
    utterance.onstart = () => setIsVoiceOrbActive(true);
    utterance.onend = () => setIsVoiceOrbActive(false);
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
  };

  const sendVoiceRecording = async (recording: Blob) => {
    if (!recording.size) {
      setVoiceStatus(isArabic ? "لم يتم التقاط صوت." : "No audio was captured.");
      return;
    }
    if (recording.size > 10 * 1024 * 1024) {
      setVoiceStatus(isArabic ? "التسجيل أكبر من الحد المسموح (10 MB)." : "Recording exceeds the 10 MB limit.");
      return;
    }

    setVoiceStatus("");
    setIsSendingChat(true);
    try {
      const audioBase64 = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
          if (typeof reader.result !== "string") {
            reject(new Error("Unable to read audio recording"));
            return;
          }
          resolve(reader.result.slice(reader.result.indexOf(",") + 1));
        };
        reader.onerror = () => reject(new Error("Unable to read audio recording"));
        reader.readAsDataURL(recording);
      });
      const response = await askGuestVoice(audioBase64, isArabic ? "ar-EG" : "en-US");
      chatMessageId.current += 1;
      const transcriptId = chatMessageId.current;
      chatMessageId.current += 1;
      setChatMessages((messages) => [
        ...messages,
        { id: transcriptId, role: "user", text: response.transcript },
        { id: chatMessageId.current, role: "assistant", text: response.answer },
      ]);
      speakVoiceReply(response.answer);
    } catch (error) {
      setVoiceStatus(error instanceof Error ? error.message : t("generalChatError"));
    } finally {
      setIsSendingChat(false);
    }
  };

  const startVoice = async () => {
    if (voiceStartInProgress.current || isSendingChat) return;
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setVoiceStatus(isArabic ? "تسجيل الصوت غير مدعوم في هذا المتصفح." : "Audio recording is not supported in this browser.");
      return;
    }

    voiceStartInProgress.current = true;
    setVoiceStatus("");
    let stream: MediaStream | null = null;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const supportedMimeType = ["audio/webm;codecs=opus", "audio/webm"].find((type) =>
        MediaRecorder.isTypeSupported(type),
      );
      if (!supportedMimeType) throw new Error("This browser cannot record WebM audio");

      const recorder = new MediaRecorder(stream, { mimeType: supportedMimeType });
      voiceStream.current = stream;
      voiceRecorder.current = recorder;
      voiceChunks.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size) voiceChunks.current.push(event.data);
      };
      recorder.onerror = () => {
        voiceChunks.current = [];
        stream?.getTracks().forEach((track) => track.stop());
        voiceStream.current = null;
        voiceRecorder.current = null;
        setVoiceStatus(isArabic ? "حدث خطأ أثناء تسجيل الصوت." : "Audio recording failed.");
        setIsVoiceRecording(false);
        setIsVoiceOrbActive(false);
      };
      recorder.onstop = () => {
        const audio = new Blob(voiceChunks.current, { type: "audio/webm" });
        voiceChunks.current = [];
        stream?.getTracks().forEach((track) => track.stop());
        voiceStream.current = null;
        voiceRecorder.current = null;
        setIsVoiceRecording(false);
        setIsVoiceOrbActive(false);
        void sendVoiceRecording(audio);
      };
      recorder.start();
      setIsVoiceRecording(true);
      setIsVoiceOrbActive(true);
    } catch {
      stream?.getTracks().forEach((track) => track.stop());
      setVoiceStatus(
        isArabic
          ? "تعذر الوصول للميكروفون. تحقق من الإذن وحاول مجددًا."
          : "Could not access the microphone. Check permission and try again.",
      );
      setIsVoiceRecording(false);
      setIsVoiceOrbActive(false);
    } finally {
      voiceStartInProgress.current = false;
    }
  };

  const toggleVoice = () => {
    if (voiceRecorder.current?.state === "recording") {
      voiceRecorder.current.stop();
      return;
    }
    void startVoice();
  };
  const copy = isArabic
    ? {
        title: "رعاية تفكر معك.",
        detail:
          "CareOS مساحة عمل SaaS موجهة للفرق الطبية: تلخيص فوري للملاحظات، اقتراحات مبنية على مصادر واضحة، وجدولة أذكى، مع بقاء القرار النهائي للطبيب.",
        primary: "احجز عرض تجريبي",
        secondary: "شاهد كيف يعمل",
      }
    : {
        title: "Care that thinks with you.",
        detail:
          "CareOS is a SaaS workspace for clinical teams: instant note summarization, source-linked suggestions, smarter scheduling, and the physician stays in control at the end of every workflow.",
        primary: "Book a demo",
        secondary: "See how it works",
      };
  const features = isArabic
    ? [
        {
          icon: <BookOpen />,
          title: "تلخيص AI",
          detail: "حوّل الملاحظة الحرة إلى مسودة منظمة قبل الاعتماد.",
        },
        {
          icon: <Database />,
          title: "اقتراحات موثقة",
          detail: "اعرض المصدر والثقة بجانب كل توصية.",
        },
        {
          icon: <CalendarDays />,
          title: "إدارة مواعيد ذكية",
          detail: "نسّق اليوميّة وذكّر الفريق من نفس الواجهة.",
        },
        {
          icon: <ShieldCheck />,
          title: "حوكمة وأمان مؤسسي",
          detail: "صلاحيات واضحة وسجل تدقيق يساعد فريقك على العمل بثقة.",
        },
        {
          icon: <FileText />,
          title: "ملف مريض منظم",
          detail: "اجمع المستندات والملاحظات في سياق واضح يسهل الرجوع إليه.",
        },
        {
          icon: <Mic />,
          title: "إدخال صوتي",
          detail: "دوّن الملاحظات أثناء التحدث وتابعها مباشرة داخل السجل الطبي.",
        },
        {
          icon: <MessageCircle />,
          title: "مساعد Chat وVoice للزوار",
          detail: "اسأل المساعد بالعربية أو الإنجليزية كتابةً أو بالصوت قبل إنشاء حساب.",
        },
      ]
    : [
        {
          icon: <BookOpen />,
          title: "AI summarization",
          detail:
            "Turn a free-form note into an editable draft before sign-off.",
        },
        {
          icon: <Database />,
          title: "Traceable suggestions",
          detail:
            "Show the source and confidence next to every recommendation.",
        },
        {
          icon: <CalendarDays />,
          title: "Smart scheduling",
          detail: "Keep appointments and follow-ups moving from one place.",
        },
        {
          icon: <ShieldCheck />,
          title: "Governed operations",
          detail: "Clear permissions and an audit trail for accountable care teams.",
        },
        {
          icon: <FileText />,
          title: "Organized patient records",
          detail: "Keep documents and notes together in a context your team can trust.",
        },
        {
          icon: <Mic />,
          title: "Voice capture",
          detail: "Dictate notes in real time and turn them into structured clinical context.",
        },
        {
          icon: <MessageCircle />,
          title: "Guest Chat & Voice assistant",
          detail: "Talk to the assistant in Arabic or English by text or voice before signing up.",
        },
      ];
  const nav = (next: typeof page) => setPage(next);
  return (
    <div
      className={`landing-page ${theme === "dark" ? "dark-mode-landing" : ""} ${
        isMobilePreview ? "force-mobile" : ""
      }`}
      dir={isArabic ? "rtl" : "ltr"}
    >
      <header className="landing-nav landing-enter-nav">
        <button
          type="button"
          className="brand landing-brand landing-logo-home"
          onClick={() => nav("home")}
        >
          <div className="brand-mark">
            <HeartPulse size={19} />
          </div>
          <span>
            care<span>os</span>
          </span>
        </button>
        <nav className="landing-links">
          <button className="nav-link-button" onClick={() => nav("problem")}>
            {isArabic ? "المشكلة" : "Problem"}
          </button>
          <button className="nav-link-button" onClick={() => nav("features")}>
            {isArabic ? "المميزات" : "Features"}
          </button>
          <button className="nav-link-button" onClick={() => nav("assistant")}>
            {isArabic ? "المساعد" : "Chat / Voice"}
          </button>
          <button className="nav-link-button" onClick={() => nav("demo")}>
            {isArabic ? "اللقطة" : "Demo"}
          </button>
          <button className="nav-link-button" onClick={() => nav("contact")}>
            {isArabic ? "تواصل" : "Contact"}
          </button>
        </nav>
        <div className="landing-nav-actions">
          <button
            className="landing-control-btn landing-icon-btn landing-mobile-control"
            onClick={() => setLanguage(isArabic ? "en" : "ar")}
            aria-label={isArabic ? "Switch to English" : "Switch to Arabic"}
            title={isArabic ? "Switch to English" : "Switch to Arabic"}
          >
            {isArabic ? "EN" : "AR"}
          </button>
          <button
            className="landing-control-btn landing-icon-btn landing-mobile-control"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            aria-label={
              theme === "dark" ? "Switch to light mode" : "Switch to dark mode"
            }
            title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          >
            {theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
          </button>
          <div className="landing-auth-links">
            <button
              className="landing-auth-link landing-auth-link-login"
              onClick={() => onEnter("signin")}
            >
              {isArabic ? "تسجيل الدخول" : "LOGIN"}
            </button>
            <span className="landing-auth-divider">|</span>
            <button
              className="landing-auth-link landing-auth-link-signup"
              onClick={() => onEnter("signup")}
            >
              {isArabic ? "إنشاء حساب" : "SIGN UP"}
            </button>
          </div>
          <button
            className="landing-primary landing-control-btn landing-control-btn-primary"
            onClick={() => onEnter()}
          >
            {t("enterPlatform")} <ArrowRight size={15} />
          </button>
        </div>
      </header>

      <nav className="mobile-page-tabs" aria-label="Mobile section tabs">
        {[
          { key: "problem", label: isArabic ? "المشكلة" : "Problem" },
          { key: "features", label: isArabic ? "المميزات" : "Features" },
          { key: "assistant", label: isArabic ? "المساعد" : "Chat / Voice" },
          { key: "demo", label: isArabic ? "اللقطة" : "Demo" },
          { key: "contact", label: isArabic ? "تواصل" : "Contact" },
        ].map((item) => (
          <button
            key={item.key}
            type="button"
            className={`mobile-page-tab ${page === item.key ? "active" : ""}`}
            onClick={() => nav(item.key as typeof page)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      {page === "home" ? (
        <main>
          <section className="landing-hero">
            <div className="landing-copy landing-hero-copy">
              <h1 className="hero-reveal hero-title">{copy.title}</h1>
              <p className="hero-reveal hero-detail">{copy.detail}</p>
              <div className="landing-actions hero-reveal hero-actions">
                <button
                  className="primary-btn landing-primary"
                  onClick={() => nav("contact")}
                >
                  {copy.primary} <ArrowRight size={17} />
                </button>
                <button
                  className="landing-secondary"
                  onClick={() => nav("features")}
                >
                  {copy.secondary} <ChevronRight size={15} />
                </button>
              </div>
              <div className="hero-badges hero-reveal">
                <span className="hero-badge">
                  {isArabic ? "عربي / إنجليزي" : "Arabic / English"}
                </span>
                <span className="hero-badge">
                  {isArabic ? "مراجعة طبية 100%" : "100% physician review"}
                </span>
                <span className="hero-badge">
                  {isArabic ? "اقتراحات مرتبطة بالمصدر" : "Source-linked suggestions"}
                </span>
              </div>
            </div>
            <div className="landing-visual landing-float-card">
              <div className="visual-orb visual-orb-a" />
              <div className="visual-orb visual-orb-b" />
              <div className="visual-scan" />
              <div className="visual-header">
                <span>
                  <span className="live-dot" /> CareOS clinical workspace
                </span>
                <span>{isArabic ? "معاينة حية" : "Live preview"}</span>
              </div>
              <div className="visual-title">
                <div>
                  <small>
                    {isArabic ? "اليوم، 21 أكتوبر" : "Today, 21 October"}
                  </small>
                  <h2>
                    {isArabic ? "صباح الخير، د. رنا" : "Good morning, Dr. Rana"}
                  </h2>
                </div>
                <div className="visual-avatar">DR</div>
              </div>
              <div className="visual-metrics">
                <div>
                  <Users size={16} />
                  <b>248</b>
                  <span>{isArabic ? "مريض" : "Patients"}</span>
                </div>
                <div>
                  <CalendarDays size={16} />
                  <b>08</b>
                  <span>{isArabic ? "زيارة اليوم" : "Visits today"}</span>
                </div>
                <div>
                  <Clock3 size={16} />
                  <b>05</b>
                  <span>{isArabic ? "متابعة" : "Follow-ups"}</span>
                </div>
              </div>
              <div className="visual-panel">
                <div className="visual-panel-heading">
                  <b>{isArabic ? "تدفق اليوم" : "Today's care flow"}</b>
                  <span>{isArabic ? "تفاصيل" : "View details"}</span>
                </div>
                <div className="visual-row">
                  <span>09:00</span>
                  <strong>Mariam Hassan</strong>
                  <em>{isArabic ? "متابعة" : "Follow-up"}</em>
                  <i>{isArabic ? "مؤكد" : "Confirmed"}</i>
                </div>
                <div className="visual-row">
                  <span>10:30</span>
                  <strong>Omar Khaled</strong>
                  <em>{isArabic ? "مراجعة سكر" : "Diabetes review"}</em>
                  <i>{isArabic ? "وصل" : "Arrived"}</i>
                </div>
                <div className="visual-row">
                  <span>12:00</span>
                  <strong>Nour El Din</strong>
                  <em>{isArabic ? "إحالة قلب" : "Cardiology referral"}</em>
                  <i>{isArabic ? "قيد الانتظار" : "Pending"}</i>
                </div>
              </div>
              <div className="visual-footer">
                <span>
                  <BookOpen size={13} />{" "}
                  {isArabic ? "مرتبط بالمصدر" : "Evidence linked"}
                </span>
                <span>
                  <ShieldCheck size={13} />{" "}
                  {isArabic ? "مراجعة بشرية" : "Human review"}
                </span>
              </div>
            </div>
          </section>
          <section className="landing-home-grid">
            <div className="landing-home-card">
              <h3>
                {isArabic
                  ? "ملاحظات أسرع، قرارات أكثر وضوحًا"
                  : "Faster notes, clearer decisions"}
              </h3>
              <p>
                {isArabic
                  ? "تجميع الملاحظات، المواعيد، والاقتراحات في واجهة واحدة."
                  : "Bring notes, schedules, and recommendations into one workflow."}
              </p>
            </div>
            <div className="landing-home-card">
              <h3>
                {isArabic
                  ? "كل اقتراح مرتبط بمصدر واضح"
                  : "Every suggestion is traceable"}
              </h3>
              <p>
                {isArabic
                  ? "يظهر المصدر والثقة حتى يراجع الطبيب القرار بدقة."
                  : "Show source and confidence so physicians review with clarity."}
              </p>
            </div>
            <div className="landing-home-card">
              <h3>
                {isArabic
                  ? "أمان للمريض، راحة للطبيب"
                  : "Safer care, calmer operations"}
              </h3>
              <p>
                {isArabic
                  ? "تجربة مؤسسية مصممة للفرق الطبية الحقيقية."
                  : "A governed experience for real healthcare operations."}
              </p>
            </div>
          </section>
        </main>
      ) : (
        <main className="landing-subpage-shell">
          <div className="landing-subpage">
            <button className="back-link" onClick={() => nav("home")}>
              <ChevronRight size={14} /> {isArabic ? "العودة" : "Back"}
            </button>
            <div className="landing-section-heading">
              <h2>
                {page === "problem"
                  ? isArabic
                    ? "أين يضيع الوقت؟"
                    : "Where does the time go?"
                  : page === "features"
                    ? isArabic
                      ? "سبع أدوات في واجهة واحدة"
                      : "Seven tools in one clinical workspace"
                    : page === "assistant"
                      ? isArabic
                        ? "تحدث مع مساعد CareOS"
                        : "Talk with the CareOS assistant"
                      : page === "demo"
                      ? isArabic
                        ? "واجهة العمل اليومية"
                        : "Clinical workspace overview"
                      : isArabic
                        ? "ابدأ المحادثة"
                        : "Start the conversation"}
              </h2>
            </div>
            {page === "assistant" ? (
              <section className="landing-assistant-preview">
                <div className="assistant-demo-shell">
                  <div
                    className="assistant-demo-toggle"
                    aria-label={isArabic ? "اختيار طريقة المحادثة" : "Conversation mode selector"}
                  >
                    <button
                      type="button"
                      className={assistantMode === "chat" ? "active" : ""}
                      onClick={() => {
                        if (voiceRecorder.current?.state === "recording") {
                          voiceRecorder.current.stop();
                        }
                        window.speechSynthesis?.cancel();
                        setIsVoiceOrbActive(false);
                        setAssistantMode("chat");
                      }}
                    >
                      {isArabic ? "دردشة" : "Chat"}
                    </button>
                    <button
                      type="button"
                      className={assistantMode === "voice" ? "active" : ""}
                      onClick={() => {
                        setAssistantMode("voice");
                        startVoice();
                      }}
                    >
                      {isArabic ? "صوت" : "Voice"}
                    </button>
                  </div>

                  <div className={`assistant-demo-card ${assistantMode === "voice" ? "voice-mode" : ""}`}>
                    {assistantMode === "chat" ? (
                      <>
                        <div className="assistant-demo-messages" aria-live="polite">
                          {chatMessages.length === 0 && (
                            <div className="assistant-demo-message assistant-demo-message-left assistant-demo-welcome">
                              {isArabic
                                ? "مرحبًا، كيف يمكنني مساعدتك اليوم؟"
                                : "Hi, how can I help you today?"}
                            </div>
                          )}
                          {chatMessages.map((message, index) => (
                            <div
                              className={`assistant-demo-message ${message.role === "user" ? "assistant-demo-message-right" : "assistant-demo-message-left"}`}
                              key={message.id}
                            >
                              {message.text}
                            </div>
                          ))}
                          {isSendingChat && (
                            <div className="assistant-demo-typing" aria-label={isArabic ? "جاري الرد" : "Assistant is responding"}>
                              <span />
                              <span />
                              <span />
                            </div>
                          )}
                          {chatError && <div className="assistant-demo-error" role="alert">{chatError}</div>}
                        </div>
                        <form
                          className="assistant-demo-input"
                          onSubmit={(event) => {
                            event.preventDefault();
                            void sendChat(chatInput);
                            setChatInput("");
                          }}
                        >
                          <input
                            aria-label={isArabic ? "اكتب رسالة" : "Type a message"}
                            value={chatInput}
                            onChange={(event) => setChatInput(event.target.value)}
                            placeholder={isArabic ? "اكتب رسالة..." : "Type a message..."}
                          />
                          <button
                            className="assistant-demo-send"
                            type="submit"
                            aria-label={isArabic ? "إرسال الرسالة" : "Send message"}
                            disabled={!chatInput.trim() || isSendingChat}
                          >
                            <ArrowRight size={17} />
                          </button>
                        </form>
                      </>
                    ) : (
                      <div className="assistant-voice-scene">
                        <button
                          className={`assistant-voice-orb ${isVoiceOrbActive ? "active" : ""}`}
                          type="button"
                          onClick={toggleVoice}
                          aria-label={
                            isArabic
                              ? isVoiceOrbActive
                                ? "إيقاف المساعد الصوتي"
                                : "تشغيل المساعد الصوتي"
                              : isVoiceOrbActive
                                ? "Pause voice assistant"
                                : "Start voice assistant"
                          }
                        />
                        <span className="assistant-sr-only" role="status" aria-live="polite">
                          {voiceStatus}
                        </span>
                      </div>
                    )}
                    {assistantMode === "voice" && (
                      <form
                        className="assistant-voice-bar"
                        onSubmit={(event) => {
                          event.preventDefault();
                          const message = voiceInput.trim();
                          if (!message || isSendingChat) return;
                          setVoiceInput("");
                          void sendChat(message).then(speakVoiceReply);
                        }}
                      >
                        <button
                          type="button"
                          aria-label={isArabic ? "محادثة جديدة" : "New conversation"}
                          title={isArabic ? "محادثة جديدة" : "New conversation"}
                          disabled={isSendingChat}
                          onClick={() => {
                            setChatMessages([]);
                            setChatError("");
                            setChatInput("");
                            setVoiceInput("");
                          }}
                        >
                          <Plus size={25} />
                        </button>
                        <input
                          aria-label={isArabic ? "اكتب رسالة" : "Type a message"}
                          placeholder={isArabic ? "اكتب" : "Type"}
                          value={voiceInput}
                          onChange={(event) => setVoiceInput(event.target.value)}
                        />
                        <button
                          className="assistant-voice-mic"
                          type="button"
                          aria-label={isArabic ? "تبديل الميكروفون" : "Toggle microphone"}
                          title={isArabic ? "تبديل الميكروفون" : "Toggle microphone"}
                          onClick={toggleVoice}
                          disabled={isSendingChat && !isVoiceRecording}
                        >
                          {isVoiceRecording ? <Mic size={20} /> : <MicOff size={20} />}
                        </button>
                        <button
                          className="assistant-voice-close"
                          type="button"
                          aria-label={isArabic ? "إغلاق الصوت والعودة للدردشة" : "Close voice and return to chat"}
                          title={isArabic ? "إغلاق الصوت" : "Close voice"}
                          onClick={() => {
                            if (voiceRecorder.current?.state === "recording") {
                              voiceRecorder.current.stop();
                            }
                            window.speechSynthesis?.cancel();
                            setIsVoiceOrbActive(false);
                            setAssistantMode("chat");
                          }}
                        >
                          <X size={22} />
                        </button>
                      </form>
                    )}
                  </div>
                </div>
              </section>
            ) : page === "problem" ? (
              <div className="section-stack">
                <div className="section-pill">
                  {isArabic
                    ? "التحدي الرئيسي: الكفاءة"
                    : "Core challenge: clinical efficiency"}
                </div>
                <div className="problem-grid problem-grid-single">
                  {[
                    isArabic
                      ? [
                          "التوثيق يستهلك الوقت",
                          "الهدف هو تقليل إعادة الكتابة وتحرير وقت الطبيب.",
                        ]
                      : [
                          "Documentation eats the day",
                          "The goal is to reduce rewrites and give the doctor back time.",
                        ],
                    isArabic
                      ? [
                          "البروتوكولات تتكرر في أماكن متعددة",
                          "البحث عن المصدر الصحيح يبطئ القرارات ويزيد الاحتكاك.",
                        ]
                      : [
                          "Guidance is scattered",
                          "Hunting for the right source slows decisions and adds friction.",
                        ],
                    isArabic
                      ? [
                          "المتابعة تفلت بين الأدوات",
                          "الجدولة، الرسائل، والملاحظات تحتاج مساحة موحدة.",
                        ]
                      : [
                          "Follow-up slips between tools",
                          "Scheduling, messages, and notes need one shared workspace.",
                        ],
                  ].map(([title, detail], index) => (
                    <article className="problem-card" key={title}>
                      <span>0{index + 1}</span>
                      <h3>{title}</h3>
                      <p>{detail}</p>
                    </article>
                  ))}
                </div>
                <div className="info-grid">
                  <div className="info-panel">
                    <small>
                      {isArabic ? "مؤشر الأداء" : "Operational signal"}
                    </small>
                    <h4>
                      {isArabic
                        ? "أوقات أطول من المتوقع"
                        : "Time lost in separate tools"}
                    </h4>
                    <p>
                      {isArabic
                        ? "الفرق بين ملاحظة المريض، البحث، والجدولة يستهلك ساعات كل يوم."
                        : "The gap between patient notes, guidance lookup, and scheduling turns into hours every day."}
                    </p>
                  </div>
                  <div className="info-panel">
                    <small>{isArabic ? "النتيجة" : "Result"}</small>
                    <h4>
                      {isArabic
                        ? "إجهاد إداري مرتفع"
                        : "Higher administrative burden"}
                    </h4>
                    <p>
                      {isArabic
                        ? "الفرق تحتاج مساحة موحدة للقرار والمتابعة."
                        : "Clinicians need one shared workspace for decisions and follow-up."}
                    </p>
                  </div>
                </div>
              </div>
            ) : page === "features" ? (
              <div className="feature-grid landing-feature-grid">
                {features.map((feature) => (
                  <article className="landing-feature" key={feature.title}>
                    <div className="feature-icon">{feature.icon}</div>
                    <h3>{feature.title}</h3>
                    <p>{feature.detail}</p>
                  </article>
                ))}
              </div>
            ) : page === "demo" ? (
              <div className="section-stack">
                <div className="section-pill">
                  {isArabic
                    ? "من الملاحظة إلى القرار"
                    : "From note to decision"}
                </div>
                <div className="demo-page-card">
                  <div className="landing-visual landing-float-card">
                    <div className="visual-orb visual-orb-a" />
                    <div className="visual-orb visual-orb-b" />
                    <div className="visual-scan" />
                    <div className="visual-header">
                      <span>
                        <span className="live-dot" /> CareOS clinical workspace
                      </span>
                      <span>{isArabic ? "معاينة حية" : "Live preview"}</span>
                    </div>
                    <div className="visual-title">
                      <div>
                        <small>
                          {isArabic ? "اليوم، 21 أكتوبر" : "Today, 21 October"}
                        </small>
                        <h2>
                          {isArabic
                            ? "صباح الخير، د. رنا"
                            : "Good morning, Dr. Rana"}
                        </h2>
                      </div>
                      <div className="visual-avatar">DR</div>
                    </div>
                    <div className="visual-metrics">
                      <div><Users size={16} /><b>248</b><span>{isArabic ? "مريض" : "Patients"}</span></div>
                      <div><CalendarDays size={16} /><b>08</b><span>{isArabic ? "زيارة اليوم" : "Visits today"}</span></div>
                      <div><Clock3 size={16} /><b>05</b><span>{isArabic ? "متابعة" : "Follow-ups"}</span></div>
                    </div>
                    <div className="visual-panel">
                      <div className="visual-panel-heading">
                        <b>{isArabic ? "تدفق اليوم" : "Today's care flow"}</b>
                        <span>{isArabic ? "تفاصيل" : "View details"}</span>
                      </div>
                      <div className="visual-row">
                        <span>09:00</span>
                        <strong>Mariam Hassan</strong>
                        <em>{isArabic ? "متابعة" : "Follow-up"}</em>
                        <i>{isArabic ? "مؤكد" : "Confirmed"}</i>
                      </div>
                      <div className="visual-row">
                        <span>10:30</span>
                        <strong>Omar Khaled</strong>
                        <em>{isArabic ? "مراجعة سكر" : "Diabetes review"}</em>
                        <i>{isArabic ? "وصل" : "Arrived"}</i>
                      </div>
                      <div className="visual-row">
                        <span>12:00</span>
                        <strong>Nour El Din</strong>
                        <em>{isArabic ? "إحالة قلب" : "Cardiology referral"}</em>
                        <i>{isArabic ? "قيد الانتظار" : "Pending"}</i>
                      </div>
                    </div>
                    <div className="visual-footer">
                      <span>
                        <BookOpen size={13} />{" "}
                        {isArabic ? "مرتبط بالمصدر" : "Evidence linked"}
                      </span>
                      <span>
                        <ShieldCheck size={13} />{" "}
                        {isArabic ? "مراجعة بشرية" : "Human review"}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            ) : page === "contact" ? (
              <div className="section-stack">
                <div className="section-pill">
                  {isArabic
                    ? "استقبال سريع — عرض تجريبي في 48 ساعة"
                    : "Fast response — demo in 48 hours"}
                </div>
                <div className="contact-wrap">
                  <form
                    className="contact-form"
                    onSubmit={(event) => {
                      event.preventDefault();
                      setDemoRequested(true);
                    }}
                  >
                    <input
                      type="text"
                      placeholder={isArabic ? "الاسم" : "Name"}
                    />
                    <input
                      type="text"
                      placeholder={isArabic ? "اسم المستشفى" : "Hospital name"}
                    />
                    <input
                      type="email"
                      placeholder={isArabic ? "البريد الإلكتروني" : "Email"}
                    />
                    <button
                      className="primary-btn landing-primary"
                      type="submit"
                    >
                      {demoRequested
                        ? isArabic
                          ? "تم الإرسال"
                          : "Sent"
                        : copy.primary}{" "}
                      <ArrowRight size={16} />
                    </button>
                  </form>
                  {demoRequested && (
                    <div className="contact-success" role="status">
                      <ShieldCheck size={15} /> {t("demoRequestSent")}
                    </div>
                  )}
                  <div className="contact-note">
                    {isArabic ? "أو" : "Or"}{" "}
                    <button className="text-link" onClick={() => onEnter()}>
                      {isArabic
                        ? "افتح مساحة العمل التجريبية"
                        : "open the demo workspace"}
                    </button>
                  </div>
                </div>
                <div className="info-grid">
                  <div className="info-panel">
                    <small>{isArabic ? "ما الذي يحدث بعد الإرسال؟" : "What happens next"}</small>
                    <h4>{isArabic ? "محادثة قصيرة حول سير العمل" : "A focused workflow conversation"}</h4>
                    <p>{isArabic ? "نراجع احتياجات فريقك، الأقسام المعنية، ونطاق التجربة قبل أي عرض للمنتج." : "We review your team structure, operational needs, and pilot scope before a product walkthrough."}</p>
                  </div>
                  <div className="info-panel">
                    <small>{isArabic ? "مصمم للفرق الطبية" : "Built for care teams"}</small>
                    <h4>{isArabic ? "خصوصية، وضوح، ومسؤولية" : "Privacy, clarity, and ownership"}</h4>
                    <p>{isArabic ? "نبدأ ببيانات تجريبية ونبقي القرار والصلاحيات والمراجعة بيد فريقك." : "Start with synthetic data while your team keeps control of access, review, and final decisions."}</p>
                  </div>
                </div>
              </div>
            ) : (
              <div className="info-grid">
                <div className="info-panel">
                  <small>{isArabic ? "CareOS" : "CareOS"}</small>
                  <h4>{page === "contact" ? copy.primary : copy.title}</h4>
                  <p>{copy.detail}</p>
                  <button
                    className="primary-btn landing-primary"
                    onClick={() => onEnter()}
                  >
                    {t("enterPlatform")} <ArrowRight size={15} />
                  </button>
                </div>
              </div>
            )}
          </div>
        </main>
      )}
    </div>
  );
}
