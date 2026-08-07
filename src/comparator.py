"""Comparación determinista de albaranes normalizados."""

from src.models import ComparisonResult, DeliveryNoteData, FieldDifference


class DeliveryNoteComparator:
    """Compara los campos de negocio de dos albaranes normalizados."""

    _COMPARABLE_FIELDS = ("proveedor", "fecha", "importe_total", "moneda")

    def compare(
        self,
        extracted: DeliveryNoteData,
        reference: DeliveryNoteData,
    ) -> ComparisonResult:
        """Devuelve las diferencias en un orden estable y predefinido."""

        differences = [
            FieldDifference(
                campo=field_name,
                valor_pdf=getattr(extracted, field_name),
                valor_referencia=getattr(reference, field_name),
            )
            for field_name in self._COMPARABLE_FIELDS
            if getattr(extracted, field_name) != getattr(reference, field_name)
        ]
        return ComparisonResult(
            coincide=not differences,
            diferencias=differences,
        )
