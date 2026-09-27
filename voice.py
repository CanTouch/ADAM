"""Adam's ears and mouth. Both run on this computer; no audio leaves it.

Listening: record from the default microphone until the user stops talking, then
transcribe with faster-whisper (the same 'base' model YAPP already downloaded).
Speaking: Piper turns the reply into a wav file, paplay plays it.
"""
import statistics
import subprocess
import threading
import wave

import numpy as np

from config import VOICES_DIR, save_setting

RATE = 16000
BLOCK = RATE // 10          # 0.1 s of audio per block
WAIT_FOR_SPEECH = 6.0       # seconds to wait for the user to start talking
END_SILENCE = 1.0           # this much quiet after speech ends the recording
MAX_SECONDS = 15
MIN_THRESHOLD = 400         # int16 RMS; room noise here measured 100-400
WHISPER_MODEL = "base"
VOICE_NAME = "en_US-lessac-medium"
REPLY_WAV = VOICES_DIR / "reply.wav"


def _rms(block):
    return float(np.sqrt(np.mean(block.astype(np.float32) ** 2)))


class Voice:
    def __init__(self, enabled=True):
        self.enabled = enabled  # speaking only; listening is always available
        self._whisper = None
        self._whisper_ready = threading.Event()
        self._piper = None
        self._player = None
        self._speak_lock = threading.Lock()
        self.listening = False
        self.level = 0.0  # loudness of the microphone while listening, 0..1

    # ---- ears ----

    def _load_whisper(self):
        if self._whisper is None:
            from faster_whisper import WhisperModel
            self._whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
        self._whisper_ready.set()

    def listen(self):
        """Record one utterance and return its text ('' if nothing was said). Blocks."""
        import sounddevice as sd
        self.listening = True
        # Load the model while recording, so the first use isn't slower to start.
        threading.Thread(target=self._load_whisper, daemon=True).start()
        self.stop_speaking()
        try:
            audio = self._record(sd)
        finally:
            self.listening = False
            self.level = 0.0
        if audio is None:
            return ""
        self._whisper_ready.wait()
        segments, _ = self._whisper.transcribe(audio, language="en", beam_size=1, vad_filter=True)
        return " ".join(s.text.strip() for s in segments).strip()

    def _record(self, sd):
        blocks, started, quiet = [], False, 0
        with sd.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=BLOCK) as stream:
            noise = [_rms(stream.read(BLOCK)[0]) for _ in range(3)]
            threshold = max(2.5 * statistics.median(noise), MIN_THRESHOLD)
            loud_run = 0
            for i in range(int(MAX_SECONDS * 10)):
                block = stream.read(BLOCK)[0][:, 0]
                blocks.append(block)
                level = _rms(block)
                self.level = min(level / (threshold * 4), 1.0)
                if not started:
                    loud_run = loud_run + 1 if level > threshold else 0
                    if loud_run >= 2:
                        started = True
                        blocks = blocks[-5:]  # keep a little audio from just before speech
                    elif i >= WAIT_FOR_SPEECH * 10:
                        return None
                    elif len(blocks) > 5:
                        blocks.pop(0)
                    continue
                quiet = quiet + 1 if level < threshold * 0.8 else 0
                if quiet >= END_SILENCE * 10:
                    break
        return np.concatenate(blocks).astype(np.float32) / 32768.0

    # ---- mouth ----

    def _load_piper(self):
        if self._piper is None:
            from piper import PiperVoice
            self._piper = PiperVoice.load(str(VOICES_DIR / f"{VOICE_NAME}.onnx"))
        return self._piper

    def warm_up(self):
        """Load the voice in the background so the first reply isn't 7 seconds late."""
        def load():
            with self._speak_lock:
                try:
                    self._load_piper()
                except Exception as e:
                    print(f"Voice error: {e}")
        if self.enabled:
            threading.Thread(target=load, daemon=True).start()

    def set_enabled(self, on):
        self.enabled = on
        save_setting("speak_replies", on)
        if not on:
            self.stop_speaking()

    def speak(self, text):
        """Say text in the background, cutting off anything still playing."""
        if not self.enabled:
            return
        threading.Thread(target=self._speak, args=(text,), daemon=True).start()

    def _speak(self, text):
        with self._speak_lock:
            self.stop_speaking()
            try:
                voice = self._load_piper()
                with wave.open(str(REPLY_WAV), "wb") as wav:
                    voice.synthesize_wav(text, wav)
                if self.listening:  # Super+A was pressed while this was being prepared
                    return
                self._player = subprocess.Popen(["paplay", str(REPLY_WAV)])
            except Exception as e:
                print(f"Voice error: {e}")

    @property
    def speaking(self):
        return self._player is not None and self._player.poll() is None

    def stop_speaking(self):
        if self._player and self._player.poll() is None:
            self._player.terminate()
