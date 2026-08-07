"""Pruebas unitarias del repositorio de datos de referencia."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from src.exceptions import ReferenceDataError
from src.models import ErrorStage, ErrorType
from src.normalizer import Normalizer
from src.reference_repository import ReferenceRepository


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "albaranes_test.json"


@pytest.fixture
def repository() -> ReferenceRepository:
    """Proporciona el repositorio basado en el fixture válido."""

    return ReferenceRepository(FIXTURE_PATH, Normalizer())


def valid_record(**overrides):
    """Construye un registro JSON válido con cambios opcionales."""

    record = {
        "numero_albaran": "ALB-001",
        "cif_proveedor": "B12345678",
        "proveedor": "Proveedor Ficticio SL",
        "fecha": "2026-08-06",
        "importe_total": 1250.75,
        "moneda": "EUR",
    }
    record.update(overrides)
    return record


def write_reference(path: Path, content: object) -> None:
    """Escribe un JSON particular para una prueba aislada."""

    path.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")


def create_repository(path: Path) -> ReferenceRepository:
    """Crea un repositorio para una ruta temporal."""

    return ReferenceRepository(path, Normalizer())


def assert_reference_error(error: ReferenceDataError) -> None:
    """Comprueba la clasificación estable del error de referencia."""

    assert error.error_type is ErrorType.REFERENCE_DATA
    assert error.error_stage is ErrorStage.REFERENCE_LOADING


def test_loads_valid_fixture(repository: ReferenceRepository) -> None:
    """Carga registros ficticios válidos conservando precisión decimal."""

    records = repository.load()

    assert len(records) == 2
    assert records[0].numero_albaran == "ALB-001/25.1"
    assert records[0].importe_total == Decimal("1250.75")
    assert isinstance(records[0].importe_total, Decimal)


def test_rejects_missing_file(tmp_path: Path) -> None:
    """Convierte la ausencia del archivo en un error controlado."""

    with pytest.raises(ReferenceDataError) as captured:
        create_repository(tmp_path / "missing.json").load()

    assert_reference_error(captured.value)
    assert str(tmp_path) not in str(captured.value)


def test_rejects_invalid_json(tmp_path: Path) -> None:
    """Rechaza contenido que no sea JSON válido."""

    path = tmp_path / "references.json"
    path.write_text("{invalid", encoding="utf-8")

    with pytest.raises(ReferenceDataError, match="JSON válido") as captured:
        create_repository(path).load()

    assert_reference_error(captured.value)


def test_rejects_non_object_root(tmp_path: Path) -> None:
    """Rechaza una raíz JSON que no sea un objeto."""

    path = tmp_path / "references.json"
    write_reference(path, [])

    with pytest.raises(ReferenceDataError, match="raíz"):
        create_repository(path).load()


def test_rejects_missing_delivery_notes_key(tmp_path: Path) -> None:
    """Rechaza un objeto sin la clave albaranes."""

    path = tmp_path / "references.json"
    write_reference(path, {})

    with pytest.raises(ReferenceDataError, match="clave 'albaranes'"):
        create_repository(path).load()


def test_rejects_non_list_delivery_notes(tmp_path: Path) -> None:
    """Rechaza una colección de albaranes que no sea una lista."""

    path = tmp_path / "references.json"
    write_reference(path, {"albaranes": {}})

    with pytest.raises(ReferenceDataError, match="debe ser una lista"):
        create_repository(path).load()


@pytest.mark.parametrize(
    "record",
    [
        {"numero_albaran": "ALB-001"},
        valid_record(importe_total=[]),
        valid_record(fecha="fecha-inválida"),
        "registro-inválido",
    ],
)
def test_rejects_invalid_record_structure(tmp_path: Path, record: object) -> None:
    """Rechaza registros con estructura, fecha o tipo inválidos."""

    path = tmp_path / "references.json"
    write_reference(path, {"albaranes": [record]})

    with pytest.raises(ReferenceDataError, match="estructura válida"):
        create_repository(path).load()


def test_rejects_null_required_field(tmp_path: Path) -> None:
    """Rechaza registros con cualquiera de sus campos obligatorios nulo."""

    path = tmp_path / "references.json"
    write_reference(path, {"albaranes": [valid_record(moneda=None)]})

    with pytest.raises(ReferenceDataError, match="obligatorios nulos"):
        create_repository(path).load()


def test_finds_record_by_supplier_and_number(repository: ReferenceRepository) -> None:
    """Encuentra un registro mediante CIF y número de albarán."""

    record = repository.find("B12345678", "ALB-001/25.1")

    assert record is not None
    assert record.proveedor == "Distribuciones Ejemplo SL"


def test_finds_record_with_normalized_identity(repository: ReferenceRepository) -> None:
    """Normaliza espacios, mayúsculas y separadores del CIF al buscar."""

    record = repository.find(" b-12.345 678 ", " alb-001/25.1 ")

    assert record is not None
    assert record.cif_proveedor == "B12345678"


def test_preserves_number_separators_when_finding(
    repository: ReferenceRepository,
) -> None:
    """Conserva guiones, barras y puntos como parte de la identidad."""

    assert repository.find("B12345678", "ALB-001/25.1") is not None
    assert repository.find("B12345678", "ALB001251") is None


def test_returns_none_for_unknown_combination(repository: ReferenceRepository) -> None:
    """Devuelve nulo cuando la combinación no está registrada."""

    assert repository.find("Z00000000", "UNKNOWN-1") is None


def test_rejects_exact_duplicate(tmp_path: Path) -> None:
    """Detecta una identidad duplicada exactamente."""

    path = tmp_path / "references.json"
    record = valid_record()
    write_reference(path, {"albaranes": [record, record]})

    with pytest.raises(ReferenceDataError, match="duplicados"):
        create_repository(path).validate_uniqueness()


def test_rejects_duplicate_after_normalization(tmp_path: Path) -> None:
    """Detecta duplicados después de normalizar ambas claves."""

    path = tmp_path / "references.json"
    first = valid_record()
    second = valid_record(
        cif_proveedor=" b-12.345 678 ",
        numero_albaran=" alb-001 ",
        proveedor="Otro proveedor",
    )
    write_reference(path, {"albaranes": [first, second]})

    with pytest.raises(ReferenceDataError, match="duplicados"):
        create_repository(path).validate_uniqueness()


def test_find_also_rejects_duplicates(tmp_path: Path) -> None:
    """Impide buscar silenciosamente cuando existen duplicados."""

    path = tmp_path / "references.json"
    record = valid_record()
    write_reference(path, {"albaranes": [record, record]})

    with pytest.raises(ReferenceDataError, match="duplicados"):
        create_repository(path).find("B12345678", "ALB-001")


def test_operations_do_not_modify_reference_file(tmp_path: Path) -> None:
    """Conserva exactamente los bytes del archivo en todas las operaciones."""

    path = tmp_path / "references.json"
    original_bytes = FIXTURE_PATH.read_bytes()
    path.write_bytes(original_bytes)
    repository = create_repository(path)

    repository.load()
    repository.validate_uniqueness()
    repository.find("B12345678", "ALB-001/25.1")

    assert path.read_bytes() == original_bytes


def test_each_operation_reads_current_file_content(tmp_path: Path) -> None:
    """Vuelve a leer el archivo en cada operación sin usar caché."""

    path = tmp_path / "references.json"
    write_reference(path, {"albaranes": [valid_record()]})
    repository = create_repository(path)
    assert repository.find("B12345678", "ALB-001") is not None

    write_reference(path, {"albaranes": []})

    assert repository.find("B12345678", "ALB-001") is None
