# --- Содержимое файла: src/transcribe-service/main.py ---
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

app = FastAPI()

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
MODEL = "nova-2"
LANGUAGE = "ru"


class TranscribeResponse(BaseModel):
    text: str


def convert_to_mp3(input_path: str) -> str:
    """Конвертация в mp3 через ffmpeg"""
    output_path = f"{input_path}.mp3"
    try:
        command = [
            "ffmpeg",
            "-y",
            "-i",
            input_path,
            "-vn",
            "-acodec",
            "libmp3lame",
            "-q:a",
            "2",
            "-loglevel",
            "error",
            output_path,
        ]
        subprocess.run(command, check=True)
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"FFmpeg error: {e}")
        return input_path


async def send_to_deepgram(audio_path: str) -> str:
    if not DEEPGRAM_API_KEY:
        raise HTTPException(status_code=500, detail="DEEPGRAM_API_KEY not set")

    url = "https://api.deepgram.com/v1/listen"
    params = {
        "model": MODEL,
        "language": LANGUAGE,
        "smart_format": "true",
        "punctuate": "true",
        "diarize": "false",
    }
    headers = {
        "Authorization": f"Token {DEEPGRAM_API_KEY}",
        "Content-Type": "audio/*",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        with open(audio_path, "rb") as f:
            audio_data = f.read()

        response = await client.post(
            url, params=params, headers=headers, content=audio_data
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code, detail=response.text
            )

        data = response.json()

        try:
            transcript = data["results"]["channels"][0]["alternatives"][0][
                "transcript"
            ]
            return transcript
        except (KeyError, IndexError):
            return ""


@app.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(file: UploadFile = File(...)):
    with tempfile.NamedTemporaryFile(
        delete=False, suffix=Path(file.filename).suffix
    ) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    converted_path = None
    try:
        converted_path = convert_to_mp3(tmp_path)
        text = await send_to_deepgram(converted_path)
        return {"text": text}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        # Чистка
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        if (
            converted_path
            and converted_path != tmp_path
            and os.path.exists(converted_path)
        ):
            os.remove(converted_path)


@app.get("/health")
def health():
    return {"status": "ok"}
