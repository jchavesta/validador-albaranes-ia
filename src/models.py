"""Modelos compartidos y enumeraciones del dominio."""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, Field


class ProcessingStatus(str, Enum):
    """Estados posibles de un procesamiento."""

    PENDING = "PENDIENTE"
    VALIDATED = "VALIDADO"
    INCOMPLETE_EXTRACTION = "EXTRACCION_INCOMPLETA"
    NOT_FOUND = "NO_ENCONTRADO"
    HAS_DIFFERENCES = "CON_DIFERENCIAS"
    INVALID_DOCUMENT = "DOCUMENTO_INVALIDO"
    TECHNICAL_ERROR = "ERROR_TECNICO"
    REFERENCE_DATA_ERROR = "ERROR_DATOS_REFERENCIA"


class ErrorType(str, Enum):
    """Tipos de error controlados por la aplicación."""

    AUTHENTICATION = "AUTENTICACION"
    PERMISSION_DENIED = "PERMISOS"
    CONNECTION = "CONEXION"
    RATE_LIMIT_OR_QUOTA = "LIMITE_CUOTA"
    TIMEOUT = "TIEMPO_ESPERA"
    INVALID_REQUEST = "SOLICITUD_INVALIDA"
    INVALID_RESPONSE = "RESPUESTA_INVALIDA"
    SERVICE_UNAVAILABLE = "SERVICIO"
    REFERENCE_DATA = "DATOS_REFERENCIA"
    FILE = "ARCHIVO"
    INTERNAL = "INTERNO"


class ErrorStage(str, Enum):
    """Etapas en las que puede producirse un error."""

    PDF_VALIDATION = "VALIDACION_PDF"
    OPENAI_EXTRACTION = "EXTRACCION_OPENAI"
    RESPONSE_VALIDATION = "VALIDACION_RESPUESTA"
    REFERENCE_LOADING = "CARGA_REFERENCIA"
    COMPARISON = "COMPARACION"
    HISTORY_WRITE = "GUARDADO_HISTORIAL"


class DeliveryNoteData(BaseModel):
    """Datos extraídos o almacenados de un albarán."""

    numero_albaran: str | None
    cif_proveedor: str | None
    proveedor: str | None
    fecha: date | None
    importe_total: Decimal | None
    moneda: str | None
    campos_no_leidos: list[str] = Field(default_factory=list)
    observaciones: list[str] = Field(default_factory=list)


class PdfInfo(BaseModel):
    """Información obtenida durante la validación de un PDF."""

    path: Path
    file_name: str
    size_bytes: int = Field(ge=0)
    page_count: int = Field(ge=0)
    file_hash: str
    has_extractable_text: bool


class FieldDifference(BaseModel):
    """Diferencia detectada entre el PDF y la referencia."""

    campo: str
    valor_pdf: str | Decimal | date | None
    valor_referencia: str | Decimal | date | None


class ComparisonResult(BaseModel):
    """Resultado de la comparación determinista local."""

    coincide: bool
    diferencias: list[FieldDifference] = Field(default_factory=list)


class ApiUsage(BaseModel):
    """Contadores de tokens comunicados por la API."""

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class OpenAIExtraction(BaseModel):
    """Datos extraídos junto con su uso opcional de API."""

    data: DeliveryNoteData
    api_usage: ApiUsage | None = None


class ProcessingResult(BaseModel):
    """Resultado persistible de un intento de procesamiento."""

    id_procesamiento: UUID
    archivo: str
    huella_archivo: str
    fecha_procesamiento: datetime
    numero_intento: int = Field(ge=1)
    estado: ProcessingStatus
    datos_extraidos: DeliveryNoteData | None = None
    datos_referencia: DeliveryNoteData | None = None
    campos_no_leidos: list[str] = Field(default_factory=list)
    diferencias: list[FieldDifference] = Field(default_factory=list)
    mensaje: str
    duracion_segundos: Decimal = Field(ge=0)
    etapa_error: ErrorStage | None = None
    tipo_error: ErrorType | None = None
    uso_api: ApiUsage | None = None


class DocumentPreparation(BaseModel):
    """Información previa necesaria para procesar un documento."""

    pdf_info: PdfInfo
    previously_processed: bool
    requires_confirmation: bool
    next_attempt_number: int = Field(ge=1)
    latest_result: ProcessingResult | None = None
