"""Pruebas unitarias del cliente de extracción de OpenAI."""

import base64
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    PermissionDeniedError,
    RateLimitError,
)
from pydantic import ValidationError

from src.config import AppConfig
from src.exceptions import ConfigurationError, OpenAIExtractionError
from src.models import DeliveryNoteData, ErrorStage, ErrorType
from src.openai_client import OpenAIExtractor


SECRET_KEY = "clave-super-secreta"


def make_config(api_key: str | None = SECRET_KEY) -> AppConfig:
    """Crea una configuración aislada del archivo de entorno."""

    return AppConfig(
        _env_file=None,
        openai_api_key=api_key,
        openai_model="modelo-prueba",
        openai_reasoning_effort="low",
        openai_timeout_seconds=12.5,
        openai_max_retries=1,
        pdf_detail="low",
    )


def make_data() -> DeliveryNoteData:
    """Crea datos válidos con formatos deliberadamente no normalizados."""

    return DeliveryNoteData(
        numero_albaran=" ab / 01 ",
        cif_proveedor=" b-12.345 ",
        proveedor="Proveedor Ágil",
        fecha=date(2026, 8, 7),
        importe_total=Decimal("10.50"),
        moneda="eur",
    )


def make_client(
    data: DeliveryNoteData | None = None,
    usage: object | None = None,
) -> MagicMock:
    """Crea un cliente simulado con una respuesta estructurada."""

    client = MagicMock()
    client.responses.parse.return_value = SimpleNamespace(
        output_parsed=data if data is not None else make_data(),
        usage=usage,
    )
    return client


def make_status_error(error_class: type[APIError], status_code: int) -> APIError:
    """Crea un error HTTP oficial sin realizar ninguna conexión."""

    request = httpx.Request("POST", "https://example.invalid/v1/responses")
    response = httpx.Response(status_code, request=request)
    return error_class("detalle técnico sensible", response=response, body=None)


def test_requires_api_key_without_injected_client() -> None:
    """Rechaza una configuración sin credenciales."""

    with pytest.raises(ConfigurationError) as captured:
        OpenAIExtractor(make_config(api_key=None))

    assert captured.value.error_type is ErrorType.AUTHENTICATION
    assert SECRET_KEY not in captured.value.message


def test_creates_official_client_with_configured_options() -> None:
    """Configura el cliente oficial con los límites aprobados."""

    config = make_config()
    with patch("src.openai_client.OpenAI") as openai_class:
        OpenAIExtractor(config)

    openai_class.assert_called_once_with(
        api_key=SECRET_KEY,
        timeout=12.5,
        max_retries=1,
    )


def test_extract_builds_expected_request_and_returns_data(tmp_path: Path) -> None:
    """Codifica el PDF y construye una única solicitud estructurada."""

    pdf_bytes = b"%PDF-1.7\ncontenido binario"
    path = tmp_path / "Albaran.PDF"
    path.write_bytes(pdf_bytes)
    data = make_data()
    usage = SimpleNamespace(input_tokens=11, output_tokens=7, total_tokens=18)
    client = make_client(data, usage)

    result = OpenAIExtractor(make_config(), client).extract(path)

    client.responses.parse.assert_called_once()
    request = client.responses.parse.call_args.kwargs
    assert request["model"] == "modelo-prueba"
    assert request["reasoning"] == {"effort": "low"}
    assert request["text_format"] is DeliveryNoteData
    file_input = request["input"][1]["content"][0]
    assert file_input == {
        "type": "input_file",
        "filename": "Albaran.PDF",
        "file_data": (
            "data:application/pdf;base64,"
            + base64.b64encode(pdf_bytes).decode("ascii")
        ),
        "detail": "low",
    }
    prompt = " ".join(
        item["content"]
        for item in request["input"]
        if isinstance(item["content"], str)
    )
    for field in (
        "numero_albaran",
        "cif_proveedor",
        "proveedor",
        "fecha",
        "importe_total",
        "moneda",
        "campos_no_leidos",
        "observaciones",
    ):
        assert field in prompt
    assert "No inventes ni deduzcas" in prompt
    assert result.data == data
    assert result.data.numero_albaran == " ab / 01 "
    assert result.data.cif_proveedor == " b-12.345 "
    assert result.data.moneda == "eur"
    assert result.api_usage is not None
    assert result.api_usage.input_tokens == 11
    assert result.api_usage.output_tokens == 7
    assert result.api_usage.total_tokens == 18


def test_returns_no_usage_when_response_has_none(tmp_path: Path) -> None:
    """Admite respuestas sin contadores de uso."""

    path = tmp_path / "documento.pdf"
    path.write_bytes(b"pdf")

    result = OpenAIExtractor(make_config(), make_client()).extract(path)

    assert result.api_usage is None


def test_returns_no_usage_when_attribute_is_absent(tmp_path: Path) -> None:
    """Admite respuestas que no exponen el atributo de uso."""

    path = tmp_path / "documento.pdf"
    path.write_bytes(b"pdf")
    client = MagicMock()
    client.responses.parse.return_value = SimpleNamespace(output_parsed=make_data())

    result = OpenAIExtractor(make_config(), client).extract(path)

    assert result.api_usage is None


def test_none_parsed_output_is_invalid_response(tmp_path: Path) -> None:
    """Clasifica una salida estructurada ausente como respuesta inválida."""

    path = tmp_path / "documento.pdf"
    path.write_bytes(b"pdf")
    client = MagicMock()
    client.responses.parse.return_value = SimpleNamespace(
        output_parsed=None,
        usage=None,
    )

    with pytest.raises(OpenAIExtractionError) as captured:
        OpenAIExtractor(make_config(), client).extract(path)

    assert captured.value.error_type is ErrorType.INVALID_RESPONSE
    assert captured.value.error_stage is ErrorStage.RESPONSE_VALIDATION


def test_pydantic_validation_error_is_invalid_response(tmp_path: Path) -> None:
    """Clasifica un fallo de validación estructurada en su etapa correcta."""

    path = tmp_path / "documento.pdf"
    path.write_bytes(b"pdf")
    client = MagicMock()
    with pytest.raises(ValidationError) as validation_error:
        DeliveryNoteData.model_validate({})
    client.responses.parse.side_effect = validation_error.value

    with pytest.raises(OpenAIExtractionError) as captured:
        OpenAIExtractor(make_config(), client).extract(path)

    assert captured.value.error_type is ErrorType.INVALID_RESPONSE
    assert captured.value.error_stage is ErrorStage.RESPONSE_VALIDATION
    assert "numero_albaran" not in captured.value.message


def test_file_read_error_is_controlled(tmp_path: Path) -> None:
    """Convierte un fallo de lectura sin revelar la ruta interna."""

    path = tmp_path / "secreto" / "ausente.pdf"
    client = make_client()

    with pytest.raises(OpenAIExtractionError) as captured:
        OpenAIExtractor(make_config(), client).extract(path)

    assert captured.value.error_type is ErrorType.FILE
    assert captured.value.error_stage is ErrorStage.OPENAI_EXTRACTION
    assert str(path) not in captured.value.message
    assert "ausente.pdf" not in captured.value.message
    client.responses.parse.assert_not_called()


@pytest.mark.parametrize(
    ("sdk_error", "expected_type"),
    [
        (
            make_status_error(AuthenticationError, 401),
            ErrorType.AUTHENTICATION,
        ),
        (
            make_status_error(PermissionDeniedError, 403),
            ErrorType.PERMISSION_DENIED,
        ),
        (
            APIConnectionError(
                message="detalle técnico sensible",
                request=httpx.Request("POST", "https://example.invalid"),
            ),
            ErrorType.CONNECTION,
        ),
        (
            make_status_error(RateLimitError, 429),
            ErrorType.RATE_LIMIT_OR_QUOTA,
        ),
        (
            APITimeoutError(httpx.Request("POST", "https://example.invalid")),
            ErrorType.TIMEOUT,
        ),
        (
            make_status_error(BadRequestError, 400),
            ErrorType.INVALID_REQUEST,
        ),
        (
            make_status_error(InternalServerError, 500),
            ErrorType.SERVICE_UNAVAILABLE,
        ),
        (
            APIError(
                "detalle técnico sensible",
                httpx.Request("POST", "https://example.invalid"),
                body=None,
            ),
            ErrorType.INTERNAL,
        ),
    ],
    ids=[
        "authentication",
        "permission",
        "connection",
        "rate-limit",
        "timeout",
        "bad-request",
        "internal-server",
        "generic-api",
    ],
)
def test_maps_sdk_errors_without_exposing_details(
    tmp_path: Path,
    sdk_error: APIError,
    expected_type: ErrorType,
) -> None:
    """Mapea cada error oficial a un mensaje controlado."""

    path = tmp_path / "documento-confidencial.pdf"
    path.write_bytes(b"pdf")
    client = MagicMock()
    client.responses.parse.side_effect = sdk_error

    with pytest.raises(OpenAIExtractionError) as captured:
        OpenAIExtractor(make_config(), client).extract(path)

    assert captured.value.error_type is expected_type
    assert captured.value.error_stage is ErrorStage.OPENAI_EXTRACTION
    assert "detalle técnico sensible" not in captured.value.message
    assert SECRET_KEY not in captured.value.message
    assert str(path) not in captured.value.message
    client.responses.parse.assert_called_once()
