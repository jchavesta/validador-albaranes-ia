"""Validación local de documentos PDF y cálculo de su huella."""

from hashlib import sha256
from pathlib import Path

from pypdf import PdfReader

from src.exceptions import PdfValidationError
from src.models import PdfInfo


class PdfValidator:
    """Valida documentos PDF antes de iniciar su extracción."""

    _HASH_BLOCK_SIZE = 64 * 1024

    def __init__(self, max_pages: int = 3) -> None:
        """Inicializa el validador con el máximo de páginas permitido."""

        if max_pages < 1:
            raise ValueError("max_pages debe ser al menos 1")
        self.max_pages = max_pages

    def validate(self, path: Path) -> PdfInfo:
        """Valida un PDF y devuelve su información básica y huella."""

        try:
            exists = path.exists()
        except OSError:
            raise PdfValidationError(
                "No se pudo comprobar la existencia del archivo."
            ) from None
        if not exists:
            raise PdfValidationError("El archivo seleccionado no existe.")

        try:
            is_file = path.is_file()
        except OSError:
            raise PdfValidationError(
                "No se pudo comprobar el tipo del archivo seleccionado."
            ) from None
        if not is_file:
            raise PdfValidationError("La ruta seleccionada no es un archivo.")

        if path.suffix.lower() != ".pdf":
            raise PdfValidationError("El archivo seleccionado no tiene extensión PDF.")

        try:
            reader = PdfReader(path)
        except Exception:
            raise PdfValidationError("No se pudo abrir el archivo PDF.") from None

        try:
            is_encrypted = reader.is_encrypted
        except Exception:
            raise PdfValidationError("No se pudo abrir el archivo PDF.") from None
        if is_encrypted:
            raise PdfValidationError("El archivo PDF está protegido con contraseña.")

        try:
            page_count = len(reader.pages)
        except Exception:
            raise PdfValidationError("No se pudieron leer las páginas del PDF.") from None

        if page_count == 0:
            raise PdfValidationError("El archivo PDF no contiene páginas.")
        if page_count > self.max_pages:
            raise PdfValidationError(
                f"El archivo PDF supera el máximo permitido de {self.max_pages} páginas."
            )

        try:
            has_extractable_text = any(
                (page.extract_text() or "").strip() for page in reader.pages
            )
        except Exception:
            raise PdfValidationError("No se pudo extraer el texto del PDF.") from None
        if not has_extractable_text:
            raise PdfValidationError("El archivo PDF no contiene texto extraíble.")

        try:
            size_bytes = path.stat().st_size
        except OSError:
            raise PdfValidationError("No se pudo obtener el tamaño del archivo.") from None

        return PdfInfo(
            path=path,
            file_name=path.name,
            size_bytes=size_bytes,
            page_count=page_count,
            file_hash=self.calculate_fingerprint(path),
            has_extractable_text=True,
        )

    def calculate_fingerprint(self, path: Path) -> str:
        """Calcula la huella SHA-256 leyendo el archivo por bloques."""

        digest = sha256()
        try:
            with path.open("rb") as pdf_file:
                while block := pdf_file.read(self._HASH_BLOCK_SIZE):
                    digest.update(block)
        except OSError:
            raise PdfValidationError(
                "No se pudo leer el archivo para calcular su huella."
            ) from None
        return digest.hexdigest()
