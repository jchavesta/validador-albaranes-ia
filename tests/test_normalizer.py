"""Pruebas unitarias de las reglas de normalización."""

from datetime import date
from decimal import Decimal

import pytest

from src.models import DeliveryNoteData
from src.normalizer import Normalizer


@pytest.fixture
def normalizer() -> Normalizer:
    """Proporciona un normalizador sin estado."""

    return Normalizer()


def test_normalizes_supplier_tax_id(normalizer: Normalizer) -> None:
    """Elimina espacios y separadores y convierte el CIF a mayúsculas."""

    assert normalizer.normalize_supplier_tax_id(" b-12. 345 678 ") == "B12345678"


def test_delivery_note_numbers_are_equivalent_by_case_and_spaces(
    normalizer: Normalizer,
) -> None:
    """Iguala números que solo difieren en espacios y mayúsculas."""

    first = normalizer.normalize_delivery_note_number(" alb - 001 / a ")
    second = normalizer.normalize_delivery_note_number("ALB-001/A")

    assert first == second


def test_preserves_delivery_note_number_separators(normalizer: Normalizer) -> None:
    """Conserva guiones, barras y puntos internos del número."""

    assert normalizer.normalize_delivery_note_number(" ab-12/3.4 ") == "AB-12/3.4"


def test_normalizes_supplier_name_with_accents(normalizer: Normalizer) -> None:
    """Reduce espacios sin eliminar los acentos del proveedor."""

    assert (
        normalizer.normalize_supplier_name("  Distribución   Ibérica  ")
        == "DISTRIBUCIÓN IBÉRICA"
    )


def test_preserves_date_instance(normalizer: Normalizer) -> None:
    """Conserva sin cambios una fecha ya convertida."""

    value = date(2026, 8, 7)

    assert normalizer.normalize_date(value) is value


def test_converts_iso_date(normalizer: Normalizer) -> None:
    """Convierte una cadena ISO en fecha."""

    assert normalizer.normalize_date("2026-08-07") == date(2026, 8, 7)


@pytest.mark.parametrize("value", ["2026-02-30", "20260807", "07/08/2026"])
def test_rejects_invalid_date(normalizer: Normalizer, value: str) -> None:
    """Rechaza fechas inválidas o que no usan el formato requerido."""

    with pytest.raises(ValueError, match="formato ISO válido"):
        normalizer.normalize_date(value)


def test_normalizes_amount_with_decimal_point(normalizer: Normalizer) -> None:
    """Normaliza un importe cuyo separador decimal es un punto."""

    assert normalizer.normalize_amount("1250.75") == Decimal("1250.75")


def test_normalizes_amount_with_decimal_comma(normalizer: Normalizer) -> None:
    """Normaliza un importe cuyo separador decimal es una coma."""

    assert normalizer.normalize_amount("1250,75") == Decimal("1250.75")


def test_normalizes_amount_with_thousands_and_decimal_comma(
    normalizer: Normalizer,
) -> None:
    """Elimina el separador de miles y conserva la coma decimal."""

    assert normalizer.normalize_amount("1.250,75") == Decimal("1250.75")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1.005", Decimal("1.01")),
        (Decimal("2.344"), Decimal("2.34")),
        (Decimal("2.345"), Decimal("2.35")),
    ],
)
def test_rounds_amount_with_round_half_up(
    normalizer: Normalizer,
    value: str | Decimal,
    expected: Decimal,
) -> None:
    """Redondea importes exactamente con ROUND_HALF_UP."""

    assert normalizer.normalize_amount(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (" € ", "EUR"),
        ("euro", "EUR"),
        ("Euros", "EUR"),
        ("$", "USD"),
        (" £ ", "GBP"),
        ("eur", "EUR"),
        (" usd ", "USD"),
        ("gbp", "GBP"),
    ],
)
def test_normalizes_known_currencies(
    normalizer: Normalizer,
    value: str,
    expected: str,
) -> None:
    """Normaliza símbolos, nombres y códigos conocidos."""

    assert normalizer.normalize_currency(value) == expected


def test_normalizes_complete_model_with_none_values(normalizer: Normalizer) -> None:
    """Normaliza solo los campos presentes y conserva los valores nulos."""

    data = DeliveryNoteData(
        numero_albaran=" alb-1 ",
        cif_proveedor=None,
        proveedor="  Proveedor   Ágil ",
        fecha=None,
        importe_total=Decimal("1.005"),
        moneda=None,
    )

    result = normalizer.normalize_delivery_note(data)

    assert result.numero_albaran == "ALB-1"
    assert result.cif_proveedor is None
    assert result.proveedor == "PROVEEDOR ÁGIL"
    assert result.fecha is None
    assert result.importe_total == Decimal("1.01")
    assert result.moneda is None


def test_preserves_unread_fields_and_observations(normalizer: Normalizer) -> None:
    """Conserva campos no leídos y observaciones en el nuevo modelo."""

    data = DeliveryNoteData(
        numero_albaran=None,
        cif_proveedor=None,
        proveedor=None,
        fecha=None,
        importe_total=None,
        moneda=None,
        campos_no_leidos=["fecha"],
        observaciones=["Texto borroso"],
    )

    result = normalizer.normalize_delivery_note(data)

    assert result.campos_no_leidos == ["fecha"]
    assert result.observaciones == ["Texto borroso"]
    assert result.campos_no_leidos is not data.campos_no_leidos
    assert result.observaciones is not data.observaciones


def test_does_not_mutate_original_model(normalizer: Normalizer) -> None:
    """Devuelve un modelo nuevo sin modificar el original."""

    data = DeliveryNoteData(
        numero_albaran=" alb-001 ",
        cif_proveedor=" b-12345678 ",
        proveedor=" Proveedor   Único ",
        fecha=date(2026, 8, 7),
        importe_total=Decimal("10.005"),
        moneda=" € ",
        campos_no_leidos=["moneda"],
        observaciones=["Revisar"],
    )
    original_dump = data.model_dump()

    result = normalizer.normalize_delivery_note(data)

    assert result is not data
    assert data.model_dump() == original_dump
