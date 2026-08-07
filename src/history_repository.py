"""Persistencia segura del historial local de procesamientos."""

import json
import os
from decimal import Decimal
from pathlib import Path
from tempfile import NamedTemporaryFile

from pydantic import ValidationError

from src.exceptions import HistoryError
from src.models import ProcessingResult


class HistoryRepository:
    """Gestiona el historial local sin mantener datos en caché."""

    def __init__(self, history_path: Path) -> None:
        """Inicializa el repositorio con la ruta de su archivo JSON."""

        self.history_path = history_path

    def load(self) -> list[ProcessingResult]:
        """Carga y valida todos los resultados almacenados."""

        try:
            if not self.history_path.exists():
                return []
            with self.history_path.open("r", encoding="utf-8") as history_file:
                content = json.load(history_file, parse_float=Decimal)
        except OSError:
            raise HistoryError("No se pudo leer el archivo de historial.") from None
        except (json.JSONDecodeError, UnicodeError):
            raise HistoryError("El archivo de historial no contiene un JSON válido.") from None

        if not isinstance(content, dict):
            raise HistoryError("La raíz del historial debe ser un objeto.")
        if "resultados" not in content:
            raise HistoryError("El historial no contiene la clave 'resultados'.")

        raw_results = content["resultados"]
        if not isinstance(raw_results, list):
            raise HistoryError("La clave 'resultados' debe contener una lista.")

        results: list[ProcessingResult] = []
        for raw_result in raw_results:
            try:
                results.append(ProcessingResult.model_validate(raw_result))
            except (ValidationError, ValueError, TypeError):
                raise HistoryError(
                    "El historial contiene un resultado con estructura inválida."
                ) from None
        return results

    def append(self, result: ProcessingResult) -> None:
        """Añade un resultado sin alterar los intentos anteriores."""

        results = self.load()
        results.append(result)
        self._write(results)

    def find_by_fingerprint(self, file_hash: str) -> list[ProcessingResult]:
        """Devuelve los intentos de una huella en su orden original."""

        return [
            result
            for result in self.load()
            if result.huella_archivo == file_hash
        ]

    def get_latest_by_fingerprint(self, file_hash: str) -> ProcessingResult | None:
        """Devuelve el último intento almacenado para una huella."""

        results = self.find_by_fingerprint(file_hash)
        return results[-1] if results else None

    def get_next_attempt_number(self, file_hash: str) -> int:
        """Calcula el siguiente número de intento para una huella."""

        results = self.find_by_fingerprint(file_hash)
        if not results:
            return 1
        return max(result.numero_intento for result in results) + 1

    def clear(self) -> None:
        """Reinicia el historial mediante una escritura segura."""

        self._write([])

    def _write(self, results: list[ProcessingResult]) -> None:
        """Escribe el historial con sustitución atómica y limpieza temporal."""

        temporary_path: Path | None = None
        try:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            serialized_results = [
                json.loads(result.model_dump_json()) for result in results
            ]
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.history_path.parent,
                prefix=f".{self.history_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                json.dump(
                    {"resultados": serialized_results},
                    temporary_file,
                    ensure_ascii=False,
                    indent=2,
                )
                temporary_file.write("\n")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, self.history_path)
        except Exception:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise HistoryError("No se pudo guardar el historial de forma segura.") from None
