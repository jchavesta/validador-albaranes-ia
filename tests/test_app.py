"""Pruebas unitarias de los auxiliares y ensamblaje de la interfaz."""

import importlib
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src import app
from src.config import AppConfig
from src.exceptions import PdfValidationError, ReprocessingConfirmationError
from src.models import (
    ApiUsage,
    DeliveryNoteData,
    ProcessingResult,
    ProcessingStatus,
)


def make_config(
    tmp_path: Path,
    api_key: str | None = None,
) -> AppConfig:
    """Crea configuración aislada sin leer el archivo de entorno."""

    return AppConfig(
        _env_file=None,
        openai_api_key=api_key,
        pdf_directory=tmp_path / "pdf",
        reference_path=tmp_path / "referencias.json",
        history_path=tmp_path / "resultados.json",
    )


def make_result(
    *,
    processed_at: datetime,
    status: ProcessingStatus = ProcessingStatus.VALIDATED,
    total_tokens: int | None = 12,
) -> ProcessingResult:
    """Crea un resultado para probar transformaciones de presentación."""

    return ProcessingResult(
        id_procesamiento=uuid4(),
        archivo="albaran.pdf",
        huella_archivo="huella",
        fecha_procesamiento=processed_at,
        numero_intento=1,
        estado=status,
        mensaje="Resultado controlado",
        duracion_segundos=Decimal("1.25"),
        uso_api=(
            ApiUsage(total_tokens=total_tokens)
            if total_tokens is not None
            else None
        ),
    )


def test_list_pdf_files_returns_only_pdf_and_accepts_uppercase(
    tmp_path: Path,
) -> None:
    """Lista solamente PDF y acepta extensiones en mayúsculas."""

    pdf_directory = tmp_path / "pdf"
    pdf_directory.mkdir()
    lower_pdf = pdf_directory / "b.pdf"
    upper_pdf = pdf_directory / "A.PDF"
    lower_pdf.write_bytes(b"pdf")
    upper_pdf.write_bytes(b"pdf")
    (pdf_directory / "notas.txt").write_text("texto", encoding="utf-8")
    (pdf_directory / "carpeta.pdf").mkdir()

    result = app.list_pdf_files(pdf_directory)

    assert result == [upper_pdf, lower_pdf]


def test_list_pdf_files_sorts_case_insensitively(tmp_path: Path) -> None:
    """Ordena los nombres sin distinguir entre mayúsculas y minúsculas."""

    pdf_directory = tmp_path / "pdf"
    pdf_directory.mkdir()
    expected_names = ["alfa.pdf", "Beta.pdf", "zeta.pdf"]
    for name in reversed(expected_names):
        (pdf_directory / name).write_bytes(b"pdf")

    result = app.list_pdf_files(pdf_directory)

    assert [path.name for path in result] == expected_names


def test_list_pdf_files_returns_empty_for_missing_directory(tmp_path: Path) -> None:
    """Devuelve una lista vacía si la carpeta todavía no existe."""

    assert app.list_pdf_files(tmp_path / "ausente") == []


def test_list_pdf_files_hides_path_on_access_error(tmp_path: Path) -> None:
    """Convierte errores de acceso sin revelar la ruta interna."""

    internal_path = tmp_path / "privado" / "documentos"
    with patch.object(Path, "exists", side_effect=PermissionError(str(internal_path))):
        try:
            app.list_pdf_files(internal_path)
        except app.AppError as error:
            assert str(internal_path) not in error.message
            assert "privado" not in error.message
        else:
            raise AssertionError("Se esperaba un error controlado")


def test_create_dependencies_without_key_uses_no_extractor(tmp_path: Path) -> None:
    """Permite construir la aplicación sin configurar OpenAI."""

    config = make_config(tmp_path)
    with patch("src.app.OpenAIExtractor") as extractor_class:
        service, history_repository = app.create_dependencies(config)

    assert service.extractor is None
    assert service.history_repository is history_repository
    extractor_class.assert_not_called()


def test_create_dependencies_with_key_builds_mocked_extractor(
    tmp_path: Path,
) -> None:
    """Construye el extractor configurado sin realizar solicitudes de red."""

    config = make_config(tmp_path, api_key="secreto-de-prueba")
    with patch("src.app.OpenAIExtractor") as extractor_class:
        service, _ = app.create_dependencies(config)

    extractor_class.assert_called_once_with(config)
    assert service.extractor is extractor_class.return_value


def test_sidebar_details_never_include_api_key(tmp_path: Path) -> None:
    """La información pública no contiene el valor de la credencial."""

    secret = "clave-que-no-debe-mostrarse"
    details = app.build_sidebar_details(make_config(tmp_path, api_key=secret))

    assert details["Estado de API"] == "API configurada"
    assert secret not in str(details)


def test_presentation_helpers_format_none_as_unavailable() -> None:
    """Presenta valores ausentes con texto comprensible."""

    data = DeliveryNoteData(
        numero_albaran=None,
        cif_proveedor=None,
        proveedor=None,
        fecha=None,
        importe_total=None,
        moneda=None,
    )

    rows = app.delivery_note_rows(data)

    assert app.format_value(None) == "No disponible"
    assert all(row["Valor"] == "No disponible" for row in rows)


def test_history_summary_uses_status_tokens_and_recent_first() -> None:
    """Resume estado y tokens ordenando primero el intento más reciente."""

    old_date = datetime(2026, 8, 7, tzinfo=timezone.utc)
    old_result = make_result(
        processed_at=old_date,
        status=ProcessingStatus.NOT_FOUND,
        total_tokens=None,
    )
    recent_result = make_result(
        processed_at=old_date + timedelta(hours=1),
        status=ProcessingStatus.HAS_DIFFERENCES,
        total_tokens=27,
    )

    rows = app.history_summary_rows([old_result, recent_result])

    assert rows[0]["Estado"] == ProcessingStatus.HAS_DIFFERENCES.value
    assert rows[0]["Tokens totales"] == 27
    assert rows[1]["Estado"] == ProcessingStatus.NOT_FOUND.value
    assert rows[1]["Tokens totales"] == "No disponible"


def test_delivery_note_presentation_does_not_modify_reference() -> None:
    """Transformar una referencia para mostrarla no modifica el modelo."""

    reference = DeliveryNoteData(
        numero_albaran="ALB-01",
        cif_proveedor="B123",
        proveedor="Proveedor Ágil",
        fecha=date(2026, 8, 7),
        importe_total=Decimal("10.50"),
        moneda="EUR",
        observaciones=["Original"],
    )
    original = reference.model_dump()

    app.delivery_note_rows(reference)

    assert reference.model_dump() == original


def test_importing_app_does_not_execute_main() -> None:
    """Importar el módulo no inicia automáticamente la interfaz."""

    with patch.object(app.st, "set_page_config") as page_config:
        importlib.reload(app)

    page_config.assert_not_called()


def test_invalid_known_pdf_stores_confirmation_request(tmp_path: Path) -> None:
    """Guarda la solicitud de confirmación para un PDF inválido conocido."""

    config = make_config(tmp_path, api_key="clave-ficticia")
    selected_path = tmp_path / "invalido.pdf"
    service = MagicMock()
    service.prepare_document.side_effect = PdfValidationError("PDF inválido")
    service.process.side_effect = ReprocessingConfirmationError()
    session_state: dict[str, object] = {}
    rerun = MagicMock()
    spinner = MagicMock()

    with (
        patch.object(app.st, "session_state", session_state),
        patch.object(app, "list_pdf_files", return_value=[selected_path]),
        patch.object(app.st, "selectbox", return_value=selected_path),
        patch.object(app.st, "button", return_value=True),
        patch.object(app.st, "spinner", spinner),
        patch.object(app.st, "rerun", rerun),
        patch.object(app.st, "title"),
        patch.object(app.st, "error"),
        patch.object(app.st, "warning"),
        patch.object(app.st, "info"),
        patch.object(app.st, "caption"),
        patch.object(app.st, "divider"),
        patch.object(app.st, "subheader"),
    ):
        app.render_processing_page(config, service)

    service.process.assert_called_once_with(
        selected_path,
        reprocessing_confirmed=False,
    )
    assert (
        session_state[app.INVALID_CONFIRMATION_KEY]
        == selected_path.name
    )
    rerun.assert_called_once_with()
    assert app.LAST_RESULT_KEY not in session_state


def test_confirmed_invalid_pdf_processes_and_clears_confirmation(
    tmp_path: Path,
) -> None:
    """Procesa un PDF inválido confirmado y limpia la marca temporal."""

    config = make_config(tmp_path, api_key="clave-ficticia")
    selected_path = tmp_path / "invalido.pdf"
    result = make_result(
        processed_at=datetime(2026, 8, 8, tzinfo=timezone.utc),
        status=ProcessingStatus.INVALID_DOCUMENT,
        total_tokens=None,
    )
    service = MagicMock()
    service.prepare_document.side_effect = PdfValidationError("PDF inválido")
    service.process.return_value = result
    session_state: dict[str, object] = {
        app.INVALID_CONFIRMATION_KEY: selected_path.name
    }
    rerun = MagicMock()
    spinner = MagicMock()

    with (
        patch.object(app.st, "session_state", session_state),
        patch.object(app, "list_pdf_files", return_value=[selected_path]),
        patch.object(app, "render_result") as render_result,
        patch.object(app.st, "selectbox", return_value=selected_path),
        patch.object(app.st, "checkbox", return_value=True),
        patch.object(app.st, "button", return_value=True),
        patch.object(app.st, "spinner", spinner),
        patch.object(app.st, "rerun", rerun),
        patch.object(app.st, "title"),
        patch.object(app.st, "error"),
        patch.object(app.st, "warning"),
        patch.object(app.st, "info"),
        patch.object(app.st, "caption"),
        patch.object(app.st, "divider"),
        patch.object(app.st, "subheader"),
    ):
        app.render_processing_page(config, service)

    service.process.assert_called_once_with(
        selected_path,
        reprocessing_confirmed=True,
    )
    assert app.INVALID_CONFIRMATION_KEY not in session_state
    assert session_state[app.LAST_RESULT_KEY] is result
    render_result.assert_called_once_with(result)
    rerun.assert_not_called()
