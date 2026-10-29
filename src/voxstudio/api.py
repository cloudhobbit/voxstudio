"""The HTTP API. Local only: binds 127.0.0.1 and refuses other hosts and origins on writes."""
import logging
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
import soundfile as sf
from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import NAME, __version__, pronounce
from .cache import AudioCache, make_key
from .catalogue import BLENDS, SAMPLE_LINES, VOICES, grade_note
from .engines import load_engine
from .fx import EFFECTS, SAMPLE_RATE, SPACES, Capabilities, apply_chain
from .jobs import JobManager
from .specs import SpecError, describe, parse_voice
from .worker import TTSWorker
from .workspace import Conflict, NotFound, Workspace, etag

APP_DIR = Path(__file__).resolve().parent / "app"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
log = logging.getLogger("voxstudio")


class SpeakIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    voice: str = "af_heart"
    speed: float = Field(1.0, ge=0.5, le=2.0)
    pitch: float = Field(0, ge=-12, le=12)       # semitones
    effect: str = "none"
    space: str = "dry"
    project: str | None = None                  # adds that project's pronunciations
    pronounce: bool = True


class PatchVoice(BaseModel):
    favourite: bool | None = None
    rating: int | None = None
    tags: list[str] | None = None
    display_name: str | None = None
    etag: str | None = None


class SignatureIn(BaseModel):
    mix: str
    speed: float = Field(1.0, ge=0.5, le=2.0)
    pitch: float = Field(0, ge=-12, le=12)
    note: str = Field("", max_length=200)
    overwrite: bool = False
    etag: str | None = None


class RenameIn(BaseModel):
    new_name: str
    etag: str | None = None


class PresetIn(BaseModel):
    voice: str
    speed: float = Field(1.0, ge=0.5, le=2.0)
    pitch: float = Field(0, ge=-12, le=12)
    effect: str = "none"
    space: str = "dry"
    etag: str | None = None


class PronunciationIn(BaseModel):
    say: str = Field(min_length=1, max_length=120)
    project: str | None = None
    etag: str | None = None


class PreviewIn(BaseModel):
    text: str = Field(max_length=20000)
    project: str | None = None


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    script: str | None = Field(None, max_length=200000)   # pasted text, split into blocks on blank lines
    voice: str = "af_heart"


class ProjectIn(BaseModel):
    title: str | None = None
    blocks: list[dict] | None = None
    pronunciations: dict | None = None
    etag: str | None = None


def split_script(text: str) -> list[str]:
    paras = [p.strip() for p in text.replace("\r", "").split("\n\n")]
    return [" ".join(p.split()) for p in paras if p]


def create_app(workspace: Workspace, engine_name: str = "kokoro", worker: TTSWorker | None = None,
               extra_hosts: set[str] = frozenset(), caps: Capabilities | None = None) -> FastAPI:
    ws = workspace
    cache = AudioCache(ws.cache_dir)
    worker = worker or TTSWorker(load_engine(engine_name))
    jobs = JobManager(log)
    caps = caps or Capabilities.detect()
    allowed = LOCAL_HOSTS | set(extra_hosts)

    app = FastAPI(title=NAME, version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.worker, app.state.cache, app.state.workspace = worker, cache, ws

    # ---- security and logging ---------------------------------------------------------

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        if request.url.hostname not in allowed:  # blocks DNS rebinding: another site's name pointing at 127.0.0.1
            return JSONResponse({"detail": f"{NAME} only answers on localhost"}, status_code=403)
        origin = request.headers.get("origin")
        if request.method not in ("GET", "HEAD", "OPTIONS") and origin and urlsplit(origin).hostname not in allowed:
            return JSONResponse({"detail": "Cross-site requests are not allowed"}, status_code=403)
        started = time.time()
        response = await call_next(request)
        log.info("%s %s %s %.0fms", request.method, request.url.path, response.status_code, (time.time() - started) * 1000)
        return response

    @app.exception_handler(ValueError)
    async def bad_value(_, e: ValueError):
        return JSONResponse({"detail": str(e)}, status_code=422)

    @app.exception_handler(Conflict)
    async def conflict(_, e: Conflict):
        return JSONResponse({"detail": str(e), "etag": e.etag, "current": e.current}, status_code=409)

    @app.exception_handler(NotFound)
    async def not_found(_, e: NotFound):
        return JSONResponse({"detail": f"Not found: {e}"}, status_code=404)

    # ---- helpers ---------------------------------------------------------------------------

    def sigs() -> dict:
        return ws.signatures.entries()[0]

    def check_sound(effect: str, space: str) -> None:
        if effect not in EFFECTS:
            raise ValueError(f"Unknown effect '{effect}' (use {', '.join(EFFECTS)})")
        if space not in SPACES:
            raise ValueError(f"Unknown space '{space}' (use {', '.join(SPACES)})")

    def finish(key: str, audio: np.ndarray, inputs: dict, pitch: float, effect: str, space: str, extra: dict) -> dict:
        """pitch + effect + space through ffmpeg (when needed), into the cache."""
        if not pitch and effect == "none" and space == "dry":
            return cache.put(key, audio, inputs, extra)
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "raw.wav"
            sf.write(raw, audio, SAMPLE_RATE, subtype="FLOAT")
            apply_chain(raw, cache.wav(key), pitch, effect, space, caps)
        return cache.put_file(key, inputs, extra)

    def render(text: str, voice: str, speed: float, pitch: float, effect: str, space: str,
               project: str | None, pronounce_: bool) -> dict:
        parts = parse_voice(voice, sigs())
        check_sound(effect, space)
        spoken = pronounce.apply(text, ws.pronunciation_table(project)) if pronounce_ else text
        speed, pitch = float(speed), float(pitch)   # 0 and 0.0 must give the same key
        inputs = {"kind": "speech", "engine": worker.engine.name, "spoken": spoken, "voice": parts, "speed": speed,
                  "pitch": pitch, "effect": effect, "space": space, "fx": "rb" if caps.rubberband else "ar"}
        key = make_key(**inputs)
        meta = cache.meta(key)
        if meta:
            return {"key": key, "url": f"/audio/{key}.wav", "duration": meta["duration"], "cached": True,
                    "queued_ahead": 0, "words": meta.get("words", [])}
        ahead = worker.queued
        audio, words = worker.speak_timed(spoken, parts, speed)
        meta = finish(key, audio, inputs, pitch, effect, space, {"text": text, "words": words})
        return {"key": key, "url": f"/audio/{key}.wav", "duration": meta["duration"], "cached": False,
                "queued_ahead": ahead, "words": words}

    app.state.render = render

    def sample_for(voice: str, text: str, speed: float = 1.0, pitch: float = 0.0) -> dict | None:
        """The cached sample of `text` in this voice, if it was rendered before (no rendering here)."""
        try:
            parts = parse_voice(voice, sigs())
        except SpecError:
            return None
        spoken = pronounce.apply(text, ws.pronunciation_table(None))
        key = make_key(kind="speech", engine=worker.engine.name, spoken=spoken, voice=parts, speed=float(speed),
                       pitch=float(pitch), effect="none", space="dry", fx="rb" if caps.rubberband else "ar")
        meta = cache.meta(key)
        return {"url": f"/audio/{key}.wav", "duration": meta["duration"]} if meta else None

    def voice_entries(text: str | None = None) -> list[dict]:
        notes, _ = ws.library.load()
        signatures = sigs()
        usage = ws.projects.voice_usage()
        out = []
        for vid, v in VOICES.items():
            out.append({"id": vid, "kind": "stock", "name": v["name"], "accent": v["accent"], "language": v["language"],
                        "gender": v["gender"], "grade": v["grade"], "grade_note": grade_note(v["grade"]),
                        "character": v["character"], "uses": v["uses"]})
        for spec, note in BLENDS.items():
            out.append({"id": spec, "kind": "blend", "name": describe(spec), "character": note, "uses": [],
                        "mix": spec, "accent": "", "gender": "", "grade": ""})
        for name, entry in signatures.items():
            try:
                shown = describe(entry["mix"])
            except SpecError:
                shown = entry["mix"]
            out.append({"id": f"@{name}", "kind": "signature", "name": name, "character": entry["note"], "uses": [],
                        "mix": entry["mix"], "described": shown, "speed": entry["speed"], "pitch": entry["pitch"],
                        "accent": "", "gender": "", "grade": ""})
        for v in out:
            v.update({k: val for k, val in (notes.get(v["id"]) or {}).items()})
            v.setdefault("favourite", False)
            v.setdefault("rating", 0)
            v.setdefault("tags", [])
            v["used_in"] = usage.get(v["id"], [])
            if text:
                v["sample"] = sample_for(v["id"], text, v.get("speed", 1.0), v.get("pitch", 0.0))
        return out

    # ---- routes: health, catalogue, speech ----------------------------------------------------

    @app.get("/api/health")
    def health():
        return {"ok": True, "name": NAME, "version": __version__, "engine": worker.engine.name,
                "languages": worker.languages, "warm_error": worker.warm_error, "queue": worker.queued,
                "cache": cache.stats(), "workspace": str(ws.root),
                "capabilities": {"ffmpeg": caps.ffmpeg, "ffmpeg_version": caps.version, "rubberband": caps.rubberband,
                                 "mp3": caps.mp3}}

    @app.get("/api/voices")
    def voices(text: str | None = Query(None, max_length=2000)):
        """The catalogue. With ?text=, each voice carries `sample` (url, duration) when that line is already cached."""
        return {"voices": voice_entries(text), "etag": etag(ws.library.path)}

    @app.patch("/api/voices/{voice_id:path}")
    def patch_voice(voice_id: str, body: PatchVoice):
        known = set(VOICES) | set(BLENDS) | {f"@{n}" for n in sigs()}
        if voice_id not in known:
            raise NotFound(voice_id)
        fields = body.model_dump(exclude={"etag"}, exclude_unset=True)
        return {"entry": ws.library.patch(voice_id, fields, body.etag), "etag": etag(ws.library.path)}

    @app.get("/api/sample-lines")
    def sample_lines():
        return {"lines": SAMPLE_LINES}

    @app.get("/api/effects")
    def effects():
        return {"effects": [{"id": k, "description": d} for k, (d, _, _) in EFFECTS.items()],
                "spaces": [{"id": k, "description": d} for k, (d, _) in SPACES.items()]}

    @app.post("/api/speak")
    def speak(req: SpeakIn):
        return render(req.text, req.voice, req.speed, req.pitch, req.effect, req.space, req.project, req.pronounce)

    @app.post("/api/speak/batch")
    def speak_batch(reqs: list[SpeakIn]):
        if not 1 <= len(reqs) <= 500:
            raise ValueError("Send 1-500 lines per batch")

        def run(job):
            for i, r in enumerate(reqs):
                try:
                    job.urls.append(render(r.text, r.voice, r.speed, r.pitch, r.effect, r.space, r.project, r.pronounce)["url"])
                except Exception as e:
                    job.urls.append(None)
                    job.failed.append({"index": i, "error": str(e)})
                job.done += 1

        return {"job_id": jobs.start("speak-batch", len(reqs), run).id}

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str):
        found = jobs.get(job_id)
        if not found:
            raise NotFound(job_id)
        return found

    @app.get("/audio/{name}")
    def audio(name: str):
        key, _, ext = name.rpartition(".")
        if ext not in ("wav",) or not cache.is_key(key) or not cache.wav(key).exists():
            raise NotFound(name)
        return FileResponse(cache.wav(key), media_type="audio/wav",
                            headers={"Cache-Control": "public, max-age=31536000, immutable"})

    # ---- signatures and presets -------------------------------------------------------------

    @app.get("/api/signatures")
    def list_signatures():
        data, tag = ws.signatures.entries()
        out = []
        for name, entry in sorted(data.items()):
            try:
                shown = describe(entry["mix"])
            except SpecError:
                shown = entry["mix"]
            out.append({"name": name, **entry, "described": shown, "used_in": ws.projects.uses_voice(f"@{name}")})
        return {"signatures": out, "etag": tag}

    @app.put("/api/signatures/{name}")
    def put_signature(name: str, body: SignatureIn):
        tag = ws.signatures.put(name, body.mix, body.speed, body.pitch, body.note, body.etag, body.overwrite)
        return {"name": name, "etag": tag}

    @app.post("/api/signatures/{name}/rename")
    def rename_signature(name: str, body: RenameIn):
        new = body.new_name.strip()
        tag = ws.signatures.rename(name, new, body.etag)
        updated = []
        for slug in ws.projects.uses_voice(f"@{name}"):
            data, ptag = ws.projects.load(slug)
            for b in data["blocks"]:
                if b.get("voice") == f"@{name}":
                    b["voice"] = f"@{new}"
            ws.projects.save(slug, data, sigs(), ptag)
            updated.append(slug)
        return {"name": new, "etag": tag, "updated_projects": updated}

    @app.delete("/api/signatures/{name}")
    def delete_signature(name: str, etag_: str | None = Query(None, alias="etag")):
        return {"deleted": name, "etag": ws.signatures.delete(name, etag_, ws.projects.uses_voice(f"@{name}"))}

    @app.get("/api/presets")
    def list_presets():
        data, tag = ws.presets.load()
        return {"presets": [{"name": n, **p} for n, p in sorted(data.items())], "etag": tag}

    @app.put("/api/presets/{name}")
    def put_preset(name: str, body: PresetIn):
        parse_voice(body.voice, sigs())
        check_sound(body.effect, body.space)
        return {"name": name, "etag": ws.presets.put(name, body.model_dump(exclude={"etag"}), body.etag)}

    @app.delete("/api/presets/{name}")
    def delete_preset(name: str, etag_: str | None = Query(None, alias="etag")):
        return {"deleted": name, "etag": ws.presets.delete(name, etag_)}

    # ---- pronunciations -----------------------------------------------------------------------

    @app.get("/api/pronunciations")
    def get_pronunciations(scope: str = "shared", project: str | None = None):
        shared, tag = ws.pronunciations.load()
        if scope == "shared":
            data = shared
        elif scope == "project" and project:
            full, tag = ws.projects.load(project)
            data = full.get("pronunciations") or {}
        else:
            raise ValueError("scope must be 'shared', or 'project' with project=<slug>")
        entries = [{"word": w, "say": str(s), "type": "phonemes" if str(s).startswith("/") else "respelling",
                    "overrides_shared": scope == "project" and w in shared}
                   for w, s in sorted(data.items(), key=lambda kv: kv[0].lower())]
        return {"entries": entries, "etag": tag}

    @app.put("/api/pronunciations/{scope}/{word}")
    def put_pronunciation(scope: str, word: str, body: PronunciationIn):
        return {"etag": _set_pron(scope, word, body.say, body.project, body.etag)}

    @app.delete("/api/pronunciations/{scope}/{word}")
    def delete_pronunciation(scope: str, word: str, project: str | None = None,
                             etag_: str | None = Query(None, alias="etag")):
        return {"etag": _set_pron(scope, word, None, project, etag_)}

    def _set_pron(scope, word, say, project, sent):
        if scope == "shared":
            return ws.pronunciations.put(word, say, sent)
        if scope == "project" and project:
            data, _ = ws.projects.load(project)
            table = dict(data.get("pronunciations") or {})
            if say is None:
                if word not in table:
                    raise NotFound(word)
                table.pop(word)
            else:
                table[word.strip()] = say.strip()
            data["pronunciations"] = table
            return ws.projects.save(project, data, sigs(), sent)[1]
        raise ValueError("scope must be 'shared', or 'project' with project=<slug>")

    @app.post("/api/pronunciations/preview")
    def preview_pronunciations(body: PreviewIn):
        return {"hits": pronounce.preview(body.text, ws.pronunciation_table(body.project))}

    # ---- projects ---------------------------------------------------------------------------------

    def project_out(slug: str) -> dict:
        data, tag = ws.projects.load(slug)
        return {"slug": slug, **data, "etag": tag}

    @app.get("/api/projects")
    def list_projects():
        out = []
        for slug in ws.projects.names():
            data, _ = ws.projects.load(slug)
            out.append({"slug": slug, "title": data["title"], "blocks": len(data["blocks"]),
                        "words": sum(len(str(b.get("text", "")).split()) for b in data["blocks"]),
                        "created": str(data.get("created", ""))})
        return {"projects": out}

    @app.post("/api/projects", status_code=201)
    def create_project(body: ProjectCreate):
        parse_voice(body.voice, sigs())
        blocks = [{"id": f"b{i + 1}", "text": t, "voice": body.voice} for i, t in enumerate(split_script(body.script or ""))]
        slug = ws.projects.create(body.title.strip(), blocks)
        if blocks:
            data, tag = ws.projects.load(slug)
            ws.projects.save(slug, data, sigs(), tag)  # normalises the blocks
        return project_out(slug)

    @app.get("/api/projects/{slug}")
    def get_project(slug: str):
        return project_out(slug)

    @app.put("/api/projects/{slug}")
    def put_project(slug: str, body: ProjectIn):
        data = body.model_dump(exclude={"etag"}, exclude_unset=True, exclude_none=True)
        saved, tag = ws.projects.save(slug, data, sigs(), body.etag)
        return {"slug": slug, **saved, "etag": tag}

    @app.delete("/api/projects/{slug}")
    def delete_project(slug: str):
        ws.projects.delete(slug)
        return {"deleted": slug}

    # ---- cache ----------------------------------------------------------------------------------

    @app.get("/api/cache")
    def cache_stats():
        return cache.stats()

    @app.delete("/api/cache")
    def cache_trim(older_than_days: float = 30):
        return {"removed": cache.trim(older_than_days), **cache.stats()}

    app.state.jobs = jobs
    if (APP_DIR / "index.html").exists():
        app.mount("/", StaticFiles(directory=APP_DIR, html=True), name="app")
    return app
