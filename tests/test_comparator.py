"""Pruebas unitarias del comparador de albaranes."""

from datetime import date
from decimal import Decimal

import pytest

from src.comparator import DeliveryNoteComparator
from src.models import DeliveryNoteData


def make_delivery_note(**overrides: object) -> DeliveryNoteData:
    """Construye un albarán normalizado con cambios opcionales."""

    values = {
        "numero_albaran": "ALB-001",
        "cif_proveedor": "B12345678",
        "proveedor": "PROVEEDOR FICTICIO SL",
        "fecha": date(2026, 8, 7),
        "importe_total": Decimal("1250.75"),
        "moneda": "EUR",
    }
    values.update(overrides)
    return DeliveryNoteData(**values)


@pytest.fixture
def comparator() -> DeliveryNoteComparator:
    """Proporciona un comparador sin estado."""

    return DeliveryNoteComparator()


def test_all_comparable_fields_match(comparator: DeliveryNoteComparator) -> None:
    """Indica coincidencia cuando todos los campos comparables son iguales."""

    result = comparator.compare(make_delivery_note(), make_delivery_note())

    assert result.coincide is True
    assert result.diferencias == []


@pytest.mark.parametrize(
    ("field_name", "different_value"),
    [
        ("proveedor", "OTRO PROVEEDOR SL"),
        ("fecha", date(2026, 8, 8)),
        ("importe_total", Decimal("1250.76")),
        ("moneda", "USD"),
    ],
)
def test_detects_one_difference_in_each_comparable_field(
    comparator: DeliveryNoteComparator,
    field_name: str,
    different_value: object,
) -> None:
    """Detecta individualmente cada campo comparable."""

    extracted = make_delivery_note(**{field_name: different_value})
    reference = make_delivery_note()

    result = comparator.compare(extracted, reference)

    assert result.coincide is False
    assert [difference.campo for difference in result.diferencias] == [field_name]


def test_multiple_differences_keep_deterministic_order(
    comparator: DeliveryNoteComparator,
) -> None:
    """Conserva el orden proveedor, fecha, importe y moneda."""

    extracted = make_delivery_note(
        proveedor="OTRO PROVEEDOR SL",
        fecha=date(2026, 8, 8),
        importe_total=Decimal("10.00"),
        moneda="USD",
    )

    result = comparator.compare(extracted, make_delivery_note())

    assert [difference.campo for difference in result.diferencias] == [
        "proveedor",
        "fecha",
        "importe_total",
        "moneda",
    ]


def test_identity_fields_do_not_affect_result(
    comparator: DeliveryNoteComparator,
) -> None:
    """Ignora número de albarán y CIF durante la comparación."""

    extracted = make_delivery_note(
        numero_albaran="OTRO-999",
        cif_proveedor="A00000000",
    )

    result = comparator.compare(extracted, make_delivery_note())

    assert result.coincide is True
    assert result.diferencias == []


def test_two_none_values_are_equal(comparator: DeliveryNoteComparator) -> None:
    """Considera iguales dos valores nulos del mismo campo."""

    result = comparator.compare(
        make_delivery_note(proveedor=None),
        make_delivery_note(proveedor=None),
    )

    assert result.coincide is True
    assert result.diferencias == []


def test_none_against_value_creates_difference(
    comparator: DeliveryNoteComparator,
) -> None:
    """Registra una diferencia cuando solo uno de los valores es nulo."""

    result = comparator.compare(
        make_delivery_note(moneda=None),
        make_delivery_note(moneda="EUR"),
    )

    assert result.coincide is False
    assert len(result.diferencias) == 1
    assert result.diferencias[0].campo == "moneda"
    assert result.diferencias[0].valor_pdf is None
    assert result.diferencias[0].valor_referencia == "EUR"


def test_compares_normalized_decimals_exactly(
    comparator: DeliveryNoteComparator,
) -> None:
    """Compara exactamente el valor numérico de importes Decimal."""

    equal_result = comparator.compare(
        make_delivery_note(importe_total=Decimal("1.01")),
        make_delivery_note(importe_total=Decimal("1.010")),
    )
    different_result = comparator.compare(
        make_delivery_note(importe_total=Decimal("1.01")),
        make_delivery_note(importe_total=Decimal("1.02")),
    )

    assert equal_result.coincide is True
    assert different_result.coincide is False
    assert different_result.diferencias[0].campo == "importe_total"


def test_does_not_modify_original_models(
    comparator: DeliveryNoteComparator,
) -> None:
    """No modifica ninguno de los modelos recibidos."""

    extracted = make_delivery_note(proveedor="OTRO PROVEEDOR SL")
    reference = make_delivery_note()
    extracted_before = extracted.model_dump()
    reference_before = reference.model_dump()

    comparator.compare(extracted, reference)

    assert extracted.model_dump() == extracted_before
    assert reference.model_dump() == reference_before


def test_field_difference_stores_expected_values(
    comparator: DeliveryNoteComparator,
) -> None:
    """Conserva los valores exactos del PDF y de la referencia."""

    pdf_date = date(2026, 8, 9)
    reference_date = date(2026, 8, 7)

    result = comparator.compare(
        make_delivery_note(fecha=pdf_date),
        make_delivery_note(fecha=reference_date),
    )

    difference = result.diferencias[0]
    assert difference.campo == "fecha"
    assert difference.valor_pdf == pdf_date
    assert difference.valor_referencia == reference_date
