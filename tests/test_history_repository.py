"""Pruebas unitarias del repositorio de historial."""

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import pytest

from src.exceptions import HistoryError
from src.history_repository import HistoryRepository
from src.models import (
    ApiUsage,
    DeliveryNoteData,
    ErrorStage,
    ErrorType,
    FieldDifference,
    ProcessingResult,
    ProcessingStatus,
)


def make_result(
    *,
    file_hash: str = "hash-a",
    attempt_number: int = 1,
    identifier: int = 1,
) -> ProcessingResult:
    """Construye un resultado completo y determinista para las pruebas."""

    extracted = DeliveryNoteData(
        numero_albaran="ALB-001",
        cif_proveedor="B12345678",
        proveedor="PROVEEDOR FICTICIO SL",
        fecha=date(2026, 8, 7),
        importe_total=Decimal("1250.75"),
        moneda="EUR",
    )
    return ProcessingResult(
        id_procesamiento=UUID(int=identifier),
        archivo="albaran.pdf",
        huella_archivo=file_hash,
        fecha_procesamiento=datetime(2026, 8, 7, 12, 30, tzinfo=timezone.utc),
        numero_intento=attempt_number,
        estado=ProcessingStatus.HAS_DIFFERENCES,
        datos_extraidos=extracted,
        datos_referencia=extracted.model_copy(deep=True),
        campos_no_leidos=["moneda"],
        diferencias=[
            FieldDifference(
                campo="fecha",
                valor_pdf=date(2026, 8, 7),
                valor_referencia=date(2026, 8, 8),
            )
        ],
        mensaje="Se detectaron diferencias",
        duracion_segundos=Decimal("1.25"),
        etapa_error=ErrorStage.COMPARISON,
        tipo_error=ErrorType.INTERNAL,
        uso_api=ApiUsage(input_tokens=10, output_tokens=5, total_tokens=15),
    )


def temporary_files(directory: Path) -> list[Path]:
    """Localiza los archivos temporales creados por el repositorio."""

    if not directory.exists():
        return []
    return [path for path in directory.iterdir() if path.suffix == ".tmp"]


def assert_history_error(error: HistoryError) -> None:
    """Comprueba la clasificación estable de un error de historial."""

    assert error.error_type is ErrorType.INTERNAL
    assert error.error_stage is ErrorStage.HISTORY_WRITE


def test_load_returns_empty_list_when_file_does_not_exist(tmp_path: Path) -> None:
    """Devuelve una lista vacía si todavía no existe historial."""

    repository = HistoryRepository(tmp_path / "runtime" / "resultados.json")

    assert repository.load() == []


def test_append_creates_directory_and_history_file(tmp_path: Path) -> None:
    """Crea la carpeta y el archivo durante la primera escritura."""

    history_path = tmp_path / "runtime" / "resultados.json"
    repository = HistoryRepository(history_path)

    repository.append(make_result())

    assert history_path.is_file()
    assert len(repository.load()) == 1
    assert temporary_files(history_path.parent) == []


def test_append_preserves_previous_results(tmp_path: Path) -> None:
    """Añade resultados al final sin sobrescribir los anteriores."""

    repository = HistoryRepository(tmp_path / "resultados.json")
    first = make_result(attempt_number=1, identifier=1)
    second = make_result(attempt_number=2, identifier=2)

    repository.append(first)
    repository.append(second)

    loaded = repository.load()
    assert [result.id_procesamiento for result in loaded] == [
        first.id_procesamiento,
        second.id_procesamiento,
    ]


def test_round_trip_serializes_supported_types(tmp_path: Path) -> None:
    """Recupera UUID, fechas, decimales y enumeraciones con sus tipos."""

    repository = HistoryRepository(tmp_path / "resultados.json")
    original = make_result()

    repository.append(original)
    recovered = repository.load()[0]

    assert recovered.id_procesamiento == original.id_procesamiento
    assert isinstance(recovered.id_procesamiento, UUID)
    assert recovered.fecha_procesamiento == original.fecha_procesamiento
    assert isinstance(recovered.fecha_procesamiento, datetime)
    assert recovered.datos_extraidos is not None
    assert isinstance(recovered.datos_extraidos.fecha, date)
    assert recovered.duracion_segundos == Decimal("1.25")
    assert isinstance(recovered.duracion_segundos, Decimal)
    assert recovered.estado is ProcessingStatus.HAS_DIFFERENCES
    assert recovered.tipo_error is ErrorType.INTERNAL
    assert recovered.etapa_error is ErrorStage.COMPARISON


def test_rejects_invalid_json(tmp_path: Path) -> None:
    """Convierte JSON inválido en un error controlado."""

    history_path = tmp_path / "resultados.json"
    history_path.write_text("{invalid", encoding="utf-8")

    with pytest.raises(HistoryError, match="JSON válido") as captured:
        HistoryRepository(history_path).load()

    assert_history_error(captured.value)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ([], "raíz"),
        ({}, "clave 'resultados'"),
        ({"resultados": {}}, "contener una lista"),
    ],
)
def test_rejects_invalid_history_structure(
    tmp_path: Path,
    content: object,
    message: str,
) -> None:
    """Rechaza raíces, claves y colecciones con estructura incorrecta."""

    history_path = tmp_path / "resultados.json"
    history_path.write_text(json.dumps(content), encoding="utf-8")

    with pytest.raises(HistoryError, match=message):
        HistoryRepository(history_path).load()


def test_rejects_invalid_processing_result(tmp_path: Path) -> None:
    """Rechaza elementos que no cumplen el modelo de procesamiento."""

    history_path = tmp_path / "resultados.json"
    history_path.write_text(
        json.dumps({"resultados": [{"archivo": "incompleto.pdf"}]}),
        encoding="utf-8",
    )

    with pytest.raises(HistoryError, match="estructura inválida"):
        HistoryRepository(history_path).load()


def test_finds_results_by_fingerprint_in_original_order(tmp_path: Path) -> None:
    """Filtra por huella conservando el orden del historial."""

    repository = HistoryRepository(tmp_path / "resultados.json")
    repository.append(make_result(file_hash="target", attempt_number=1, identifier=1))
    repository.append(make_result(file_hash="other", attempt_number=1, identifier=2))
    repository.append(make_result(file_hash="target", attempt_number=2, identifier=3))

    results = repository.find_by_fingerprint("target")

    assert [result.numero_intento for result in results] == [1, 2]


def test_gets_latest_result_by_fingerprint(tmp_path: Path) -> None:
    """Devuelve el último intento de la huella solicitada."""

    repository = HistoryRepository(tmp_path / "resultados.json")
    repository.append(make_result(file_hash="target", attempt_number=1, identifier=1))
    repository.append(make_result(file_hash="target", attempt_number=2, identifier=2))

    latest = repository.get_latest_by_fingerprint("target")

    assert latest is not None
    assert latest.numero_intento == 2
    assert repository.get_latest_by_fingerprint("missing") is None


def test_calculates_next_attempt_number(tmp_path: Path) -> None:
    """Devuelve uno o incrementa el máximo intento de la huella."""

    repository = HistoryRepository(tmp_path / "resultados.json")
    assert repository.get_next_attempt_number("target") == 1

    repository.append(make_result(file_hash="target", attempt_number=2, identifier=1))
    repository.append(make_result(file_hash="target", attempt_number=5, identifier=2))
    repository.append(make_result(file_hash="other", attempt_number=9, identifier=3))

    assert repository.get_next_attempt_number("target") == 6


def test_clear_leaves_valid_empty_history(tmp_path: Path) -> None:
    """Reinicia el historial con una estructura JSON válida y legible."""

    history_path = tmp_path / "runtime" / "resultados.json"
    repository = HistoryRepository(history_path)
    repository.append(make_result())

    repository.clear()

    assert repository.load() == []
    assert json.loads(history_path.read_text(encoding="utf-8")) == {"resultados": []}
    assert temporary_files(history_path.parent) == []


def test_clear_creates_missing_parent_directory(tmp_path: Path) -> None:
    """Crea la carpeta de historial al reiniciar una instalación vacía."""

    history_path = tmp_path / "new-runtime" / "resultados.json"

    HistoryRepository(history_path).clear()

    assert json.loads(history_path.read_text(encoding="utf-8")) == {"resultados": []}
    assert temporary_files(history_path.parent) == []


def test_queries_reload_file_without_cache(tmp_path: Path) -> None:
    """Lee el contenido actual en cada consulta."""

    history_path = tmp_path / "resultados.json"
    repository = HistoryRepository(history_path)
    repository.append(make_result(file_hash="target"))
    assert len(repository.find_by_fingerprint("target")) == 1

    history_path.write_text('{"resultados": []}', encoding="utf-8")

    assert repository.find_by_fingerprint("target") == []


def test_append_does_not_modify_received_model(tmp_path: Path) -> None:
    """No modifica el resultado recibido durante la serialización."""

    repository = HistoryRepository(tmp_path / "resultados.json")
    result = make_result()
    original_dump = result.model_dump()

    repository.append(result)

    assert result.model_dump() == original_dump


def test_replace_failure_preserves_previous_file_and_removes_temporary(
    tmp_path: Path,
) -> None:
    """Conserva el archivo anterior y limpia el temporal si falla el reemplazo."""

    history_path = tmp_path / "resultados.json"
    repository = HistoryRepository(history_path)
    repository.append(make_result(identifier=1))
    original_bytes = history_path.read_bytes()

    with patch("src.history_repository.os.replace", side_effect=OSError("fallo interno")):
        with pytest.raises(HistoryError) as captured:
            repository.append(make_result(attempt_number=2, identifier=2))

    assert history_path.read_bytes() == original_bytes
    assert temporary_files(history_path.parent) == []
    assert_history_error(captured.value)


def test_error_does_not_expose_internal_path(tmp_path: Path) -> None:
    """Evita incluir rutas internas en los mensajes controlados."""

    internal_directory = tmp_path / "directorio-secreto"
    internal_directory.mkdir()
    repository = HistoryRepository(internal_directory)

    with pytest.raises(HistoryError) as captured:
        repository.load()

    assert str(internal_directory) not in str(captured.value)
    assert_history_error(captured.value)
