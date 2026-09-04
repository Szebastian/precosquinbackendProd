"""
Excel parser for unstructured inscriptions form.

Extracts three data blocks from a single-sheet .xlsx using anchor/header
detection (never fixed iloc indices).

Sections:
  1. Datos del Solista — personal data row
  2. Equipamiento     — dynamic list of instruments/needs
  3. Planilla de Temas — up to 6 songs
"""

from __future__ import annotations

import io
from typing import Any

import pandas as pd
import structlog

logger = structlog.get_logger(__name__)

# ── Pydantic schemas ────────────────────────────────────────────
from pydantic import BaseModel, Field


class SolistaData(BaseModel):
    """Personal data extracted from the 'DATOS DEL SOLISTA:' section."""
    nombre: str = ""
    apellido: str = ""
    dni: str = ""
    fecha_nacimiento: str = ""
    direccion: str = ""
    ciudad: str = ""
    provincia: str = ""
    telefono: str = ""
    correo_electronico: str = ""
    instrumento_que_tocan: str = ""
    tipo_instrumento: str = ""


class InstrumentoItem(BaseModel):
    """Single instrument row from the 'CARGAR:' section."""
    instrumento: str = ""
    necesita: str = ""


class TemaItem(BaseModel):
    """Single song from the 'PLANILLA DE 6 TEMAS:' section."""
    nombre_del_tema: str = ""
    autor: str = ""
    ritmo: str = ""


class MissingField(BaseModel):
    """A required field that is missing or empty after parsing."""
    field_key: str
    label: str
    section: str


class ExcelParseResult(BaseModel):
    """Complete result of parsing the inscription Excel form."""
    solista: SolistaData = Field(default_factory=SolistaData)
    instrumentos: list[InstrumentoItem] = Field(default_factory=list)
    temas: list[TemaItem] = Field(default_factory=list)
    missing_fields: list[MissingField] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ── Helper functions ────────────────────────────────────────────

def _cell_str(value: Any) -> str:
    """Convert a cell value to a clean string. NaN/None → ''."""
    if pd.isna(value):
        return ""
    return str(value).strip()


def _row_to_dict(row: pd.Series) -> dict[str, str]:
    """Convert a pandas Series row to {normalized_col: value}."""
    return {str(c).strip().lower(): _cell_str(v) for c, v in row.items()}


# ── Anchor detection ───────────────────────────────────────────

_SOLISTA_ANCHORS = {"datos del solista", "nombre", "apellido"}
_EQUIPO_ANCHORS = {"cargar", "instrumento", "necesita"}
_TEMA_ANCHORS = {"planilla de 6 temas", "nombre del tema", "autor", "ritmo"}


def _find_anchor_row(
    df: pd.DataFrame,
    anchors: set[str],
) -> int | None:
    """
    Search every cell in the DataFrame for any anchor string.
    Returns the first matching row index, or None.
    """
    for idx, row in df.iterrows():
        cells = {_cell_str(v).lower() for v in row.values}
        if cells & anchors:
            return int(idx)
    return None


def _find_header_row(
    df: pd.DataFrame,
    expected_cols: list[str],
) -> tuple[int | None, dict[int, str]]:
    """
    Find a row whose cells match expected column names (order-insensitive).
    Returns (row_index, {col_position: normalized_name}).
    """
    normalized = [c.lower().strip() for c in expected_cols]
    for idx, row in df.iterrows():
        cells = [_cell_str(v).lower() for v in row.values]
        matches = 0
        mapping: dict[int, str] = {}
        for i, cell in enumerate(cells):
            if cell in normalized:
                mapping[i] = normalized[normalized.index(cell)]
                matches += 1
        if matches >= len(expected_cols) // 2:
            return int(idx), mapping
    return None, {}


# ── Section extractors ─────────────────────────────────────────

def _extract_solista(
    df: pd.DataFrame,
    anchor_row: int,
) -> tuple[SolistaData, list[str]]:
    """
    Extract personal data from the SOLISTA section.
    Strategy: look for the header row with field names, then read the
    data row immediately below it.
    """
    warnings: list[str] = []
    col_names = ["NOMBRE", "APELLIDO", "DNI", "FECHA DE NACIMIENTO", "DIRECCION",
                 "CIUDAD", "TELEFONO", "CORREO ELECTRONICO",
                 "INSTRUMENTO QUE TOCAN", "TIPO DE INSTRUMENTO"]

    # Search from anchor_row downward for the header (max 10 rows)
    search_end = min(anchor_row + 10, len(df))
    header_idx, col_map = _find_header_row(df.loc[anchor_row:search_end], col_names)

    if header_idx is None:
        warnings.append("No se encontró la fila de encabezados de datos del solista")
        return SolistaData(), warnings

    # Data row is immediately below the header
    data_idx = header_idx + 1
    if data_idx >= len(df):
        warnings.append("Falta la fila de datos debajo del encabezado del solista")
        return SolistaData(), warnings

    data_row = df.iloc[data_idx]
    mapping = {
        "nombre": "nombre",
        "apellido": "apellido",
        "dni": "dni",
        "fecha de nacimiento": "fecha_nacimiento",
        "direccion": "direccion",
        "telefono": "telefono",
        "correo electronico": "correo_electronico",
        "ciudad": "ciudad",
        "instrumento que tocan": "instrumento_que_tocan",
        "tipo de instrumento": "tipo_instrumento",
    }

    values: dict[str, str] = {}
    for pos, col_name in col_map.items():
        field = mapping.get(col_name, col_name)
        values[field] = _cell_str(data_row.iloc[pos]) if pos < len(data_row) else ""

    # Split "ciudad, provincia" into separate fields
    raw_ciudad = values.pop("ciudad", "")
    if "," in raw_ciudad:
        parts = raw_ciudad.split(",", 1)
        values["ciudad"] = parts[0].strip()
        values["provincia"] = parts[1].strip()
    else:
        values["ciudad"] = raw_ciudad

    return SolistaData(**values), warnings


def _extract_instrumentos(
    df: pd.DataFrame,
    anchor_row: int,
) -> tuple[list[InstrumentoItem], list[str]]:
    """
    Extract the instrument/equipment list from the CARGAR section.
    Reads rows from the header downward until an empty row or section boundary.
    """
    warnings: list[str] = []
    col_names = ["INSTRUMENTO", "NECESITA"]

    search_end = min(anchor_row + 5, len(df))
    header_idx, col_map = _find_header_row(df.loc[anchor_row:search_end], col_names)

    if header_idx is None:
        # Fallback: assume columns are in order from anchor row
        header_idx = anchor_row
        col_map = {}
        for i, cell in enumerate(df.iloc[header_idx].values):
            normalized = _cell_str(cell).lower()
            if normalized in ("instrumento",):
                col_map[i] = "instrumento"
            elif normalized in ("necesita",):
                col_map[i] = "necesita"

        if not col_map:
            warnings.append("No se encontró la fila de encabezados de instrumentos")
            return [], warnings

    items: list[InstrumentoItem] = []
    max_rows = 50  # safety limit
    current_row = header_idx + 1

    while current_row < len(df) and len(items) < max_rows:
        row = df.iloc[current_row]
        inst = ""
        necesita = ""

        for pos, col_name in col_map.items():
            if pos < len(row):
                val = _cell_str(row.iloc[pos])
                if col_name == "instrumento":
                    inst = val
                elif col_name == "necesita":
                    necesita = val

        # Stop on empty row (both cells blank)
        if not inst and not necesita:
            break

        if inst or necesita:
            items.append(InstrumentoItem(instrumento=inst, necesita=necesita))

        current_row += 1

    return items, warnings


def _extract_temas(
    df: pd.DataFrame,
    anchor_row: int,
) -> tuple[list[TemaItem], list[str]]:
    """
    Extract songs from the PLANILLA DE 6 TEMAS section.
    Reads up to 6 rows of data below the header.
    """
    warnings: list[str] = []
    col_names = ["NOMBRE DEL TEMA", "AUTOR", "RITMO"]

    search_end = min(anchor_row + 5, len(df))
    header_idx, col_map = _find_header_row(df.loc[anchor_row:search_end], col_names)

    if header_idx is None:
        header_idx = anchor_row
        col_map = {}
        for i, cell in enumerate(df.iloc[header_idx].values):
            normalized = _cell_str(cell).lower()
            if normalized in ("nombre del tema",):
                col_map[i] = "nombre_del_tema"
            elif normalized in ("autor",):
                col_map[i] = "autor"
            elif normalized in ("ritmo",):
                col_map[i] = "ritmo"

        if not col_map:
            warnings.append("No se encontró la fila de encabezados de temas")
            return [], warnings

    items: list[TemaItem] = []
    max_temas = 6
    current_row = header_idx + 1

    while current_row < len(df) and len(items) < max_temas:
        row = df.iloc[current_row]
        nombre = ""
        autor = ""
        ritmo = ""

        for pos, col_name in col_map.items():
            if pos < len(row):
                val = _cell_str(row.iloc[pos])
                if col_name == "nombre_del_tema":
                    nombre = val
                elif col_name == "autor":
                    autor = val
                elif col_name == "ritmo":
                    ritmo = val

        # Stop on empty row
        if not nombre and not autor and not ritmo:
            break

        if nombre or autor or ritmo:
            items.append(TemaItem(nombre_del_tema=nombre, autor=autor, ritmo=ritmo))

        current_row += 1

    return items, warnings


# ── Main parser ────────────────────────────────────────────────

def parse_inscription_excel(file_bytes: bytes, filename: str = "") -> ExcelParseResult:
    """
    Parse an unstructured inscription Excel file.

    Reads the .xlsx from raw bytes, detects three sections by anchor/header
    strings, and returns structured data.

    Args:
        file_bytes: Raw bytes of the .xlsx file.
        filename: Original filename (for logging only).

    Returns:
        ExcelParseResult with solista, instrumentos, temas, and warnings.

    Raises:
        ValueError: If the file is corrupt, empty, or unreadable.
    """
    logger.info("excel_parse_start", filename=filename, size=len(file_bytes))

    if not file_bytes:
        raise ValueError("El archivo está vacío")

    try:
        df = pd.read_excel(
            io.BytesIO(file_bytes),
            engine="openpyxl",
            header=None,       # Don't treat any row as header — we detect headers ourselves
            dtype=str,         # Read everything as strings to avoid type coercion
        )
    except Exception as exc:
        logger.error("excel_parse_read_error", error=str(exc))
        raise ValueError(f"No se pudo leer el archivo Excel: {exc}") from exc

    if df.empty:
        raise ValueError("El archivo Excel no contiene datos")

    logger.info("excel_parse_loaded", rows=len(df), cols=len(df.columns))

    all_warnings: list[str] = []

    # ── Section 1: Solista ──────────────────────────────────────
    solista_row = _find_anchor_row(df, _SOLISTA_ANCHORS)
    if solista_row is not None:
        solista, sw = _extract_solista(df, solista_row)
        all_warnings.extend(sw)
    else:
        solista = SolistaData()
        all_warnings.append("No se encontró la sección 'DATOS DEL SOLISTA'")

    # ── Section 2: Instrumentos ─────────────────────────────────
    equipo_row = _find_anchor_row(df, _EQUIPO_ANCHORS)
    if equipo_row is not None:
        instrumentos, ew = _extract_instrumentos(df, equipo_row)
        all_warnings.extend(ew)
    else:
        instrumentos = []
        all_warnings.append("No se encontró la sección 'CARGAR' de instrumentos")

    # ── Section 3: Temas ────────────────────────────────────────
    tema_row = _find_anchor_row(df, _TEMA_ANCHORS)
    if tema_row is not None:
        temas, tw = _extract_temas(df, tema_row)
        all_warnings.extend(tw)
    else:
        temas = []
        all_warnings.append("No se encontró la sección 'PLANILLA DE 6 TEMAS'")

    logger.info(
        "excel_parse_done",
        solista_nombre=solista.nombre,
        instrumentos_count=len(instrumentos),
        temas_count=len(temas),
        warnings_count=len(all_warnings),
    )

    # ── Field validation: required fields for inscripcion ────────
    missing: list[MissingField] = []
    _req = [
        ("firstName",      "Nombre",             "Datos personales",   solista.nombre),
        ("lastName",       "Apellido",           "Datos personales",   solista.apellido),
        ("dni",            "DNI",                "Datos personales",   solista.dni),
        ("birthDate",      "Fecha de nacimiento","Datos personales",   solista.fecha_nacimiento),
        ("address",        "Domicilio",          "Datos personales",   solista.direccion),
        ("locality",       "Localidad",          "Datos personales",   solista.ciudad),
        ("province",       "Provincia",          "Datos personales",   solista.provincia),
        ("phone",          "Teléfono",           "Datos personales",   solista.telefono),
        ("email",          "Email",              "Datos personales",   solista.correo_electronico),
        ("instrumentName", "Instrumento",        "Categoría",          solista.instrumento_que_tocan),
    ]
    for key, label, section, value in _req:
        if not value.strip():
            missing.append(MissingField(field_key=key, label=label, section=section))

    return ExcelParseResult(
        solista=solista,
        instrumentos=instrumentos,
        temas=temas,
        missing_fields=missing,
        warnings=all_warnings,
    )
