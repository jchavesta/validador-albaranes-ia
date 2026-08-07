"""Pruebas unitarias del validador local de PDF."""

from hashlib import sha256
from unittest.mock import MagicMock, patch

import pytest
from pypdf import PdfWriter

from src.exceptions import PdfValidationError
from src.models import ErrorStage, ErrorType
from src.pdf_validator import PdfValidator


def write_pdf(path, page_count: int = 1, password: str | None = None) -> None:
    """Crea un PDF de prueba con páginas en blanco."""

    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=100, height=100)
    if password is not None:
        writer.encrypt(password)
    with path.open("wb") as output_file:
        writer.write(output_file)


def mocked_reader_with_text() -> MagicMock:
    """Construye un lector simulado con una página de texto."""

    page = MagicMock()
    page.extract_text.return_value = "Texto del albarán"
    reader = MagicMock()
    reader.is_encrypted = False
    reader.pages = [page]
    return reader


def test_rejects_invalid_max_pages() -> None:
    """Rechaza límites inferiores a una página."""

    with pytest.raises(ValueError, match="al menos 1"):
        PdfValidator(max_pages=0)


def test_rejects_missing_file(tmp_path) -> None:
    """Rechaza un archivo inexistente."""

    with pytest.raises(PdfValidationError, match="no existe"):
        PdfValidator().validate(tmp_path / "missing.pdf")


def test_rejects_path_that_is_not_file(tmp_path) -> None:
    """Rechaza una ruta que apunta a un directorio."""

    pdf_directory = tmp_path / "document.pdf"
    pdf_directory.mkdir()

    with pytest.raises(PdfValidationError, match="no es un archivo"):
        PdfValidator().validate(pdf_directory)


def test_rejects_non_pdf_extension(tmp_path) -> None:
    """Rechaza archivos cuya extensión no es PDF."""

    text_file = tmp_path / "document.txt"
    text_file.write_text("contenido", encoding="utf-8")

    with pytest.raises(PdfValidationError, match="extensión PDF"):
        PdfValidator().validate(text_file)


def test_rejects_pdf_that_cannot_be_opened(tmp_path) -> None:
    """Convierte un PDF corrupto en un error controlado."""

    invalid_pdf = tmp_path / "invalid.pdf"
    invalid_pdf.write_bytes(b"not a pdf")

    with pytest.raises(PdfValidationError, match="No se pudo abrir"):
        PdfValidator().validate(invalid_pdf)


def test_rejects_encrypted_pdf(tmp_path) -> None:
    """Rechaza un PDF protegido mediante contraseña."""

    encrypted_pdf = tmp_path / "encrypted.pdf"
    write_pdf(encrypted_pdf, password="test-password")

    with pytest.raises(PdfValidationError, match="protegido"):
        PdfValidator().validate(encrypted_pdf)


def test_rejects_pdf_without_pages(tmp_path) -> None:
    """Rechaza un PDF que no contiene páginas."""

    empty_pdf = tmp_path / "empty.pdf"
    write_pdf(empty_pdf, page_count=0)

    with pytest.raises(PdfValidationError, match="no contiene páginas"):
        PdfValidator().validate(empty_pdf)


def test_rejects_pdf_without_extractable_text(tmp_path) -> None:
    """Rechaza un PDF cuyas páginas no contienen texto."""

    blank_pdf = tmp_path / "blank.pdf"
    write_pdf(blank_pdf)

    with pytest.raises(PdfValidationError, match="texto extraíble"):
        PdfValidator().validate(blank_pdf)


def test_rejects_pdf_over_page_limit(tmp_path) -> None:
    """Rechaza un PDF que supera el máximo configurado."""

    long_pdf = tmp_path / "long.pdf"
    write_pdf(long_pdf, page_count=2)

    with pytest.raises(PdfValidationError, match="máximo permitido de 1"):
        PdfValidator(max_pages=1).validate(long_pdf)


def test_returns_pdf_info_for_valid_pdf_with_mocked_text(tmp_path) -> None:
    """Devuelve la información esperada para un PDF válido."""

    pdf_path = tmp_path / "valid.pdf"
    content = b"mock pdf content"
    pdf_path.write_bytes(content)

    with patch("src.pdf_validator.PdfReader", return_value=mocked_reader_with_text()):
        info = PdfValidator().validate(pdf_path)

    assert info.path == pdf_path
    assert info.file_name == "valid.pdf"
    assert info.size_bytes == len(content)
    assert info.page_count == 1
    assert info.file_hash == sha256(content).hexdigest()
    assert info.has_extractable_text is True


def test_calculates_stable_sha256_fingerprint(tmp_path) -> None:
    """Calcula una huella SHA-256 correcta y estable."""

    pdf_path = tmp_path / "fingerprint.pdf"
    content = b"a" * 100_000 + b"stable content"
    pdf_path.write_bytes(content)
    validator = PdfValidator()

    first_fingerprint = validator.calculate_fingerprint(pdf_path)
    second_fingerprint = validator.calculate_fingerprint(pdf_path)

    assert first_fingerprint == sha256(content).hexdigest()
    assert second_fingerprint == first_fingerprint


def test_accepts_uppercase_pdf_extension(tmp_path) -> None:
    """Acepta la extensión PDF escrita en mayúsculas."""

    pdf_path = tmp_path / "document.PDF"
    pdf_path.write_bytes(b"mock pdf content")

    with patch("src.pdf_validator.PdfReader", return_value=mocked_reader_with_text()):
        info = PdfValidator().validate(pdf_path)

    assert info.file_name == "document.PDF"


def test_converts_reader_errors_without_exposing_details(tmp_path) -> None:
    """Convierte errores de lectura sin revelar detalles internos."""

    pdf_path = tmp_path / "document.pdf"
    pdf_path.write_bytes(b"mock pdf content")

    with patch(
        "src.pdf_validator.PdfReader",
        side_effect=OSError("/internal/secret/path"),
    ):
        with pytest.raises(PdfValidationError) as captured:
            PdfValidator().validate(pdf_path)

    assert captured.value.error_type is ErrorType.FILE
    assert captured.value.error_stage is ErrorStage.PDF_VALIDATION
    assert str(captured.value) == "No se pudo abrir el archivo PDF."
    assert "/internal/secret/path" not in str(captured.value)


def test_converts_fingerprint_file_errors(tmp_path) -> None:
    """Convierte errores de archivo al calcular la huella."""

    missing_pdf = tmp_path / "missing.pdf"

    with pytest.raises(PdfValidationError, match="calcular su huella"):
        PdfValidator().calculate_fingerprint(missing_pdf)
