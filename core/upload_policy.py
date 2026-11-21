"""ONE place that decides which files may be uploaded anywhere (public site, Django admin, staff portal).

Every ``FileField`` / ``ImageField`` in the project names a policy from ``POLICIES`` (``SafeImageField(policy=...)``,
``SafeFileField(policy=...)``, ``PrivateFileField(policy=...)``); ``tests/test_upload_policies.py`` fails if a
field has none, so a new field cannot skip validation. ``validate_upload`` runs, in this order:

a. file name: no null bytes, control characters, path separators, ``..``, hidden names or double extensions
b. extension against the policy whitelist (macro-enabled Office files get their own message)
c. size cap (Super Admin may change it in "Upload limits", never above ``HARD_MAX_BYTES``)
d. real content type (libmagic) must be allowed AND must match the extension; executables, scripts, HTML and
   SVG are refused everywhere, and so is embedded markup/script in images, PDFs and audio (polyglots)
e. per kind: images (decoded with Pillow; dimensions, pixel bomb guard), video (container, codec, duration,
   size, no audio track), PDF (no JavaScript, launch/embedded-file actions or encryption, also inside
   compressed streams), Office (zip structure, no macros/embedded objects, no zip bombs), CSV (UTF-8, no NUL)
f. optional ClamAV scan (``CLAMAV_ENABLED``) before anything is stored; fails closed

Random server-side names (``core.uploads.RandomUploadTo``), image re-encoding without EXIF/GPS and private
storage are applied by the field classes. The HTML ``accept`` attribute is only a hint for the file picker.
"""

from __future__ import annotations

import os
import re
import socket
import struct
import unicodedata
import warnings
import zipfile
import zlib
from dataclasses import dataclass, replace
from typing import Any

import magic
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.base import File
from django.utils.deconstruct import deconstructible
from PIL import Image, UnidentifiedImageError

MB = 1024 * 1024
# Pillow refuses anything bigger (decompression bomb); 1x-2x only warns, which we treat as an error too.
Image.MAX_IMAGE_PIXELS = 40_000_000
MAX_IMAGE_SIDE = 12_000
HARD_MAX_BYTES = 60 * MB  # nothing can be configured above this; the web server refuses bigger bodies
HARD_MAX_VIDEO_SECONDS = 30
POLICY_CACHE_KEY = "core:upload-limits:v1"

# Extension -> the content types libmagic may report for it.
MIME_FOR_EXT: dict[str, set[str]] = {
    "jpg": {"image/jpeg"},
    "jpeg": {"image/jpeg"},
    "png": {"image/png"},
    "webp": {"image/webp"},
    "pdf": {"application/pdf"},
    "mp3": {"audio/mpeg", "audio/mp3"},
    "m4a": {"audio/mp4", "audio/x-m4a", "video/mp4", "audio/m4a"},
    "mp4": {"video/mp4"},
    "webm": {"video/webm"},
    "docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
        "application/octet-stream",
    },
    "xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",
        "application/octet-stream",
    },
    "csv": {"text/csv", "text/plain", "application/csv"},
}
KIND_FOR_EXT = {
    "jpg": "image",
    "jpeg": "image",
    "png": "image",
    "webp": "image",
    "pdf": "pdf",
    "mp3": "audio",
    "m4a": "audio",
    "mp4": "video",
    "webm": "video",
    "docx": "office",
    "xlsx": "office",
    "csv": "csv",
}
MACRO_EXTENSIONS = {
    "docm",
    "xlsm",
    "pptm",
    "dotm",
    "xltm",
    "potm",
    "ppsm",
    "xlam",
    "ppam",
    "doc",
    "xls",
    "ppt",
}
# Never accepted, whatever a policy says (also used to spot "photo.php.jpg"-style double extensions).
BLOCKED_EXTENSIONS = {
    "exe", "dll", "com", "bat", "cmd", "msi", "msp", "scr", "pif", "cpl", "jar", "apk", "app", "dmg", "deb",
    "rpm", "sh", "bash", "zsh", "ps1", "psm1", "vbs", "vbe", "js", "mjs", "jse", "wsf", "wsh", "hta", "py",
    "pyc", "pl", "rb", "php", "phtml", "php5", "phar", "asp", "aspx", "jsp", "cgi", "html", "htm", "xhtml",
    "shtml", "svg", "svgz", "xml", "xsl", "swf", "lnk", "reg", "iso", "img", "zip", "rar", "7z", "gz", "tar",
    "bz2", "xz", "cab", "url", "inf", "scf", "chm", "htaccess", "ini", "config",
}  # fmt: skip
BLOCKED_MIME_PREFIXES = (
    "application/x-dosexec",
    "application/x-executable",
    "application/x-mach-binary",
    "application/x-sharedlib",
    "application/x-msdownload",
    "application/x-sh",
    "application/x-shellscript",
    "application/javascript",
    "application/x-php",
    "application/java-archive",
    "application/x-msi",
    "text/html",
    "text/javascript",
    "text/x-php",
    "text/x-shellscript",
    "text/x-python",
    "text/x-script",
    "text/xml",
    "application/xml",
    "image/svg",
    "application/x-rar",
    "application/x-7z",
)
# Markup or script inside a binary file means a polyglot (e.g. a JPEG that is also an HTML page).
EMBEDDED_CODE = re.compile(
    rb"<\s*(script|html|svg|iframe|object|embed|body)[\s>/]|<\?php|javascript:",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Policy:
    code: str
    label: str
    extensions: tuple[str, ...]
    max_bytes: int
    private: bool = False
    min_width: int = 0
    max_seconds: int = 0  # video only
    output: str = (
        ""  # images: "png" forces PNG output (logos keep transparency); "" = PNG if alpha, else JPEG
    )
    note: str = ""

    @property
    def kinds(self) -> set[str]:
        return {KIND_FOR_EXT[ext] for ext in self.extensions}

    @property
    def formats_label(self) -> str:
        names = []
        for ext in self.extensions:
            name = {"jpeg": "", "jpg": "JPEG", "m4a": "M4A", "mp4": "MP4 (H.264)"}.get(ext, ext.upper())
            if name and name not in names:
                names.append(name)
        return ", ".join(names)

    @property
    def max_mb_label(self) -> str:
        mb = self.max_bytes / MB
        return f"{mb:g} MB"

    @property
    def help_text(self) -> str:
        parts = [f"Accepted: {self.formats_label}. Maximum {self.max_mb_label}."]
        if self.min_width:
            parts.append(f"At least {self.min_width} pixels wide.")
        if self.max_seconds:
            parts.append(f"At most {self.max_seconds} seconds.")
        if self.note:
            parts.append(self.note)
        return " ".join(parts)

    @property
    def accept(self) -> str:
        """For the HTML ``accept`` attribute: a picker hint only, never the security check."""
        return ",".join(f".{ext}" for ext in self.extensions)


IMG = ("jpg", "jpeg", "png", "webp")
_POLICY_LIST = [
    Policy("logo", "Site logo", ("png", "webp"), 2 * MB, output="png"),
    Policy("favicon", "Favicon", ("png",), 2 * MB, output="png", note="Square, at least 512 x 512 pixels."),
    Policy("hero_photo", "Hero photo, slide image or page banner", IMG, 5 * MB, min_width=1600),
    Policy(
        "hero_video",
        "Hero background video",
        ("mp4", "webm"),
        15 * MB,
        max_seconds=15,
        note="Recommended: a loop of 10 seconds or less, 1080p, under 10 MB, without sound. "
        "A poster image is required.",
    ),
    Policy("content_image", "Profile, activity, news, event and other content images", IMG, 3 * MB),
    Policy("gallery_photo", "Gallery photo", IMG, 8 * MB, note="Thumbnails are made automatically."),
    Policy("sermon_audio", "Sermon audio", ("mp3", "m4a"), 50 * MB),
    Policy("public_document", "Public documents, reports and study materials", ("pdf",), 10 * MB),
    Policy("finance_receipt", "Receipts and vouchers", ("pdf", "jpg", "jpeg", "png"), 5 * MB, private=True),
    Policy(
        "office_document",
        "Budgets, proposals, contracts, designs and BOQs",
        ("pdf", "docx", "xlsx", "jpg", "jpeg", "png"),
        20 * MB,
        private=True,
    ),
    Policy("site_photo", "Project site-visit and field photos", IMG, 8 * MB, private=True),
    Policy("private_record", "Member, pastoral and meeting documents", ("pdf", "jpg", "jpeg", "png"), 10 * MB, private=True),
    Policy("study_material", "Study materials (staff only)", ("pdf",), 10 * MB, private=True),
    Policy("design_file", "Media design artwork", ("pdf", "jpg", "jpeg", "png", "webp"), 20 * MB, private=True),
    Policy("csv_import", "CSV import", ("csv",), 2 * MB, private=True, note="UTF-8 text."),
]  # fmt: skip
POLICIES: dict[str, Policy] = {p.code: p for p in _POLICY_LIST}


def get_policy(code: str) -> Policy:
    """The policy with the Super Admin's adjusted limits applied (cached; see ``core.UploadLimit``)."""
    base = POLICIES[code]
    overrides = cache.get(POLICY_CACHE_KEY)
    if overrides is None:
        overrides = {}
        try:
            from .models import UploadLimit

            for row in UploadLimit.objects.all():
                overrides[row.policy] = (row.max_mb, row.min_width, row.max_seconds)
        except Exception:  # noqa: BLE001 - table missing during the first migrate; defaults apply
            overrides = {}
        cache.set(POLICY_CACHE_KEY, overrides, 300)
    if code not in overrides:
        return base
    max_mb, min_width, max_seconds = overrides[code]
    changes: dict[str, Any] = {}
    if max_mb:
        changes["max_bytes"] = min(int(max_mb * MB), HARD_MAX_BYTES)
    if min_width is not None:
        changes["min_width"] = min_width
    if max_seconds and base.max_seconds:
        changes["max_seconds"] = min(max_seconds, HARD_MAX_VIDEO_SECONDS)
    return replace(base, **changes)


# ---------------------------------------------------------------------------------------------- helpers
def _reject(policy: Policy, reason: str, code: str = "invalid_upload") -> ValidationError:
    return ValidationError(
        f"{reason} Accepted for this field: {policy.formats_label}, up to {policy.max_mb_label}.",
        code=code,
    )


def extension(name: str) -> str:
    return os.path.splitext(name or "")[1].lower().lstrip(".")


def check_filename(name: str, policy: Policy) -> str:
    """Return the lower-case extension, or raise for names that try path tricks or double extensions."""
    raw = name or ""
    base = os.path.basename(raw.replace("\\", "/"))
    if (
        not base
        or "\x00" in raw
        or any(unicodedata.category(ch) in ("Cc", "Cf") for ch in raw)
        or "/" in raw
        or "\\" in raw
        or ".." in raw
        or base.startswith(".")
        or len(raw) > 200
    ):
        raise _reject(
            policy,
            "The file name is not allowed (it contains a path, hidden or control characters).",
        )
    stem, _ = os.path.splitext(base)
    inner = extension(stem)
    if inner and (inner in BLOCKED_EXTENSIONS or inner in KIND_FOR_EXT or inner in MACRO_EXTENSIONS):
        raise _reject(
            policy,
            "Files with two extensions (for example photo.php.jpg) are not accepted.",
        )
    ext = extension(base)
    if ext in MACRO_EXTENSIONS:
        raise _reject(policy, "Macro-enabled or old-format Office files (.docm, .xlsm, .pptm, .doc, .xls) are not "
                      "accepted. Save as .docx or .xlsx, or as PDF.")  # fmt: skip
    if ext in BLOCKED_EXTENSIONS:
        raise _reject(
            policy,
            "Programs, scripts, web pages, SVG images and archives are never accepted.",
        )
    if ext not in policy.extensions:
        raise _reject(policy, f"'.{ext or '?'}' files are not accepted here.")
    return ext


def _read_all(file: File, limit: int) -> bytes:
    file.seek(0)
    data = file.read(limit + 1)
    file.seek(0)
    return data


def sniff(data: bytes) -> str:
    return magic.from_buffer(data[:8192], mime=True)


# ---------------------------------------------------------------------------------------------- images
def check_image(file: File, policy: Policy) -> tuple[int, int]:
    try:
        file.seek(0)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(file) as img:
                width, height = img.size
                fmt = (img.format or "").upper()
                if width * height > Image.MAX_IMAGE_PIXELS or max(width, height) > MAX_IMAGE_SIDE:
                    raise _reject(policy, "The image has too many pixels.")
                img.verify()
            file.seek(0)
            with Image.open(file) as img:
                img.load()  # a full decode catches truncated or malformed data that verify() lets through
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:  # fmt: skip
        raise _reject(policy, "The image could not be read (it may be damaged or too large).") from exc
    finally:
        file.seek(0)
    if fmt not in {"JPEG", "PNG", "WEBP", "MPO"}:
        raise _reject(policy, "The image format is not accepted.")
    if policy.min_width and width < policy.min_width:
        raise _reject(
            policy,
            f"The image is {width} pixels wide; at least {policy.min_width} are needed.",
        )
    return width, height


# ---------------------------------------------------------------------------------------------- video
@dataclass
class VideoInfo:
    container: str
    codec: str
    seconds: float
    width: int
    height: int
    has_audio: bool


def _mp4_boxes(data: bytes, start: int, end: int):  # type: ignore[no-untyped-def]
    pos = start
    while pos + 8 <= end:
        size, kind = struct.unpack(">I4s", data[pos : pos + 8])
        header = 8
        if size == 1:
            if pos + 16 > end:
                return
            size = struct.unpack(">Q", data[pos + 8 : pos + 16])[0]
            header = 16
        elif size == 0:
            size = end - pos
        if size < header or pos + size > end:
            raise ValueError("bad box")
        yield kind, pos + header, pos + size
        pos += size


def _mp4_child(data: bytes, start: int, end: int, kind: bytes) -> tuple[int, int] | None:
    for k, s, e in _mp4_boxes(data, start, end):
        if k == kind:
            return s, e
    return None


def parse_mp4(data: bytes) -> VideoInfo:
    top = {k: (s, e) for k, s, e in _mp4_boxes(data, 0, len(data))}
    if b"ftyp" not in top or b"moov" not in top:
        raise ValueError("not an MP4 file")
    ms, me = top[b"moov"]
    mvhd = _mp4_child(data, ms, me, b"mvhd")
    if mvhd is None:
        raise ValueError("no movie header")
    s = mvhd[0]
    version = data[s]
    if version == 1:
        timescale, duration = struct.unpack(">IQ", data[s + 20 : s + 32])
    else:
        timescale, duration = struct.unpack(">II", data[s + 12 : s + 20])
    seconds = duration / timescale if timescale else 0.0
    codec, width, height, has_audio = "", 0, 0, False
    for kind, ts, te in _mp4_boxes(data, ms, me):
        if kind != b"trak":
            continue
        mdia = _mp4_child(data, ts, te, b"mdia")
        if mdia is None:
            continue
        hdlr = _mp4_child(data, *mdia, b"hdlr")
        handler = data[hdlr[0] + 8 : hdlr[0] + 12] if hdlr else b""
        if handler == b"soun":
            has_audio = True
        elif handler == b"vide":
            minf = _mp4_child(data, *mdia, b"minf")
            stbl = _mp4_child(data, *minf, b"stbl") if minf else None
            stsd = _mp4_child(data, *stbl, b"stsd") if stbl else None
            if stsd:
                entry = stsd[0] + 8  # version/flags + entry count
                codec = data[entry + 4 : entry + 8].decode("latin-1")
                width, height = struct.unpack(">HH", data[entry + 32 : entry + 36])
    return VideoInfo("mp4", codec, seconds, width, height, has_audio)


def _ebml_vint(data: bytes, pos: int, *, keep_marker: bool) -> tuple[int, int]:
    first = data[pos]
    length = 1
    mask = 0x80
    while length <= 8 and not first & mask:
        mask >>= 1
        length += 1
    if length > 8:
        raise ValueError("bad EBML number")
    value = first if keep_marker else first & (mask - 1)
    for byte in data[pos + 1 : pos + length]:
        value = (value << 8) | byte
    unknown = not keep_marker and value == (1 << (7 * length)) - 1
    return (-1 if unknown else value), pos + length


def _ebml_elements(data: bytes, start: int, end: int):  # type: ignore[no-untyped-def]
    pos = start
    while pos < end:
        eid, pos = _ebml_vint(data, pos, keep_marker=True)
        size, pos = _ebml_vint(data, pos, keep_marker=False)
        stop = end if size < 0 else pos + size
        if stop > len(data):
            stop = len(data)
        yield eid, pos, stop
        pos = stop


def parse_webm(data: bytes) -> VideoInfo:
    elements = list(_ebml_elements(data, 0, min(len(data), 64)))
    if not elements or elements[0][0] != 0x1A45DFA3:
        raise ValueError("not a WebM file")
    _, hs, he = elements[0]
    doctype = next((data[s:e] for i, s, e in _ebml_elements(data, hs, he) if i == 0x4282), b"")
    if doctype != b"webm":
        raise ValueError("not a WebM file")
    seg = next(
        ((s, e) for i, s, e in _ebml_elements(data, he, len(data)) if i == 0x18538067),
        None,
    )
    if seg is None:
        raise ValueError("no segment")
    scale, duration, codec, width, height, has_audio = 1_000_000, None, "", 0, 0, False
    for eid, s, e in _ebml_elements(data, *seg):
        if eid == 0x1F43B675:  # first Cluster: the headers are done
            break
        if eid == 0x1549A966:  # Info
            for cid, cs, ce in _ebml_elements(data, s, e):
                if cid == 0x2AD7B1:
                    scale = int.from_bytes(data[cs:ce], "big")
                elif cid == 0x4489:
                    duration = struct.unpack(">f" if ce - cs == 4 else ">d", data[cs:ce])[0]
        elif eid == 0x1654AE6B:  # Tracks
            for tid, ts, te in _ebml_elements(data, s, e):
                if tid != 0xAE:
                    continue
                fields = {i: (a, b) for i, a, b in _ebml_elements(data, ts, te)}
                track_type = int.from_bytes(data[slice(*fields[0x83])], "big") if 0x83 in fields else 0
                track_codec = data[slice(*fields[0x86])].decode("latin-1") if 0x86 in fields else ""
                if track_type == 2:
                    has_audio = True
                elif track_type == 1:
                    codec = track_codec
                    if 0xE0 in fields:
                        for vid, vs, ve in _ebml_elements(data, *fields[0xE0]):
                            if vid == 0xB0:
                                width = int.from_bytes(data[vs:ve], "big")
                            elif vid == 0xBA:
                                height = int.from_bytes(data[vs:ve], "big")
    if duration is None:
        raise ValueError("unknown duration")
    return VideoInfo("webm", codec, duration * scale / 1e9, width, height, has_audio)


H264_CODECS = {"avc1", "avc3"}
WEBM_CODECS = {"V_VP8", "V_VP9", "V_AV1"}


def check_video(data: bytes, ext: str, policy: Policy) -> VideoInfo:
    try:
        info = parse_mp4(data) if ext == "mp4" else parse_webm(data)
    except (ValueError, IndexError, struct.error) as exc:
        raise _reject(
            policy,
            "The video could not be read. Export it again as MP4 (H.264) or WebM.",
        ) from exc
    if ext == "mp4" and info.codec not in H264_CODECS:
        raise _reject(
            policy,
            f"MP4 videos must use the H.264 codec (this one uses '{info.codec or '?'}').",
        )
    if ext == "webm" and info.codec not in WEBM_CODECS:
        raise _reject(policy, "WebM videos must use VP8, VP9 or AV1.")
    if info.seconds <= 0:
        raise _reject(policy, "The video length could not be read. Export it again.")
    if policy.max_seconds and info.seconds > policy.max_seconds + 0.5:
        raise _reject(
            policy,
            f"The video is {info.seconds:.0f} seconds long; at most {policy.max_seconds} are allowed.",
        )
    if info.has_audio:
        raise _reject(
            policy,
            "Background videos play without sound. Remove the audio track and upload it again.",
        )
    if max(info.width, info.height) > 2560:
        raise _reject(policy, "The video is larger than 1440p. Export it at 1080p.")
    return info


# ---------------------------------------------------------------------------------------------- PDF
PDF_FORBIDDEN = (
    b"/javascript", b"/js", b"/launch", b"/embeddedfile", b"/embeddedfiles", b"/richmedia", b"/xfa", b"/aa",
    b"/submitform", b"/importdata", b"/gotoe", b"/gotor",
)  # fmt: skip
_PDF_NAME = re.compile(rb"/[^\s/<>\[\]()%{}]+")
_PDF_STREAM = re.compile(rb"stream\r?\n")
PDF_INFLATE_LIMIT = 80 * MB


def _pdf_names(chunk: bytes) -> set[bytes]:
    out = set()
    for match in _PDF_NAME.finditer(chunk):
        name = re.sub(
            rb"#([0-9a-fA-F]{2})",
            lambda m: bytes([int(m.group(1), 16)]),
            match.group(0),
        )
        out.add(name.lower())
    return out


def check_pdf(data: bytes, policy: Policy) -> None:
    if not data.startswith(b"%PDF-"):
        raise _reject(policy, "The file is not a valid PDF.")
    chunks = [data]
    budget = PDF_INFLATE_LIMIT
    for match in _PDF_STREAM.finditer(data):
        start = match.end()
        stop = data.find(b"endstream", start)
        if stop < 0:
            break
        try:
            inflater = zlib.decompressobj()
            out = inflater.decompress(data[start:stop], budget)
        except zlib.error:
            continue  # not Flate (images, fonts in other filters)
        budget -= len(out)
        if inflater.unconsumed_tail or budget <= 0:
            raise _reject(policy, "The PDF expands to an unreasonable size and was refused.")
        chunks.append(out)
    names: set[bytes] = set()
    for chunk in chunks:
        names |= _pdf_names(chunk)
    if b"/encrypt" in names:
        raise _reject(
            policy,
            "Password-protected or encrypted PDFs cannot be checked. Upload an unprotected copy.",
        )
    bad = names & set(PDF_FORBIDDEN)
    if bad:
        raise _reject(
            policy,
            "The PDF contains scripts, actions or embedded files, which are not allowed.",
        )


# ---------------------------------------------------------------------------------------------- Office
OFFICE_MAX_ENTRIES = 2000
OFFICE_MAX_UNCOMPRESSED = 200 * MB
OFFICE_MAX_RATIO = 100
OFFICE_MAIN_PART = {"docx": "word/document.xml", "xlsx": "xl/workbook.xml"}


def check_office(file: File, ext: str, policy: Policy) -> None:
    file.seek(0)
    try:
        with zipfile.ZipFile(file) as archive:
            infos = archive.infolist()
            if len(infos) > OFFICE_MAX_ENTRIES:
                raise _reject(policy, "The document contains too many parts.")
            total = 0
            names = set()
            for info in infos:
                name = info.filename
                names.add(name)
                if name.startswith(("/", "\\")) or ".." in name or "\x00" in name or ":" in name:
                    raise _reject(policy, "The document contains unsafe paths.")
                lower = name.lower()
                if lower.endswith(("vbaproject.bin", "vbadata.xml")) or "/activex/" in lower:
                    raise _reject(policy, "The document contains macros, which are not allowed.")
                if "/embeddings/" in lower or lower.endswith((".exe", ".dll", ".js", ".vbs", ".bat", ".zip")):
                    raise _reject(
                        policy,
                        "The document contains embedded files or objects, which are not allowed.",
                    )
                if info.flag_bits & 0x1:
                    raise _reject(policy, "Password-protected documents cannot be checked.")
                total += info.file_size
                if (
                    info.file_size > MB
                    and info.compress_size
                    and info.file_size / info.compress_size > OFFICE_MAX_RATIO
                ):
                    raise _reject(
                        policy,
                        "The document looks like a compression bomb and was refused.",
                    )
            if total > OFFICE_MAX_UNCOMPRESSED:
                raise _reject(
                    policy,
                    "The document expands to an unreasonable size and was refused.",
                )
            if "[Content_Types].xml" not in names or OFFICE_MAIN_PART[ext] not in names:
                raise _reject(policy, f"The file is not a valid .{ext} document.")
            content_types = archive.read("[Content_Types].xml")[: 2 * MB].lower()
            if b"macroenabled" in content_types or b"vbaproject" in content_types:
                raise _reject(policy, "The document contains macros, which are not allowed.")
    except zipfile.BadZipFile as exc:
        raise _reject(policy, f"The file is not a valid .{ext} document.") from exc
    finally:
        file.seek(0)


# ---------------------------------------------------------------------------------------------- CSV
def check_csv(data: bytes, policy: Policy) -> None:
    if b"\x00" in data:
        raise _reject(policy, "The file is not a text CSV file.")
    try:
        data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise _reject(policy, "The CSV file must be saved as UTF-8.") from exc


# ---------------------------------------------------------------------------------------------- ClamAV
class ScannerUnavailable(Exception):
    pass


def clamav_scan(data: bytes) -> str | None:
    """Return the signature name if infected, None if clean. Raises ScannerUnavailable on errors."""
    host, port = settings.CLAMAV_HOST, settings.CLAMAV_PORT
    try:
        with socket.create_connection((host, port), timeout=settings.CLAMAV_TIMEOUT) as sock:
            sock.sendall(b"zINSTREAM\0")
            for i in range(0, len(data), 64 * 1024):
                chunk = data[i : i + 64 * 1024]
                sock.sendall(struct.pack(">I", len(chunk)) + chunk)
            sock.sendall(struct.pack(">I", 0))
            reply = b""
            while not reply.endswith(b"\0"):
                part = sock.recv(4096)
                if not part:
                    break
                reply += part
    except OSError as exc:
        raise ScannerUnavailable(str(exc)) from exc
    text = reply.rstrip(b"\0").decode("utf-8", "replace")
    if text.endswith("OK"):
        return None
    if "FOUND" in text:
        return text.split(":", 1)[-1].replace("FOUND", "").strip() or "malware"
    raise ScannerUnavailable(text)


# ---------------------------------------------------------------------------------------------- entry point
def validate_upload(file: File, policy_code: str) -> None:
    """Raise ValidationError unless ``file`` satisfies the named policy. Idempotent and side-effect free."""
    policy = get_policy(policy_code)
    ext = check_filename(getattr(file, "name", ""), policy)
    size = getattr(file, "size", None)
    if size is None or size > policy.max_bytes:
        raise _reject(policy, "The file is too large.", code="file_too_large")
    if size == 0:
        raise _reject(policy, "The file is empty.")
    data = _read_all(file, policy.max_bytes)
    if len(data) > policy.max_bytes:
        raise _reject(policy, "The file is too large.", code="file_too_large")
    mime = sniff(data)
    if mime.startswith(BLOCKED_MIME_PREFIXES):
        raise _reject(policy, "Programs, scripts, web pages and SVG images are never accepted.")
    if mime not in MIME_FOR_EXT[ext]:
        raise _reject(policy, f"The content of the file does not match its '.{ext}' extension.")
    kind = KIND_FOR_EXT[ext]
    if kind in {"image", "pdf", "audio"} and EMBEDDED_CODE.search(data):
        raise _reject(
            policy,
            "The file contains embedded web code (a disguised file) and was refused.",
        )
    if kind == "image":
        check_image(file, policy)
    elif kind == "video":
        check_video(data, ext, policy)
    elif kind == "pdf":
        check_pdf(data, policy)
    elif kind == "office":
        check_office(file, ext, policy)
    elif kind == "csv":
        check_csv(data, policy)
    if settings.CLAMAV_ENABLED:
        try:
            found = clamav_scan(data)
        except ScannerUnavailable as exc:
            raise ValidationError(
                "The virus scanner is not available, so the file was not accepted. Try again later."
            ) from exc
        if found:
            raise ValidationError("The file was flagged by the virus scanner and was not accepted.")
    file.seek(0)


@deconstructible
class MissingPolicyValidator:
    """Attached to an upload field that names no policy: refuses everything (fail closed)."""

    def __call__(self, value: Any) -> None:
        if value and not getattr(value, "_committed", True):
            raise ValidationError("Uploads are switched off for this field (no upload policy).")

    def __eq__(self, other: object) -> bool:
        return isinstance(other, MissingPolicyValidator)


@deconstructible
class PolicyValidator:
    """Model-field validator naming its policy (runs in every ModelForm: public, admin and portal)."""

    def __init__(self, policy: str) -> None:
        if policy not in POLICIES:
            raise KeyError(f"Unknown upload policy {policy!r}")
        self.policy = policy

    def __call__(self, value: Any) -> None:
        if not value:
            return
        # Already stored (and validated when it was uploaded): nothing new to check. Checked before touching
        # ``value.file``, which would open the stored file.
        if getattr(value, "_committed", False):
            return
        validate_upload(value, self.policy)
        value._rlm_validated = self.policy  # the storage hook skips re-checking this exact object

    def __eq__(self, other: object) -> bool:
        return isinstance(other, PolicyValidator) and other.policy == self.policy
