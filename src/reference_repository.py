"""Repositorio de solo lectura para los datos de referencia."""

import json
from decimal import Decimal
from pathlib import Path

from pydantic import ValidationError

from src.exceptions import ReferenceDataError
from src.models import DeliveryNoteData
from src.normalizer import Normalizer


class ReferenceRepository:
    """Carga, valida y consulta albaranes de referencia sin modificarlos."""

    _REQUIRED_FIELDS = (
        "numero_albaran",
        "cif_proveedor",
        "proveedor",
        "fecha",
        "importe_total",
        "moneda",
    )

    def __init__(self, reference_path: Path, normalizer: Normalizer) -> None:
        """Inicializa el repositorio con su ruta y normalizador."""

        self.reference_path = reference_path
        self.normalizer = normalizer

    def load(self) -> list[DeliveryNoteData]:
        """Carga y valida todos los registros del archivo de referencia."""

        try:
            with self.reference_path.open("r", encoding="utf-8") as reference_file:
                content = json.load(reference_file, parse_float=Decimal)
        except OSError:
            raise ReferenceDataError(
                "No se pudo leer el archivo de datos de referencia."
            ) from None
        except (json.JSONDecodeError, UnicodeError):
            raise ReferenceDataError(
                "El archivo de datos de referencia no contiene un JSON válido."
            ) from None

        if not isinstance(content, dict):
            raise ReferenceDataError(
                "La raíz de los datos de referencia debe ser un objeto."
            )
        if "albaranes" not in content:
            raise ReferenceDataError(
                "Los datos de referencia no contienen la clave 'albaranes'."
            )

        raw_records = content["albaranes"]
        if not isinstance(raw_records, list):
            raise ReferenceDataError(
                "La clave 'albaranes' de los datos de referencia debe ser una lista."
            )

        records: list[DeliveryNoteData] = []
        for raw_record in raw_records:
            try:
                record = DeliveryNoteData.model_validate(raw_record)
            except (ValidationError, ValueError, TypeError):
                raise ReferenceDataError(
                    "Un registro de los datos de referencia no tiene una estructura válida."
                ) from None

            if any(getattr(record, field) is None for field in self._REQUIRED_FIELDS):
                raise ReferenceDataError(
                    "Un registro de referencia contiene campos obligatorios nulos."
                )
            records.append(record)

        return records

    def validate_uniqueness(self) -> None:
        """Comprueba la unicidad de CIF y número después de normalizarlos."""

        self._ensure_unique(self.load())

    def find(
        self,
        supplier_tax_id: str,
        delivery_note_number: str,
    ) -> DeliveryNoteData | None:
        """Busca un registro por su identidad normalizada."""

        records = self.load()
        self._ensure_unique(records)
        target_key = (
            self.normalizer.normalize_supplier_tax_id(supplier_tax_id),
            self.normalizer.normalize_delivery_note_number(delivery_note_number),
        )

        for record in records:
            record_key = self._identity_key(record)
            if record_key == target_key:
                return record
        return None

    def _ensure_unique(self, records: list[DeliveryNoteData]) -> None:
        """Rechaza combinaciones normalizadas de identidad repetidas."""

        identities: set[tuple[str, str]] = set()
        for record in records:
            identity = self._identity_key(record)
            if identity in identities:
                raise ReferenceDataError(
                    "Los datos de referencia contienen albaranes duplicados."
                )
            identities.add(identity)

    def _identity_key(self, record: DeliveryNoteData) -> tuple[str, str]:
        """Obtiene la identidad normalizada de un registro completo."""

        if record.cif_proveedor is None or record.numero_albaran is None:
            raise ReferenceDataError(
                "Un registro de referencia no contiene una identidad completa."
            )
        return (
            self.normalizer.normalize_supplier_tax_id(record.cif_proveedor),
            self.normalizer.normalize_delivery_note_number(record.numero_albaran),
        )
