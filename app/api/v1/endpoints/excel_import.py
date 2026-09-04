"""
Excel inscription form parser endpoint.

Receives an .xlsx file upload, parses its unstructured sections
(solista data, instruments, themes) using anchor/header detection,
and returns structured JSON.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse

from app.services.excel_parser import ExcelParseResult, parse_inscription_excel

logger = structlog.get_logger(__name__)
router = APIRouter()

_MAX_FILE_SIZE_MB = 10
_ALLOWED_EXTENSIONS = {".xlsx", ".xls"}
_ALLOWED_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "application/octet-stream",  # some browsers send this for downloads
}


def _validate_file(file: UploadFile) -> None:
    """Validate file extension, MIME type, and size before parsing."""
    filename = file.filename or ""

    # Extension check
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Formato no soportado: '{ext}'. Use archivos .xlsx o .xls.",
        )

    # MIME type check (lenient — some clients send generic types)
    if file.content_type and file.content_type not in _ALLOWED_MIME_TYPES:
        logger.warning("excel_upload_unexpected_mime", mime=file.content_type, filename=filename)

    # Size check
    if file.size and file.size > _MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"El archivo supera el límite de {_MAX_FILE_SIZE_MB} MB.",
        )


@router.post(
    "/parse-excel",
    response_model=ExcelParseResult,
    summary="Parse inscription Excel form",
    description=(
        "Uploads an .xlsx file with unstructured inscription data "
        "(solista, instrumentos, temas) and returns structured JSON."
    ),
)
async def parse_excel(
    file: UploadFile = File(..., description="Archivo .xlsx con la planilla de inscripción"),
) -> ExcelParseResult:
    """
    Parse an unstructured inscription Excel form.

    The file must contain three sections detected by anchor strings:
    - "DATOS DEL SOLISTA:" — personal data
    - "CARGAR:" — instruments and equipment needs
    - "PLANILLA DE 6 TEMAS:" — songs/themes

    Returns structured JSON with all extracted data and any warnings.
    """
    _validate_file(file)

    try:
        content = await file.read()
    except Exception as exc:
        logger.error("excel_upload_read_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo leer el archivo subido.",
        )

    try:
        result = parse_inscription_excel(content, filename=file.filename or "")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except Exception as exc:
        logger.error("excel_parse_unexpected_error", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al procesar el archivo Excel.",
        )

    return result
