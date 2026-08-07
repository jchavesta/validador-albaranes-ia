"""Operaciones puras para normalizar datos de albaranes."""

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from src.models import DeliveryNoteData


class Normalizer:
    """Normaliza los campos utilizados en búsquedas y comparaciones."""

    _AMOUNT_PRECISION = Decimal("0.01")

    def normalize_supplier_tax_id(self, value: str) -> str:
        """Normaliza un CIF conservando únicamente letras y números."""

        return "".join(character for character in value.upper() if character.isalnum())

    def normalize_delivery_note_number(self, value: str) -> str:
        """Normaliza un número sin eliminar sus separadores internos."""

        return "".join(character for character in value.upper() if not character.isspace())

    def normalize_supplier_name(self, value: str) -> str:
        """Normaliza mayúsculas y espacios del nombre del proveedor."""

        return " ".join(value.split()).upper()

    def normalize_date(self, value: str | date) -> date:
        """Normaliza una fecha ISO o conserva una fecha ya convertida."""

        if isinstance(value, date):
            return value
        if (
            not isinstance(value, str)
            or len(value) != 10
            or value[4] != "-"
            or value[7] != "-"
        ):
            raise ValueError("La fecha no tiene un formato ISO válido.")
        try:
            return date.fromisoformat(value)
        except (TypeError, ValueError):
            raise ValueError("La fecha no tiene un formato ISO válido.") from None

    def normalize_amount(self, value: str | Decimal) -> Decimal:
        """Normaliza un importe y aplica redondeo financiero a dos decimales."""

        if isinstance(value, Decimal):
            amount = value
        else:
            normalized = "".join(value.split())
            if "." in normalized and "," in normalized:
                decimal_separator = "." if normalized.rfind(".") > normalized.rfind(",") else ","
                thousands_separator = "," if decimal_separator == "." else "."
                normalized = normalized.replace(thousands_separator, "")
                if decimal_separator == ",":
                    normalized = normalized.replace(",", ".")
            elif "," in normalized:
                normalized = normalized.replace(",", ".")

            try:
                amount = Decimal(normalized)
            except (InvalidOperation, ValueError):
                raise ValueError("El importe no tiene un formato válido.") from None

        if not amount.is_finite():
            raise ValueError("El importe no tiene un formato válido.")
        return amount.quantize(self._AMOUNT_PRECISION, rounding=ROUND_HALF_UP)

    def normalize_currency(self, value: str) -> str:
        """Normaliza símbolos y nombres habituales de moneda."""

        normalized = "".join(value.split()).upper()
        currency_codes = {
            "€": "EUR",
            "EURO": "EUR",
            "EUROS": "EUR",
            "$": "USD",
            "£": "GBP",
        }
        return currency_codes.get(normalized, normalized)

    def normalize_delivery_note(self, data: DeliveryNoteData) -> DeliveryNoteData:
        """Devuelve una copia normalizada sin modificar el modelo recibido."""

        return DeliveryNoteData(
            numero_albaran=(
                self.normalize_delivery_note_number(data.numero_albaran)
                if data.numero_albaran is not None
                else None
            ),
            cif_proveedor=(
                self.normalize_supplier_tax_id(data.cif_proveedor)
                if data.cif_proveedor is not None
                else None
            ),
            proveedor=(
                self.normalize_supplier_name(data.proveedor)
                if data.proveedor is not None
                else None
            ),
            fecha=self.normalize_date(data.fecha) if data.fecha is not None else None,
            importe_total=(
                self.normalize_amount(data.importe_total)
                if data.importe_total is not None
                else None
            ),
            moneda=(
                self.normalize_currency(data.moneda)
                if data.moneda is not None
                else None
            ),
            campos_no_leidos=list(data.campos_no_leidos),
            observaciones=list(data.observaciones),
        )
