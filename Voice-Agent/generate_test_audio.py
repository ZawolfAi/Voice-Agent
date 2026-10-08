import os
import subprocess
import wave
import struct
import math
from gtts import gTTS

AUDIO_DIR = "test_audio"

PHRASES = {
    # Booking
    "booking_01_request.wav": "عايز احجز ميعاد جلدية",
    "booking_02_evening.wav": "عايز ميعاد مسائي",
    "booking_03_confirm.wav": "تمام احجزه",

    # Follow-up
    "followup_01_request.wav": "عايز أتابع مع الدكتور بخصوص حالتي",
    "followup_02_status.wav": "ممكن تقولي آخر متابعة ليا",
    "followup_03_confirm.wav": "تمام"
}

def verify_wav(path: str):
    with wave.open(path, "rb") as w:
        n_channels = w.getnchannels()
        sampwidth = w.getsampwidth()
        framerate = w.getframerate()
        n_frames = w.getnframes()
        duration = n_frames / framerate if framerate else 0
        pcm_bytes = w.readframes(n_frames)
        samples = struct.unpack(f"<{len(pcm_bytes)//2}h", pcm_bytes)
        max_amp = max(abs(s) for s in samples) if samples else 0
        rms = math.sqrt(sum(s**2 for s in samples) / len(samples)) if samples else 0

    print(f"  [VERIFIED {os.path.basename(path)}]: {framerate}Hz, {n_channels}ch, {sampwidth*8}-bit, duration={duration:.2f}s, size={len(pcm_bytes)}b, max_amp={max_amp}, rms={rms:.1f}")
    assert n_channels == 1, "Must be mono"
    assert sampwidth == 2, "Must be 16-bit"
    assert framerate == 16000, "Must be 16kHz"
    assert len(pcm_bytes) > 0, "WAV must contain PCM data"
    assert max_amp > 100, "Audio amplitude too low"

def generate_speech_wav(filename: str, text: str):
    out_path = os.path.join(AUDIO_DIR, filename)
    print(f"Generating '{text}' -> {out_path}...")
    temp_mp3 = f"{out_path}.temp.mp3"

    tts = gTTS(text=text, lang="ar")
    tts.save(temp_mp3)

    # Convert MP3 to 16kHz mono 16-bit PCM WAV + append 1.5s trailing silence
    cmd = [
        "ffmpeg", "-y",
        "-i", temp_mp3,
        "-af", "apad=pad_dur=1.5",
        "-ar", "16000", "-ac", "1", "-sample_fmt", "s16",
        out_path
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if os.path.exists(temp_mp3):
        os.remove(temp_mp3)

    verify_wav(out_path)

def main():
    os.makedirs(AUDIO_DIR, exist_ok=True)
    for filename, text in PHRASES.items():
        out_path = os.path.join(AUDIO_DIR, filename)
        generate_speech_wav(filename, text)

if __name__ == "__main__":
    main()
