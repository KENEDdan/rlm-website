"""Hand-built sample files (good and malicious) for the upload policy tests. Nothing here is a real exploit:
the "malicious" files only carry the markers each check must catch."""

from __future__ import annotations

import io
import struct
import zipfile
import zlib

from PIL import Image


def jpeg(width: int = 1800, height: int = 900, color: str = "orange") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="JPEG", quality=70)
    return buf.getvalue()


def png(width: int = 600, height: int = 400, alpha: bool = False) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA" if alpha else "RGB", (width, height), (240, 101, 42, 200)).save(buf, format="PNG")
    return buf.getvalue()


def webp(width: int = 600, height: int = 400) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), "black").save(buf, format="WEBP")
    return buf.getvalue()


def pixel_bomb(side: int = 10_000) -> bytes:
    """A tiny PNG that decodes to side x side pixels (100 MP by default)."""
    buf = io.BytesIO()
    Image.new("1", (side, side)).save(buf, format="PNG")
    return buf.getvalue()


EXE = (
    b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00"
    + b"\x00" * 48
    + b"PE\x00\x00"
    + b"\x00" * 200
)
SVG_SCRIPT = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
HTML = b"<!DOCTYPE html><html><body><script>alert(document.cookie)</script></body></html>"


def polyglot_jpeg() -> bytes:
    """A valid JPEG with an HTML/script payload appended (renders as an image, sniffed as a page)."""
    return jpeg(1800, 900) + b"<html><script>alert(1)</script></html>"


# ---------------------------------------------------------------------------------------------- PDF
def pdf(body: bytes = b"") -> bytes:
    return (
        b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        + body
        + (b"\n2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n")
    )


def pdf_javascript() -> bytes:
    return pdf(b"3 0 obj\n<< /S /JavaScript /JS (app.alert('x')) >>\nendobj\n")


def pdf_obfuscated_javascript() -> bytes:
    return pdf(b"3 0 obj\n<< /S /J#61vaScript /J#53 (app.alert('x')) >>\nendobj\n")


def pdf_launch_in_compressed_stream() -> bytes:
    inner = zlib.compress(b"<< /Type /Action /S /Launch /F (cmd.exe) >>")
    return pdf(
        b"3 0 obj\n<< /Type /ObjStm /Filter /FlateDecode /Length %d >>\nstream\n" % len(inner)
        + inner
        + b"\nendstream\nendobj\n"
    )


# ---------------------------------------------------------------------------------------------- Office
CONTENT_TYPES = (
    b'<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/'
    b'content-types"><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/'
    b'document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.'
    b'main+xml"/></Types>'
)


def docx(extra: dict[str, bytes] | None = None, content_types: bytes = CONTENT_TYPES) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", b"<Relationships/>")
        z.writestr(
            "word/document.xml",
            b"<w:document><w:body><w:p>Budget</w:p></w:body></w:document>",
        )
        for name, data in (extra or {}).items():
            z.writestr(name, data)
    return buf.getvalue()


def docx_with_macro() -> bytes:
    return docx(
        {"word/vbaProject.bin": b"\xd0\xcf\x11\xe0 macro"},
        CONTENT_TYPES.replace(b"document.main+xml", b"document.macroEnabled.main+xml"),
    )


def docx_zip_bomb() -> bytes:
    return docx({"word/media/filler.xml": b"\x00" * (60 * 1024 * 1024)})


# ---------------------------------------------------------------------------------------------- MP4
def _box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def _track(handler: bytes, codec: bytes, width: int = 1920, height: int = 1080) -> bytes:
    hdlr = _box(b"hdlr", b"\x00" * 4 + b"\x00" * 4 + handler + b"\x00" * 12 + b"\x00")
    entry_body = b"\x00" * 6 + b"\x00\x01" + b"\x00" * 16 + struct.pack(">HH", width, height) + b"\x00" * 50
    entry = struct.pack(">I4s", 8 + len(entry_body), codec) + entry_body
    stsd = _box(b"stsd", b"\x00" * 4 + struct.pack(">I", 1) + entry)
    minf = _box(b"minf", _box(b"stbl", stsd))
    return _box(b"trak", _box(b"mdia", hdlr + minf))


def mp4(
    seconds: float = 8,
    codec: bytes = b"avc1",
    audio: bool = False,
    size: tuple[int, int] = (1920, 1080),
) -> bytes:
    ftyp = _box(b"ftyp", b"isom" + struct.pack(">I", 512) + b"isomiso2avc1mp41")
    mvhd = _box(
        b"mvhd",
        b"\x00" * 4 + b"\x00" * 8 + struct.pack(">II", 1000, int(seconds * 1000)) + b"\x00" * 80,
    )
    tracks = _track(b"vide", codec, *size)
    if audio:
        tracks += _track(b"soun", b"mp4a")
    moov = _box(b"moov", mvhd + tracks)
    mdat = _box(b"mdat", b"\x00" * 2048)
    return ftyp + moov + mdat


# ---------------------------------------------------------------------------------------------- WebM
def _vint_size(n: int) -> bytes:
    for length in range(1, 9):
        if n < (1 << (7 * length)) - 1:
            return (n | (1 << (7 * length))).to_bytes(length, "big")
    raise ValueError(n)


def _el(eid: int, payload: bytes) -> bytes:
    return eid.to_bytes((eid.bit_length() + 7) // 8, "big") + _vint_size(len(payload)) + payload


def webm(seconds: float = 8, codec: bytes = b"V_VP9", audio: bool = False) -> bytes:
    header = _el(
        0x1A45DFA3,
        _el(0x4286, b"\x01") + _el(0x4282, b"webm") + _el(0x4287, b"\x04") + _el(0x4285, b"\x02"),
    )
    info = _el(
        0x1549A966,
        _el(0x2AD7B1, (1_000_000).to_bytes(3, "big")) + _el(0x4489, struct.pack(">d", seconds * 1000)),
    )
    video = _el(
        0xE0,
        _el(0xB0, (1920).to_bytes(2, "big")) + _el(0xBA, (1080).to_bytes(2, "big")),
    )
    tracks_body = _el(0xAE, _el(0xD7, b"\x01") + _el(0x83, b"\x01") + _el(0x86, codec) + video)
    if audio:
        tracks_body += _el(0xAE, _el(0xD7, b"\x02") + _el(0x83, b"\x02") + _el(0x86, b"A_OPUS"))
    cluster = _el(0x1F43B675, _el(0xE7, b"\x00") + b"\x00" * 64)
    segment = (
        b"\x18\x53\x80\x67"
        + b"\x01\xff\xff\xff\xff\xff\xff\xff"
        + info
        + _el(0x1654AE6B, tracks_body)
        + cluster
    )
    return header + segment


# ---------------------------------------------------------------------------------------------- audio
def mp3() -> bytes:
    frame = b"\xff\xfb\x90\x64" + b"\x00" * 413
    return b"ID3\x03\x00\x00\x00\x00\x00\x00" + frame * 20
