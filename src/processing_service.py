"""Coordinación del flujo completo de procesamiento de albaranes."""

import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from src.comparator import DeliveryNoteComparator
from src.config import AppConfig
from src.exceptions import (
    ConfigurationError,
    OpenAIExtractionError,
    PdfValidationError,
    ReferenceDataError,
    ReprocessingConfirmationError,
)
from src.history_repository import HistoryRepository
from src.models import (
    ApiUsage,
    DeliveryNoteData,
    DocumentPreparation,
    ErrorStage,
    ErrorType,
    FieldDifference,
    PdfInfo,
    ProcessingResult,
    ProcessingStatus,
)
from src.normalizer import Normalizer
from src.openai_client import OpenAIExtractor
from src.pdf_validator import PdfValidator
from src.reference_repository import ReferenceRepository


class ProcessingService:
    """Coordina validación, extracción, comparación y persistencia."""

    _REQUIRED_FIELDS = (
        "numero_albaran",
        "cif_proveedor",
        "proveedor",
        "fecha",
        "importe_total",
        "moneda",
    )

    def __init__(
        self,
        config: AppConfig,
        pdf_validator: PdfValidator,
        extractor: OpenAIExtractor | None,
        normalizer: Normalizer,
        comparator: DeliveryNoteComparator,
        reference_repository: ReferenceRepository,
        history_repository: HistoryRepository,
    ) -> None:
        """Inicializa el servicio con sus dependencias especializadas."""

        self.config = config
        self.pdf_validator = pdf_validator
        self.extractor = extractor
        self.normalizer = normalizer
        self.comparator = comparator
        self.reference_repository = reference_repository
        self.history_repository = history_repository

    def prepare_document(self, path: Path) -> DocumentPreparation:
        """Prepara un PDF y consulta sus intentos sin iniciar extracción."""

        pdf_info = self.pdf_validator.validate(path)
        attempts = self.history_repository.find_by_fingerprint(pdf_info.file_hash)
        previously_processed = bool(attempts)
        next_attempt_number = (
            max(attempt.numero_intento for attempt in attempts) + 1
            if attempts
            else 1
        )
        return DocumentPreparation(
            pdf_info=pdf_info,
            previously_processed=previously_processed,
            requires_confirmation=previously_processed,
            next_attempt_number=next_attempt_number,
            latest_result=attempts[-1] if attempts else None,
        )

    def process(
        self,
        path: Path,
        reprocessing_confirmed: bool = False,
    ) -> ProcessingResult:
        """Procesa un PDF y persiste exactamente un resultado controlado."""

        extractor = self._get_available_extractor()
        started_at = datetime.now(timezone.utc)
        started_counter = time.perf_counter()
        processing_id = uuid4()

        try:
            pdf_info = self.pdf_validator.validate(path)
        except PdfValidationError as validation_error:
            file_hash = self.pdf_validator.calculate_fingerprint(path)
            attempts = self.history_repository.find_by_fingerprint(file_hash)
            attempt_number = self._resolve_attempt_number(
                attempts,
                reprocessing_confirmed,
            )
            return self._save_result(
                processing_id=processing_id,
                file_name=path.name,
                file_hash=file_hash,
                started_at=started_at,
                started_counter=started_counter,
                attempt_number=attempt_number,
                status=ProcessingStatus.INVALID_DOCUMENT,
                message=validation_error.message,
                error_stage=validation_error.error_stage,
                error_type=validation_error.error_type,
            )

        attempts = self.history_repository.find_by_fingerprint(pdf_info.file_hash)
        attempt_number = self._resolve_attempt_number(
            attempts,
            reprocessing_confirmed,
        )

        try:
            extraction = extractor.extract(path)
        except OpenAIExtractionError as extraction_error:
            return self._save_result(
                processing_id=processing_id,
                pdf_info=pdf_info,
                started_at=started_at,
                started_counter=started_counter,
                attempt_number=attempt_number,
                status=ProcessingStatus.TECHNICAL_ERROR,
                message=extraction_error.message,
                error_stage=extraction_error.error_stage,
                error_type=extraction_error.error_type,
            )
        except Exception:
            return self._save_result(
                processing_id=processing_id,
                pdf_info=pdf_info,
                started_at=started_at,
                started_counter=started_counter,
                attempt_number=attempt_number,
                status=ProcessingStatus.TECHNICAL_ERROR,
                message="Se produjo un error técnico durante la extracción.",
                error_stage=ErrorStage.OPENAI_EXTRACTION,
                error_type=ErrorType.INTERNAL,
            )

        original_data = extraction.data
        api_usage = extraction.api_usage
        missing_fields = [
            field_name
            for field_name in self._REQUIRED_FIELDS
            if getattr(original_data, field_name) is None
        ]
        if missing_fields:
            unread_fields = list(original_data.campos_no_leidos)
            unread_fields.extend(
                field_name
                for field_name in missing_fields
                if field_name not in unread_fields
            )
            return self._save_result(
                processing_id=processing_id,
                pdf_info=pdf_info,
                started_at=started_at,
                started_counter=started_counter,
                attempt_number=attempt_number,
                status=ProcessingStatus.INCOMPLETE_EXTRACTION,
                message="No se han podido leer todos los campos obligatorios.",
                extracted_data=original_data,
                unread_fields=unread_fields,
                api_usage=api_usage,
            )

        original_reference: DeliveryNoteData | None = None
        try:
            normalized_data = self.normalizer.normalize_delivery_note(original_data)
            supplier_tax_id = normalized_data.cif_proveedor
            delivery_note_number = normalized_data.numero_albaran
            if supplier_tax_id is None or delivery_note_number is None:
                raise ValueError(
                    "La identidad normalizada del albarán está incompleta."
                )
            original_reference = self.reference_repository.find(
                supplier_tax_id,
                delivery_note_number,
            )
            if original_reference is None:
                return self._save_result(
                    processing_id=processing_id,
                    pdf_info=pdf_info,
                    started_at=started_at,
                    started_counter=started_counter,
                    attempt_number=attempt_number,
                    status=ProcessingStatus.NOT_FOUND,
                    message="No se encontró el albarán en los datos de referencia.",
                    extracted_data=original_data,
                    unread_fields=list(original_data.campos_no_leidos),
                    api_usage=api_usage,
                )

            normalized_reference = self.normalizer.normalize_delivery_note(
                original_reference
            )
            comparison = self.comparator.compare(
                normalized_data,
                normalized_reference,
            )
        except ReferenceDataError as reference_error:
            return self._save_result(
                processing_id=processing_id,
                pdf_info=pdf_info,
                started_at=started_at,
                started_counter=started_counter,
                attempt_number=attempt_number,
                status=ProcessingStatus.REFERENCE_DATA_ERROR,
                message=reference_error.message,
                extracted_data=original_data,
                unread_fields=list(original_data.campos_no_leidos),
                error_stage=reference_error.error_stage,
                error_type=reference_error.error_type,
                api_usage=api_usage,
            )
        except Exception:
            return self._save_result(
                processing_id=processing_id,
                pdf_info=pdf_info,
                started_at=started_at,
                started_counter=started_counter,
                attempt_number=attempt_number,
                status=ProcessingStatus.TECHNICAL_ERROR,
                message="Se produjo un error técnico durante la comparación.",
                extracted_data=original_data,
                reference_data=original_reference,
                unread_fields=list(original_data.campos_no_leidos),
                error_stage=ErrorStage.COMPARISON,
                error_type=ErrorType.INTERNAL,
                api_usage=api_usage,
            )

        if comparison.coincide:
            status = ProcessingStatus.VALIDATED
            message = "El albarán coincide con los datos de referencia."
            differences: list[FieldDifference] = []
        else:
            status = ProcessingStatus.HAS_DIFFERENCES
            message = (
                "El albarán contiene diferencias respecto a los datos de referencia."
            )
            differences = list(comparison.diferencias)

        return self._save_result(
            processing_id=processing_id,
            pdf_info=pdf_info,
            started_at=started_at,
            started_counter=started_counter,
            attempt_number=attempt_number,
            status=status,
            message=message,
            extracted_data=original_data,
            reference_data=original_reference,
            unread_fields=list(original_data.campos_no_leidos),
            differences=differences,
            api_usage=api_usage,
        )

    def _get_available_extractor(self) -> OpenAIExtractor:
        """Devuelve el extractor tras comprobar las precondiciones del flujo."""

        if not self.config.openai_api_key:
            raise ConfigurationError(
                "Falta configurar la clave de acceso al servicio de extracción.",
                ErrorType.AUTHENTICATION,
            )
        if self.extractor is None:
            raise ConfigurationError(
                "El servicio de extracción no está disponible.",
                ErrorType.INTERNAL,
            )
        return self.extractor

    @staticmethod
    def _resolve_attempt_number(
        attempts: list[ProcessingResult],
        reprocessing_confirmed: bool,
    ) -> int:
        """Comprueba la confirmación y calcula el siguiente intento."""

        if attempts and not reprocessing_confirmed:
            raise ReprocessingConfirmationError()
        return (
            max(attempt.numero_intento for attempt in attempts) + 1
            if attempts
            else 1
        )

    def _save_result(
        self,
        *,
        processing_id: UUID,
        started_at: datetime,
        started_counter: float,
        attempt_number: int,
        status: ProcessingStatus,
        message: str,
        pdf_info: PdfInfo | None = None,
        file_name: str | None = None,
        file_hash: str | None = None,
        extracted_data: DeliveryNoteData | None = None,
        reference_data: DeliveryNoteData | None = None,
        unread_fields: list[str] | None = None,
        differences: list[FieldDifference] | None = None,
        error_stage: ErrorStage | None = None,
        error_type: ErrorType | None = None,
        api_usage: ApiUsage | None = None,
    ) -> ProcessingResult:
        """Construye, guarda y devuelve un único resultado de procesamiento."""

        result = ProcessingResult(
            id_procesamiento=processing_id,
            archivo=pdf_info.file_name if pdf_info is not None else file_name or "",
            huella_archivo=(
                pdf_info.file_hash if pdf_info is not None else file_hash or ""
            ),
            fecha_procesamiento=started_at,
            numero_intento=attempt_number,
            estado=status,
            datos_extraidos=extracted_data,
            datos_referencia=reference_data,
            campos_no_leidos=list(unread_fields or []),
            diferencias=list(differences or []),
            mensaje=message,
            duracion_segundos=Decimal(
                str(max(0.0, time.perf_counter() - started_counter))
            ),
            etapa_error=error_stage,
            tipo_error=error_type,
            uso_api=api_usage,
        )
        self.history_repository.append(result)
        return result
