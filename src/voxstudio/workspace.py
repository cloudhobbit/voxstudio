"""The workspace: one folder of plain YAML files that the app and your scripts share.

    <workspace>/
      library.yaml          favourites, ratings, tags, display names per voice
      signatures.yaml       named voice mixes, used as "@name"
      pronunciations.yaml   how to say words, shared by every project
      presets.yaml          saved Workbench settings
      projects/<slug>/project.yaml
      cache/                rendered audio by content hash (safe to delete)
      exports/<slug>/       rendered projects

Every read returns an etag (modification time + size). Writes send the etag they loaded; if the file changed
on disk in between, the write is refused with Conflict instead of silently overwriting.
"""
import re
import shutil
import time
from pathlib import Path

import yaml

from .fx import EFFECTS, SPACES
from .specs import SpecError, parse_voice

SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
DEFAULT_ROOT = Path.home() / "VoxStudio"


class Conflict(Exception):
    def __init__(self, etag: str, current):
        super().__init__("The file changed on disk since it was loaded")
        self.etag, self.current = etag, current


class NotFound(Exception):
    pass


def etag(path: Path) -> str:
    if not path.exists():
        return "missing"
    st = path.stat()
    return f"{st.st_mtime_ns}-{st.st_size}"


def _check(path: Path, sent: str | None, current) -> None:
    """sent=None skips the check (the caller accepts the last write wins)."""
    if sent is not None and sent != etag(path):
        raise Conflict(etag(path), current)


def _dump(data) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False)


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:60] or "untitled"


def replace_top_level_block(text: str, key: str, data) -> str:
    """Rewrite one top-level `key:` block of a YAML file, keeping every comment and setting around it."""
    block = _dump({key: data}).rstrip("\n") if data else f"{key}: {{}}"
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if re.match(rf"^{re.escape(key)}:(\s|$)", ln)), None)
    if start is None:
        return text.rstrip("\n") + "\n\n" + block + "\n" if text.strip() else block + "\n"
    end = start + 1
    while end < len(lines) and (lines[end].startswith((" ", "\t", "-")) or not lines[end].strip()):
        if not lines[end].strip() and end + 1 < len(lines) and not lines[end + 1].startswith((" ", "\t", "-")):
            break
        end += 1
    return "\n".join(lines[:start] + block.splitlines() + lines[end:]) + "\n"


class _YamlFile:
    HEADER = ""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> tuple[dict, str]:
        data = (yaml.safe_load(self.path.read_text()) or {}) if self.path.exists() else {}
        return data, etag(self.path)

    def write(self, data: dict) -> str:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(self.HEADER + (_dump(dict(sorted(data.items()))) if data else ""))
        return etag(self.path)


class LibraryStore(_YamlFile):
    HEADER = "# Your voice notes: favourites, ratings 1-5, tags and display names, per voice id.\n"
    FIELDS = {"favourite": bool, "rating": int, "tags": list, "display_name": str}

    def patch(self, voice_id: str, fields: dict, sent_etag: str | None) -> dict:
        data, _ = self.load()
        _check(self.path, sent_etag, data)
        entry = dict(data.get(voice_id) or {})
        for k, v in fields.items():
            if k not in self.FIELDS:
                raise ValueError(f"Unknown field '{k}' (use {', '.join(self.FIELDS)})")
            if v is None or v == [] or v == "" or v is False:
                entry.pop(k, None)
                continue
            if not isinstance(v, self.FIELDS[k]):
                raise ValueError(f"'{k}' must be {self.FIELDS[k].__name__}")
            if k == "rating" and not 1 <= v <= 5:
                raise ValueError("rating must be 1-5")
            if k == "tags":
                v = sorted({str(t).strip().lower() for t in v if str(t).strip()})
            entry[k] = v
        if entry:
            data[voice_id] = entry
        else:
            data.pop(voice_id, None)
        self.write(data)
        return entry


class SignatureStore(_YamlFile):
    """signatures.yaml: name -> {mix, speed, pitch, note}. The old one-line form (name: mix) is still read."""
    HEADER = "# Signature voices: use one anywhere as voice: \"@name\".\n"

    def entries(self) -> tuple[dict, str]:
        data, tag = self.load()
        full = {}
        for name, entry in data.items():
            if isinstance(entry, dict):
                full[name] = {"mix": str(entry.get("mix", "")), "speed": float(entry.get("speed", 1.0)),
                              "pitch": float(entry.get("pitch", 0)), "note": str(entry.get("note", ""))}
            else:
                full[name] = {"mix": str(entry), "speed": 1.0, "pitch": 0.0, "note": ""}
        return full, tag

    def put(self, name: str, mix: str, speed: float, pitch: float, note: str, sent_etag: str | None,
            overwrite: bool = False) -> str:
        if not SLUG.match(name):
            raise ValueError("Signature names use lowercase letters, digits, - and _")
        if mix.strip().startswith("@"):
            raise ValueError("A signature is a mix of voices, not another signature")
        parse_voice(mix)
        data, _ = self.load()
        _check(self.path, sent_etag, data)
        if name in data and not overwrite:
            raise ValueError(f"@{name} already exists; send overwrite: true to replace it")
        data[name] = {"mix": mix.strip(), "speed": speed, "pitch": pitch, "note": note}
        return self.write(data)

    def rename(self, old: str, new: str, sent_etag: str | None) -> str:
        if not SLUG.match(new):
            raise ValueError("Signature names use lowercase letters, digits, - and _")
        data, _ = self.load()
        if old not in data:
            raise NotFound(f"@{old}")
        if new in data:
            raise ValueError(f"@{new} already exists")
        _check(self.path, sent_etag, data)
        data[new] = data.pop(old)
        return self.write(data)

    def delete(self, name: str, sent_etag: str | None, used_in: list[str]) -> str:
        data, _ = self.load()
        if name not in data:
            raise NotFound(f"@{name}")
        if used_in:
            raise ValueError(f"@{name} is used by {', '.join(used_in)}; change those first")
        _check(self.path, sent_etag, data)
        del data[name]
        return self.write(data)


class PronunciationStore(_YamlFile):
    HEADER = ("# How to say words, shared by every project (a project's own `pronunciations:` override these).\n"
              "#   Respelling:  Chandrayaan: \"Chun-druh-yaan\"\n"
              "#   Phonemes:    Pragyan: \"/pɹˈʌɡjɑn/\"      (exact sounds, between slashes)\n")

    def put(self, word: str, say: str | None, sent_etag: str | None) -> str:
        if not word.strip() or "\n" in word:
            raise ValueError("Empty or multi-line word")
        data, _ = self.load()
        _check(self.path, sent_etag, data)
        if say is None:
            if word not in data:
                raise NotFound(word)
            data.pop(word)
        else:
            data[word.strip()] = say.strip()
        return self.write(data)


class PresetStore(_YamlFile):
    HEADER = "# Workbench presets: a voice with its speed, pitch, effect and space.\n"
    FIELDS = ("voice", "speed", "pitch", "effect", "space")

    def put(self, name: str, settings: dict, sent_etag: str | None) -> str:
        if not SLUG.match(name):
            raise ValueError("Preset names use lowercase letters, digits, - and _")
        data, _ = self.load()
        _check(self.path, sent_etag, data)
        data[name] = {k: settings[k] for k in self.FIELDS if k in settings}
        return self.write(data)

    def delete(self, name: str, sent_etag: str | None) -> str:
        data, _ = self.load()
        if name not in data:
            raise NotFound(name)
        _check(self.path, sent_etag, data)
        del data[name]
        return self.write(data)


BLOCK_DEFAULTS = {"speed": 1.0, "pitch": 0.0, "effect": "none", "space": "dry", "pause": 0.5}


def normalise_block(block: dict, signatures: dict, index: int) -> dict:
    """Fill defaults and validate one script block."""
    if not isinstance(block, dict) or not str(block.get("text", "")).strip():
        raise ValueError(f"Block {index + 1} has no text")
    out = {"id": str(block.get("id") or f"b{index + 1}"), "text": str(block["text"]).strip(),
           "voice": str(block.get("voice") or "af_heart")}
    try:
        parse_voice(out["voice"], signatures)
    except SpecError as e:
        raise ValueError(f"Block {index + 1}: {e}") from None
    for k, default in BLOCK_DEFAULTS.items():
        out[k] = type(default)(block.get(k, default))
    if not 0.5 <= out["speed"] <= 2.0:
        raise ValueError(f"Block {index + 1}: speed must be 0.5-2.0")
    if not -12 <= out["pitch"] <= 12:
        raise ValueError(f"Block {index + 1}: pitch must be -12..12 semitones")
    if out["effect"] not in EFFECTS:
        raise ValueError(f"Block {index + 1}: unknown effect '{out['effect']}'")
    if out["space"] not in SPACES:
        raise ValueError(f"Block {index + 1}: unknown space '{out['space']}'")
    if not 0 <= out["pause"] <= 10:
        raise ValueError(f"Block {index + 1}: pause must be 0-10 seconds")
    return out


class ProjectStore:
    """projects/<slug>/project.yaml: a title, script blocks and project pronunciations."""
    HEADER = "# A Vox Studio project: the script as blocks, each with its voice and settings.\n"

    def __init__(self, root: Path):
        self.root = root

    def folder(self, slug: str) -> Path:
        if not SLUG.match(slug):
            raise NotFound(slug)
        folder = (self.root / slug).resolve()
        if not folder.is_relative_to(self.root.resolve()) or not (folder / "project.yaml").exists():
            raise NotFound(slug)
        return folder

    def names(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(p.name for p in self.root.iterdir() if (p / "project.yaml").exists() and SLUG.match(p.name))

    def load(self, slug: str) -> tuple[dict, str]:
        path = self.folder(slug) / "project.yaml"
        data = yaml.safe_load(path.read_text()) or {}
        data.setdefault("title", slug)
        data.setdefault("blocks", [])
        data.setdefault("pronunciations", {})
        return data, etag(path)

    def create(self, title: str, blocks: list | None = None) -> str:
        base = slugify(title)
        slug, n = base, 2
        while (self.root / slug).exists():
            slug, n = f"{base}-{n}", n + 1
        folder = self.root / slug
        folder.mkdir(parents=True)
        (folder / "project.yaml").write_text(self.HEADER + _dump({"title": title, "blocks": blocks or [],
                                                                   "pronunciations": {}, "created": time.strftime("%Y-%m-%d")}))
        return slug

    def save(self, slug: str, data: dict, signatures: dict, sent_etag: str | None) -> tuple[dict, str]:
        path = self.folder(slug) / "project.yaml"
        current, _ = self.load(slug)
        _check(path, sent_etag, current)
        title = str(data.get("title") or current["title"]).strip() or slug
        blocks = [normalise_block(b, signatures, i) for i, b in enumerate(data.get("blocks", current["blocks"]))]
        ids = [b["id"] for b in blocks]
        if len(set(ids)) != len(ids):
            raise ValueError("Block ids must be unique")
        pron = data.get("pronunciations", current["pronunciations"]) or {}
        if not isinstance(pron, dict):
            raise ValueError("pronunciations must be a mapping of word: say")
        saved = {**current, "title": title, "blocks": blocks, "pronunciations": {str(k): str(v) for k, v in pron.items()}}
        path.write_text(self.HEADER + _dump(saved))
        return saved, etag(path)

    def delete(self, slug: str) -> None:
        shutil.rmtree(self.folder(slug))

    def voice_usage(self) -> dict[str, list[str]]:
        """voice spec (and every base voice id inside it) -> projects whose blocks use it, in one pass."""
        usage: dict[str, list[str]] = {}
        for slug in self.names():
            try:
                blocks = self.load(slug)[0]["blocks"]
            except Exception:  # a half-edited file must not break the catalogue
                continue
            seen = set()
            for b in blocks:
                spec = str(b.get("voice", ""))
                for key in {spec, *[part.partition(":")[0].strip() for part in spec.split(",")]}:
                    if key and key not in seen:
                        seen.add(key)
                        usage.setdefault(key, []).append(slug)
        return usage

    def uses_voice(self, needle: str) -> list[str]:
        """Projects whose blocks use this voice spec or signature (for example '@narrator')."""
        return self.voice_usage().get(needle, [])


class Workspace:
    def __init__(self, root: Path | None = None):
        self.root = Path(root or DEFAULT_ROOT).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "projects").mkdir(exist_ok=True)
        (self.root / "exports").mkdir(exist_ok=True)
        self.library = LibraryStore(self.root / "library.yaml")
        self.signatures = SignatureStore(self.root / "signatures.yaml")
        self.pronunciations = PronunciationStore(self.root / "pronunciations.yaml")
        self.presets = PresetStore(self.root / "presets.yaml")
        self.projects = ProjectStore(self.root / "projects")
        self.cache_dir = self.root / "cache"
        self.exports = self.root / "exports"

    def pronunciation_table(self, project: str | None) -> dict:
        shared = self.pronunciations.load()[0]
        if not project:
            return dict(shared)
        return {**shared, **(self.projects.load(project)[0].get("pronunciations") or {})}
