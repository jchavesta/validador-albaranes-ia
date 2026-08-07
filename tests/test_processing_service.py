"""Pruebas unitarias del coordinador de procesamiento."""

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.config import AppConfig
from src.exceptions import (
    ConfigurationError,
    HistoryError,
    OpenAIExtractionError,
    PdfValidationError,
    ReferenceDataError,
    ReprocessingConfirmationError,
)
from src.models import (
    ApiUsage,
    ComparisonResult,
    DeliveryNoteData,
    ErrorStage,
    ErrorType,
    FieldDifference,
    OpenAIExtraction,
    PdfInfo,
    ProcessingResult,
    ProcessingStatus,
)
from src.processing_service import ProcessingService


def make_config(api_key: str | None = "clave-de-prueba") -> AppConfig:
    """Crea configuración sin consultar archivos de entorno."""

    return AppConfig(_env_file=None, openai_api_key=api_key)


def make_pdf_info(name: str = "albaran.pdf", file_hash: str = "huella") -> PdfInfo:
    """Crea información simulada de un PDF válido."""

    return PdfInfo(
        path=Path(name),
        file_name=name,
        size_bytes=100,
        page_count=1,
        file_hash=file_hash,
        has_extractable_text=True,
    )


def make_data(**changes: object) -> DeliveryNoteData:
    """Crea un albarán completo y permite reemplazar campos."""

    values = {
        "numero_albaran": " alb-01 ",
        "cif_proveedor": " b-123 ",
        "proveedor": "Proveedor Uno",
        "fecha": date(2026, 8, 7),
        "importe_total": Decimal("10.50"),
        "moneda": "eur",
        "campos_no_leidos": ["observado"],
        "observaciones": ["Lectura parcial"],
    }
    values.update(changes)
    return DeliveryNoteData(**values)


def make_attempt(number: int = 1, file_hash: str = "huella") -> ProcessingResult:
    """Crea un intento histórico mínimo."""

    return ProcessingResult(
        id_procesamiento=uuid4(),
        archivo="anterior.pdf",
        huella_archivo=file_hash,
        fecha_procesamiento=datetime(2026, 8, 7, tzinfo=timezone.utc),
        numero_intento=number,
        estado=ProcessingStatus.VALIDATED,
        mensaje="Correcto",
        duracion_segundos=Decimal("1"),
    )


@pytest.fixture
def dependencies() -> dict[str, MagicMock]:
    """Crea dobles aislados para todas las dependencias."""

    pdf_validator = MagicMock()
    pdf_validator.validate.return_value = make_pdf_info()
    extractor = MagicMock()
    extractor.extract.return_value = OpenAIExtraction(data=make_data())
    normalizer = MagicMock()
    normalizer.normalize_delivery_note.side_effect = lambda data: data.model_copy()
    comparator = MagicMock()
    comparator.compare.return_value = ComparisonResult(coincide=True)
    reference_repository = MagicMock()
    reference_repository.find.return_value = make_data()
    history_repository = MagicMock()
    history_repository.find_by_fingerprint.return_value = []
    return {
        "pdf_validator": pdf_validator,
        "extractor": extractor,
        "normalizer": normalizer,
        "comparator": comparator,
        "reference_repository": reference_repository,
        "history_repository": history_repository,
    }


def make_service(
    dependencies: dict[str, MagicMock],
    *,
    config: AppConfig | None = None,
    extractor: MagicMock | None | object = ...,
) -> ProcessingService:
    """Construye el servicio con configuración y dobles controlados."""

    selected_extractor = (
        dependencies["extractor"] if extractor is ... else extractor
    )
    return ProcessingService(
        config=config or make_config(),
        pdf_validator=dependencies["pdf_validator"],
        extractor=selected_extractor,  # type: ignore[arg-type]
        normalizer=dependencies["normalizer"],
        comparator=dependencies["comparator"],
        reference_repository=dependencies["reference_repository"],
        history_repository=dependencies["history_repository"],
    )


def test_prepare_new_document(dependencies: dict[str, MagicMock]) -> None:
    """Prepara un documento nuevo sin iniciar un intento."""

    service = make_service(dependencies, config=make_config(api_key=None))
    preparation = service.prepare_document(Path("nuevo.pdf"))

    assert not preparation.previously_processed
    assert not preparation.requires_confirmation
    assert preparation.next_attempt_number == 1
    assert preparation.latest_result is None
    dependencies["pdf_validator"].validate.assert_called_once_with(Path("nuevo.pdf"))
    dependencies["history_repository"].find_by_fingerprint.assert_called_once_with(
        "huella"
    )
    dependencies["extractor"].extract.assert_not_called()
    dependencies["history_repository"].append.assert_not_called()


def test_prepare_known_document_uses_latest_and_maximum(
    dependencies: dict[str, MagicMock],
) -> None:
    """Prepara un documento conocido usando el máximo y el último registro."""

    attempts = [make_attempt(4), make_attempt(2)]
    dependencies["history_repository"].find_by_fingerprint.return_value = attempts

    preparation = make_service(dependencies).prepare_document(Path("renombrado.pdf"))

    assert preparation.previously_processed
    assert preparation.requires_confirmation
    assert preparation.next_attempt_number == 5
    assert preparation.latest_result is attempts[-1]


@pytest.mark.parametrize("dependency", ["pdf_validator", "history_repository"])
def test_prepare_propagates_controlled_errors(
    dependencies: dict[str, MagicMock],
    dependency: str,
) -> None:
    """Propaga fallos de validación e historial durante preparación."""

    error = PdfValidationError("PDF inválido") if dependency == "pdf_validator" else HistoryError("Historial inválido")
    if dependency == "pdf_validator":
        dependencies[dependency].validate.side_effect = error
    else:
        dependencies[dependency].find_by_fingerprint.side_effect = error

    with pytest.raises(type(error)):
        make_service(dependencies).prepare_document(Path("documento.pdf"))

    dependencies["extractor"].extract.assert_not_called()
    dependencies["history_repository"].append.assert_not_called()


def test_missing_api_key_stops_before_validation(dependencies: dict[str, MagicMock]) -> None:
    """Impide iniciar el flujo sin clave configurada."""

    service = make_service(dependencies, config=make_config(api_key=None))
    with pytest.raises(ConfigurationError) as captured:
        service.process(Path("documento.pdf"))

    assert captured.value.error_type is ErrorType.AUTHENTICATION
    assert "clave-de-prueba" not in captured.value.message
    dependencies["pdf_validator"].validate.assert_not_called()
    dependencies["history_repository"].append.assert_not_called()


def test_missing_extractor_stops_before_validation(dependencies: dict[str, MagicMock]) -> None:
    """Impide iniciar el flujo sin adaptador de extracción."""

    service = make_service(dependencies, extractor=None)
    with pytest.raises(ConfigurationError) as captured:
        service.process(Path("documento.pdf"))

    assert captured.value.error_type is ErrorType.INTERNAL
    dependencies["pdf_validator"].validate.assert_not_called()
    dependencies["history_repository"].append.assert_not_called()


def test_known_document_requires_confirmation(dependencies: dict[str, MagicMock]) -> None:
    """Exige confirmación sin extraer ni persistir."""

    dependencies["history_repository"].find_by_fingerprint.return_value = [make_attempt()]

    with pytest.raises(ReprocessingConfirmationError):
        make_service(dependencies).process(Path("documento.pdf"))

    dependencies["extractor"].extract.assert_not_called()
    dependencies["history_repository"].append.assert_not_called()


def test_confirmed_reprocessing_recalculates_next_attempt(
    dependencies: dict[str, MagicMock],
) -> None:
    """Recalcula el historial y utiliza el máximo al reprocesar."""

    dependencies["history_repository"].find_by_fingerprint.return_value = [
        make_attempt(5),
        make_attempt(2),
    ]

    result = make_service(dependencies).process(
        Path("documento.pdf"),
        reprocessing_confirmed=True,
    )

    assert result.numero_intento == 6
    dependencies["history_repository"].find_by_fingerprint.assert_called_once_with(
        "huella"
    )


def test_validated_result_preserves_originals_usage_and_metadata(
    dependencies: dict[str, MagicMock],
) -> None:
    """Guarda un resultado validado con originales y metadatos auditables."""

    original = make_data()
    reference = make_data(proveedor="PROVEEDOR UNO")
    usage = ApiUsage(input_tokens=10, output_tokens=5, total_tokens=15)
    dependencies["extractor"].extract.return_value = OpenAIExtraction(
        data=original,
        api_usage=usage,
    )
    dependencies["reference_repository"].find.return_value = reference
    original_dump = original.model_dump()
    reference_dump = reference.model_dump()

    result = make_service(dependencies).process(Path("documento.pdf"))

    assert result.estado is ProcessingStatus.VALIDATED
    assert result.datos_extraidos is original
    assert result.datos_referencia is reference
    assert result.uso_api == usage
    assert result.campos_no_leidos == ["observado"]
    assert result.fecha_procesamiento.tzinfo is not None
    assert result.fecha_procesamiento.utcoffset().total_seconds() == 0
    assert result.duracion_segundos >= 0
    assert result.id_procesamiento.version == 4
    assert original.model_dump() == original_dump
    assert reference.model_dump() == reference_dump
    dependencies["extractor"].extract.assert_called_once_with(Path("documento.pdf"))
    dependencies["normalizer"].normalize_delivery_note.assert_any_call(original)
    dependencies["normalizer"].normalize_delivery_note.assert_any_call(reference)
    dependencies["history_repository"].append.assert_called_once_with(result)


@pytest.mark.parametrize(
    "missing_field",
    [
        "numero_albaran",
        "cif_proveedor",
        "proveedor",
        "fecha",
        "importe_total",
        "moneda",
    ],
)
def test_each_missing_required_field_is_incomplete(
    dependencies: dict[str, MagicMock],
    missing_field: str,
) -> None:
    """Clasifica cada campo obligatorio nulo sin consultar referencias."""

    data = make_data(**{missing_field: None}, campos_no_leidos=["proveedor"])
    dependencies["extractor"].extract.return_value = OpenAIExtraction(data=data)

    result = make_service(dependencies).process(Path("documento.pdf"))

    assert result.estado is ProcessingStatus.INCOMPLETE_EXTRACTION
    assert result.datos_extraidos is data
    assert result.datos_referencia is None
    assert result.diferencias == []
    assert result.campos_no_leidos.count(missing_field) == 1
    assert result.campos_no_leidos[0] == "proveedor"
    dependencies["normalizer"].normalize_delivery_note.assert_not_called()
    dependencies["reference_repository"].find.assert_not_called()
    dependencies["comparator"].compare.assert_not_called()


def test_not_found_preserves_original_and_usage(dependencies: dict[str, MagicMock]) -> None:
    """Clasifica una identidad completa que no aparece en referencia."""

    usage = ApiUsage(total_tokens=3)
    original = make_data()
    dependencies["extractor"].extract.return_value = OpenAIExtraction(
        data=original,
        api_usage=usage,
    )
    dependencies["reference_repository"].find.return_value = None

    result = make_service(dependencies).process(Path("documento.pdf"))

    assert result.estado is ProcessingStatus.NOT_FOUND
    assert result.datos_extraidos is original
    assert result.datos_referencia is None
    assert result.diferencias == []
    assert result.uso_api == usage


def test_has_differences_preserves_normalized_differences(
    dependencies: dict[str, MagicMock],
) -> None:
    """Conserva diferencias producidas por el comparador normalizado."""

    difference = FieldDifference(
        campo="importe_total",
        valor_pdf=Decimal("10.50"),
        valor_referencia=Decimal("11.00"),
    )
    dependencies["comparator"].compare.return_value = ComparisonResult(
        coincide=False,
        diferencias=[difference],
    )

    result = make_service(dependencies).process(Path("documento.pdf"))

    assert result.estado is ProcessingStatus.HAS_DIFFERENCES
    assert result.diferencias == [difference]


def test_uses_normalized_identity_and_models_for_comparison(
    dependencies: dict[str, MagicMock],
) -> None:
    """Usa la identidad y los modelos normalizados solo para comparar."""

    original_extracted = make_data()
    normalized_extracted = make_data(
        cif_proveedor="B123",
        numero_albaran="ALB-01",
    )
    original_reference = make_data(proveedor="Proveedor de referencia")
    normalized_reference = make_data(proveedor="PROVEEDOR DE REFERENCIA")
    dependencies["extractor"].extract.return_value = OpenAIExtraction(
        data=original_extracted
    )
    dependencies["reference_repository"].find.return_value = original_reference
    dependencies["normalizer"].normalize_delivery_note.side_effect = [
        normalized_extracted,
        normalized_reference,
    ]

    result = make_service(dependencies).process(Path("documento.pdf"))

    dependencies["reference_repository"].find.assert_called_once_with(
        "B123",
        "ALB-01",
    )
    dependencies["comparator"].compare.assert_called_once_with(
        normalized_extracted,
        normalized_reference,
    )
    assert result.datos_extraidos is original_extracted
    assert result.datos_referencia is original_reference


def test_invalid_pdf_with_fingerprint_is_persisted_without_extraction(
    dependencies: dict[str, MagicMock],
) -> None:
    """Registra un PDF inválido cuando puede identificarse por su huella."""

    validation_error = PdfValidationError("El PDF supera el máximo permitido.")
    dependencies["pdf_validator"].validate.side_effect = validation_error
    dependencies["pdf_validator"].calculate_fingerprint.return_value = "hash-invalido"

    result = make_service(dependencies).process(Path("carpeta/invalido.pdf"))

    assert result.estado is ProcessingStatus.INVALID_DOCUMENT
    assert result.archivo == "invalido.pdf"
    assert result.huella_archivo == "hash-invalido"
    assert result.mensaje == validation_error.message
    assert result.tipo_error is ErrorType.FILE
    assert result.etapa_error is ErrorStage.PDF_VALIDATION
    assert result.uso_api is None
    dependencies["extractor"].extract.assert_not_called()
    dependencies["history_repository"].append.assert_called_once_with(result)


def test_known_invalid_pdf_requires_confirmation(
    dependencies: dict[str, MagicMock],
) -> None:
    """Exige confirmación para volver a registrar un PDF inválido conocido."""

    dependencies["pdf_validator"].validate.side_effect = PdfValidationError(
        "PDF inválido"
    )
    dependencies["pdf_validator"].calculate_fingerprint.return_value = "hash-invalido"
    dependencies["history_repository"].find_by_fingerprint.return_value = [
        make_attempt(file_hash="hash-invalido")
    ]

    with pytest.raises(ReprocessingConfirmationError):
        make_service(dependencies).process(Path("invalido.pdf"))

    dependencies["extractor"].extract.assert_not_called()
    dependencies["history_repository"].append.assert_not_called()


def test_confirmed_invalid_pdf_uses_next_attempt(
    dependencies: dict[str, MagicMock],
) -> None:
    """Calcula el siguiente intento al confirmar un PDF inválido conocido."""

    dependencies["pdf_validator"].validate.side_effect = PdfValidationError(
        "PDF inválido"
    )
    dependencies["pdf_validator"].calculate_fingerprint.return_value = "hash-invalido"
    dependencies["history_repository"].find_by_fingerprint.return_value = [
        make_attempt(2, "hash-invalido"),
        make_attempt(5, "hash-invalido"),
    ]

    result = make_service(dependencies).process(
        Path("invalido.pdf"),
        reprocessing_confirmed=True,
    )

    assert result.estado is ProcessingStatus.INVALID_DOCUMENT
    assert result.numero_intento == 6
    dependencies["history_repository"].append.assert_called_once_with(result)
    dependencies["extractor"].extract.assert_not_called()


def test_invalid_pdf_without_fingerprint_is_not_persisted(
    dependencies: dict[str, MagicMock],
) -> None:
    """Propaga el fallo de huella de un documento no identificable."""

    dependencies["pdf_validator"].validate.side_effect = PdfValidationError("Inválido")
    fingerprint_error = PdfValidationError("No se pudo calcular la huella")
    dependencies["pdf_validator"].calculate_fingerprint.side_effect = fingerprint_error

    with pytest.raises(PdfValidationError) as captured:
        make_service(dependencies).process(Path("invalido.pdf"))

    assert captured.value is fingerprint_error
    dependencies["history_repository"].append.assert_not_called()
    dependencies["extractor"].extract.assert_not_called()


def test_reference_error_preserves_extraction_and_usage(
    dependencies: dict[str, MagicMock],
) -> None:
    """Convierte un fallo de referencia conservando la extracción."""

    data = make_data()
    usage = ApiUsage(total_tokens=8)
    dependencies["extractor"].extract.return_value = OpenAIExtraction(
        data=data,
        api_usage=usage,
    )
    dependencies["reference_repository"].find.side_effect = ReferenceDataError(
        "Los datos de referencia son inválidos."
    )

    result = make_service(dependencies).process(Path("documento.pdf"))

    assert result.estado is ProcessingStatus.REFERENCE_DATA_ERROR
    assert result.datos_extraidos is data
    assert result.datos_referencia is None
    assert result.uso_api == usage
    assert result.tipo_error is ErrorType.REFERENCE_DATA
    assert result.etapa_error is ErrorStage.REFERENCE_LOADING


def test_controlled_openai_error_becomes_technical(
    dependencies: dict[str, MagicMock],
) -> None:
    """Conserva clasificación y etapa de un fallo controlado de OpenAI."""

    dependencies["extractor"].extract.side_effect = OpenAIExtractionError(
        "No se pudo conectar con el servicio.",
        ErrorType.CONNECTION,
        ErrorStage.OPENAI_EXTRACTION,
    )

    result = make_service(dependencies).process(Path("documento.pdf"))

    assert result.estado is ProcessingStatus.TECHNICAL_ERROR
    assert result.tipo_error is ErrorType.CONNECTION
    assert result.etapa_error is ErrorStage.OPENAI_EXTRACTION
    assert result.datos_extraidos is None
    assert result.uso_api is None


def test_unexpected_extractor_error_is_safe(dependencies: dict[str, MagicMock]) -> None:
    """Oculta los detalles de un fallo inesperado del extractor."""

    dependencies["extractor"].extract.side_effect = RuntimeError("secreto interno")

    result = make_service(dependencies).process(Path("documento.pdf"))

    assert result.estado is ProcessingStatus.TECHNICAL_ERROR
    assert result.tipo_error is ErrorType.INTERNAL
    assert result.etapa_error is ErrorStage.OPENAI_EXTRACTION
    assert "secreto interno" not in result.mensaje


@pytest.mark.parametrize("failing_dependency", ["normalizer", "comparator"])
def test_unexpected_comparison_error_is_safe(
    dependencies: dict[str, MagicMock],
    failing_dependency: str,
) -> None:
    """Clasifica fallos locales sin almacenar detalles técnicos."""

    if failing_dependency == "normalizer":
        dependencies["normalizer"].normalize_delivery_note.side_effect = RuntimeError(
            "dato interno"
        )
    else:
        dependencies["comparator"].compare.side_effect = RuntimeError("dato interno")

    result = make_service(dependencies).process(Path("documento.pdf"))

    assert result.estado is ProcessingStatus.TECHNICAL_ERROR
    assert result.tipo_error is ErrorType.INTERNAL
    assert result.etapa_error is ErrorStage.COMPARISON
    assert "dato interno" not in result.mensaje


def test_incomplete_normalized_identity_becomes_safe_technical_error(
    dependencies: dict[str, MagicMock],
) -> None:
    """Convierte una identidad normalizada incompleta en un error seguro."""

    original_data = make_data()
    dependencies["extractor"].extract.return_value = OpenAIExtraction(
        data=original_data
    )
    dependencies["normalizer"].normalize_delivery_note.return_value = make_data(
        cif_proveedor=None
    )
    dependencies["normalizer"].normalize_delivery_note.side_effect = None

    result = make_service(dependencies).process(Path("documento.pdf"))

    assert result.estado is ProcessingStatus.TECHNICAL_ERROR
    assert result.tipo_error is ErrorType.INTERNAL
    assert result.etapa_error is ErrorStage.COMPARISON
    assert (
        "La identidad normalizada del albarán está incompleta."
        not in result.mensaje
    )
    dependencies["reference_repository"].find.assert_not_called()
    dependencies["history_repository"].append.assert_called_once_with(result)


def test_history_error_is_propagated_without_second_write(
    dependencies: dict[str, MagicMock],
) -> None:
    """Propaga el fallo de persistencia sin reintentar la escritura."""

    history_error = HistoryError("No se pudo guardar el historial.")
    dependencies["history_repository"].append.side_effect = history_error

    with pytest.raises(HistoryError) as captured:
        make_service(dependencies).process(Path("documento.pdf"))

    assert captured.value is history_error
    assert dependencies["history_repository"].append.call_count == 1
