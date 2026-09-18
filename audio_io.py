import numpy as np
import sounddevice as sd
from scipy.io.wavfile import write as write_wav
from openai import OpenAI
from config import (
    SAMPLE_RATE,
    MAX_RECORD_SECONDS,
    VAD_BLOCK_MS,
    VAD_SILENCE_THRESHOLD,
    VAD_SILENCE_DURATION_S,
    VAD_MIN_SPEECH_DURATION_S,
    STT_MODEL,
    TTS_MODEL,
    TTS_VOICE,
    TTS_FORMAT,
    TTS_CHUNK_SIZE,
    TMP_RECORDING_PATH,
)

client = OpenAI()

def record_audio(no_speech_timeout_s: float | None = None) -> str | None:
    """Record from the mic until the user stops talking (VAD), then save to disk.

    If no_speech_timeout_s is set and the user never starts speaking within
    that window, returns None instead of a path - used to auto-end a
    conversation when it's gone quiet.

    Falls back to MAX_RECORD_SECONDS as a hard cap so a stuck-open mic or a
    noisy room that never reads as "silent" can't record forever.
    """
    block_size = int(SAMPLE_RATE * VAD_BLOCK_MS / 1000)
    silence_blocks_needed = int(VAD_SILENCE_DURATION_S * 1000 / VAD_BLOCK_MS)
    min_speech_blocks = int(VAD_MIN_SPEECH_DURATION_S * 1000 / VAD_BLOCK_MS)
    max_blocks = int(MAX_RECORD_SECONDS * 1000 / VAD_BLOCK_MS)
    no_speech_timeout_blocks = (
        int(no_speech_timeout_s * 1000 / VAD_BLOCK_MS) if no_speech_timeout_s else None
    )

    recorded_chunks = []
    speech_block_count = 0
    silence_block_count = 0
    has_started_speaking = False

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=block_size
    )
    with stream:
        for block_index in range(max_blocks):
            block, _ = stream.read(block_size)
            recorded_chunks.append(block.copy())

            rms = np.sqrt(np.mean(block.astype(np.float32) ** 2))

            if rms >= VAD_SILENCE_THRESHOLD:
                speech_block_count += 1
                silence_block_count = 0
                if speech_block_count >= min_speech_blocks:
                    has_started_speaking = True
            else:
                if has_started_speaking:
                    silence_block_count += 1
                    if silence_block_count >= silence_blocks_needed:
                        break
                elif (
                    no_speech_timeout_blocks is not None
                    and block_index >= no_speech_timeout_blocks
                ):
                    return None  # gone quiet before ever speaking - give up

    audio = np.concatenate(recorded_chunks, axis=0)
    write_wav(TMP_RECORDING_PATH, SAMPLE_RATE, audio)
    return TMP_RECORDING_PATH


def transcribe(audio_path: str) -> str:
    """Send recorded audio to the STT model and return the transcribed text."""
    with open(audio_path, "rb") as f:
        result = client.audio.transcriptions.create(
            model=STT_MODEL,
            file=f,
        )
    return result.text.strip()


def speak(text: str) -> None:
    """Convert text to speech and play it back as audio streams in, chunk by chunk."""
    if not text or not text.strip():
        print("Nova: (no reply text - skipping speech)")
        return

    print(f"Nova: {text}")

    playback_stream = sd.RawOutputStream(
        samplerate=24000,  # OpenAI TTS PCM output is 24kHz
        channels=1,
        dtype="int16",
    )
    playback_stream.start()

    with client.audio.speech.with_streaming_response.create(
        model=TTS_MODEL,
        voice=TTS_VOICE,
        input=text,
        response_format=TTS_FORMAT,
    ) as response:
        for chunk in response.iter_bytes(chunk_size=TTS_CHUNK_SIZE):
            if chunk:
                playback_stream.write(chunk)

    playback_stream.stop()
    playback_stream.close()