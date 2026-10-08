import { request } from "./client";

export type GeneralChatResponse = {
  answer: string;
  sources: Array<{ title?: string; page?: string }>;
  provider: string;
};

export type GuestVoiceResponse = GeneralChatResponse & {
  transcript: string;
  speech_provider: string;
};

export function askGeneralChat(message: string): Promise<GeneralChatResponse> {
  return request<GeneralChatResponse>("/assistant/chat", {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}

export function askGuestChat(message: string): Promise<GeneralChatResponse> {
  return request<GeneralChatResponse>("/assistant/guest-chat", {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}

export function askGuestVoice(
  audioBase64: string,
  language: "ar-EG" | "en-US",
): Promise<GuestVoiceResponse> {
  return request<GuestVoiceResponse>("/assistant/guest-voice", {
    method: "POST",
    body: JSON.stringify({
      audio_base64: audioBase64,
      content_type: "audio/webm",
      language,
    }),
  });
}
