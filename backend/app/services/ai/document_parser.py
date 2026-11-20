"""Text extraction for documents an auditee attaches to the CAR chatbot
(e.g. a customer requirement spec). Kept intentionally simple: no OCR, no
vector store — just plain text extraction that gets truncated and injected
directly into the chatbot prompt.
"""

import io
import logging

logger = logging.getLogger(__name__)

# .doc (legacy binary Word format) has no reliable pure-python reader, so it
# is deliberately not supported here — only formats we can actually extract
# text from without a heavy new dependency (e.g. antiword, LibreOffice).
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}

MAX_PDF_PAGES = 20


class DocumentParseError(ValueError):
    """Raised when a document can't be parsed or contains no usable text."""


def extract_text(filename: str, content: bytes) -> str:
    """Extract plain text from a .pdf, .docx, or .txt file's bytes.

    Raises DocumentParseError if the extension is unsupported or the file
    can't be parsed (e.g. corrupted, password-protected, or — for PDFs —
    image-only/scanned with no extractable text layer).
    """
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    ext = f".{ext}"

    if ext == ".txt":
        try:
            return content.decode("utf-8", errors="ignore")
        except Exception as exc:
            raise DocumentParseError(f"Could not read text file: {exc}") from exc

    if ext == ".pdf":
        return _extract_pdf_text(content)

    if ext == ".docx":
        return _extract_docx_text(content)

    raise DocumentParseError(
        f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
    )


def _extract_pdf_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise DocumentParseError("PDF parsing is not available on this server.") from exc

    try:
        reader = PdfReader(io.BytesIO(content))
    except Exception as exc:
        raise DocumentParseError(f"Could not open PDF (corrupted or password-protected): {exc}") from exc

    if reader.is_encrypted:
        raise DocumentParseError("This PDF is password-protected and can't be read.")

    pages = reader.pages[:MAX_PDF_PAGES]
    texts = []
    for page in pages:
        try:
            texts.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(texts)


def _extract_docx_text(content: bytes) -> str:
    try:
        from docx import Document as DocxDocument
    except ImportError as exc:
        raise DocumentParseError("Word document parsing is not available on this server.") from exc

    try:
        doc = DocxDocument(io.BytesIO(content))
    except Exception as exc:
        raise DocumentParseError(f"Could not open Word document (corrupted?): {exc}") from exc

    return "\n".join(p.text for p in doc.paragraphs)
