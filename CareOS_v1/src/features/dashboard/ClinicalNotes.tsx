import { useEffect, useRef, useState } from "react";
import { FileText, Mic, Save, Square, Upload } from "lucide-react";
import {
  createClinicalNote,
  generateClinicalSummary,
} from "../../api/clinical";
import {
  getEncounter,
  getTranscript,
  reviewTranscript,
  transcribeRecording,
  uploadEncounterRecording,
  type ApiEncounter,
  type ApiTranscript,
} from "../../api";
import { PageHeading } from "../../components/PageHeading";
import { PanelHeading } from "../../components/PanelHeading";
import type { TranslationKey } from "../../i18n";

type Translator = (key: TranslationKey) => string;

export function ClinicalNotes({ t }: { t: Translator }) {
  const [encounter, setEncounter] = useState<ApiEncounter | null>(null);
  const [transcript, setTranscript] = useState<ApiTranscript | null>(null);
  const [body, setBody] = useState("");
  const [summary, setSummary] = useState("");
  const [noteId, setNoteId] = useState<string | null>(null);
  const [status, setStatus] = useState(t("recordingReady"));
  const [error, setError] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);
  const [saving, setSaving] = useState(false);
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);

  useEffect(() => {
    const id = localStorage.getItem("careos-active-encounter-id");
    if (!id) {
      setError(t("startEncounterRequired"));
      return;
    }
    getEncounter(id)
      .then(setEncounter)
      .catch((reason: unknown) =>
        setError(
          reason instanceof Error
            ? reason.message
            : "Could not load encounter.",
        ),
      );
  }, []);

  const stopAndUpload = () => {
    recorder.current?.stop();
    setRecording(false);
  };
  const startRecording = async () => {
    if (!encounter) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const next = new MediaRecorder(stream, { mimeType: "audio/webm" });
      chunks.current = [];
      next.ondataavailable = (event) => {
        if (event.data.size) chunks.current.push(event.data);
      };
      next.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        const blob = new Blob(chunks.current, { type: "audio/webm" });
        setStatus(t("uploadingRecording"));
        setError(null);
        try {
          const uploaded = await uploadEncounterRecording(encounter.id, blob);
          setStatus(t("transcribing"));
          await transcribeRecording(uploaded.id);
          let nextTranscript = await getTranscript(uploaded.transcript_id);
          for (
            let attempt = 0;
            attempt < 12 &&
            !["COMPLETED", "FAILED"].includes(nextTranscript.status);
            attempt += 1
          ) {
            await new Promise((resolve) => window.setTimeout(resolve, 1000));
            nextTranscript = await getTranscript(uploaded.transcript_id);
          }
          setTranscript(nextTranscript);
          if (nextTranscript.status !== "COMPLETED")
            throw new Error(
              nextTranscript.error_code === "SPEECH_TO_TEXT_NOT_CONFIGURED"
                ? "Speech-to-text service is not configured."
                : "Transcription could not be completed.",
            );
          setBody(nextTranscript.transcript_text || "");
          setStatus(t("transcriptReady"));
        } catch (reason: unknown) {
          setStatus(t("transcriptionFailed"));
          setError(
            reason instanceof Error
              ? reason.message
              : "Speech-to-text service is unavailable.",
          );
        }
      };
      recorder.current = next;
      next.start();
      setRecording(true);
      setStatus(t("recording"));
      setError(null);
    } catch (reason: unknown) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Microphone permission is required.",
      );
    }
  };

  const saveDraft = async () => {
    if (!encounter || !body.trim()) return null;
    setSaving(true);
    setError(null);
    try {
      if (transcript) {
        const reviewed = await reviewTranscript(transcript.id, body.trim());
        setTranscript((current) =>
          current
            ? {
                ...current,
                transcript_text: reviewed.transcript_text,
                status: reviewed.status,
              }
            : current,
        );
      }
      const note = await createClinicalNote({
        patient_id: encounter.patient_id,
        encounter_id: encounter.id,
        body: body.trim(),
      });
      setNoteId(note.id);
      setStatus(t("draftSaved"));
      return note.id;
    } catch (reason: unknown) {
      setError(
        reason instanceof Error ? reason.message : "Could not save draft.",
      );
      return null;
    } finally {
      setSaving(false);
    }
  };
  const generateDraft = async () => {
    const id = noteId || (await saveDraft());
    if (!id) return;
    setSaving(true);
    try {
      const note = await generateClinicalSummary(id);
      setSummary(note.summary || note.ai_draft || "");
      setStatus(t("aiDraftReady"));
    } catch (reason: unknown) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Could not generate AI draft.",
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <PageHeading
        eyebrow={t("notes")}
        title={t("notes")}
        detail={
          encounter
            ? `${t("activeEncounter")} · ${encounter.encounter_type}`
            : t("encounterRequired")
        }
      />
      <div className="notes-layout">
        <section className="panel">
          <PanelHeading
            title={t("secureVoiceRecording")}
            detail={t("privateAudioDetail")}
          />
          {encounter ? (
            <>
              <div className="voice-status" role="status">
                <span
                  className={`voice-pulse ${recording ? "is-listening" : ""}`}
                />{" "}
                {status}
              </div>
              <div className="notes-actions">
                <button
                  type="button"
                  className={`outline-btn voice-input-button ${recording ? "is-listening" : ""}`}
                  onClick={() =>
                    recording ? stopAndUpload() : void startRecording()
                  }
                >
                  {recording ? <Square size={15} /> : <Mic size={15} />}{" "}
                  {recording ? t("stopRecording") : t("startRecording")}
                </button>
                {transcript && (
                  <span className="status confirmed">
                    <Upload size={14} /> {transcript.language} ·{" "}
                    {transcript.confidence
                      ? `${Math.round(transcript.confidence * 100)}%`
                      : t("review")}
                  </span>
                )}
              </div>
            </>
          ) : (
            <div className="empty-state">{t("noActiveEncounter")}</div>
          )}
          {error && (
            <div className="inline-error" role="alert">
              {error}
            </div>
          )}
        </section>
        <section className="panel">
          <PanelHeading
            title={t("transcriptReview")}
            detail={t("transcriptReviewDetail")}
          />
          <label className="transcript-editor-label" htmlFor="clinical-transcript">
            <FileText size={16} /> {t("transcriptNoteLabel")}
          </label>
          <textarea
            id="clinical-transcript"
            className="transcript-editor"
            dir={body ? "auto" : undefined}
            value={body}
            onChange={(event) => setBody(event.target.value)}
            rows={10}
            placeholder={t("transcriptPlaceholder")}
          />
          <div className="notes-actions">
            <button
              className="outline-btn"
              disabled={!body.trim() || saving}
              onClick={() => void saveDraft()}
            >
              <Save size={15} /> {t("saveDraft")}
            </button>
            <button
              className="primary-btn"
              disabled={!body.trim() || saving}
              onClick={() => void generateDraft()}
            >
              {saving ? t("working") : t("generateAiDraft")}
            </button>
          </div>
        </section>
        <section className="panel">
          <PanelHeading
            title={t("aiDraftTitle")}
            detail={t("aiDraftDetail")}
          />
          <div className="ai-summary-box">
            {summary || t("noAiDraft")}
          </div>
          {summary && (
            <span className="status pending">
              {t("clinicianReviewRequired")}
            </span>
          )}
        </section>
      </div>
    </>
  );
}
