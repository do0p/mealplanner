"""Runtime format detection from content signature (magic bytes) with
extension fallback. Never trusts the client-supplied content-type."""
import io
import zipfile

_EXT_MAP = {
    "pdf": "pdf",
    "epub": "epub",
    "docx": "docx",
    "odt": "odt",
    "txt": "txt",
    "csv": "csv",
    "png": "image",
    "jpg": "image",
    "jpeg": "image",
    "tiff": "image",
    "tif": "image",
    "webp": "image",
    "bmp": "image",
    "gif": "image",
}


def detect_format(data: bytes, filename: str) -> str:
    # --- magic bytes ---
    if data[:4] == b"%PDF":
        return "pdf"

    if data[:4] == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = z.namelist()
                if "mimetype" in names:
                    mime = z.read("mimetype").decode("utf-8", "ignore").strip()
                    if "epub" in mime:
                        return "epub"
                if "[Content_Types].xml" in names:
                    ct = z.read("[Content_Types].xml").decode("utf-8", "ignore")
                    if "wordprocessingml" in ct:
                        return "docx"
                    if "spreadsheetml" in ct:
                        return "xlsx"
                    if "opendocument" in ct or "oasis" in ct:
                        return "odt"
        except Exception:
            pass
        return "zip"

    # image magic bytes
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image"
    if data[:3] in (b"\xff\xd8\xff",):
        return "image"
    if data[:2] in (b"BM",):
        return "image"
    if data[:4] in (b"GIF8",):
        return "image"

    # --- extension fallback ---
    if "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()
        if ext in _EXT_MAP:
            return _EXT_MAP[ext]

    # --- try text ---
    try:
        data[:1024].decode("utf-8")
        return "txt"
    except (UnicodeDecodeError, Exception):
        pass

    return "unknown"
