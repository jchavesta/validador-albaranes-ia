"""Cliente de extracción estructurada de albaranes mediante OpenAI."""

import base64
from pathlib import Path
from typing import Any, NoReturn

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)
from pydantic import ValidationError

from src.config import AppConfig
from src.exceptions import ConfigurationError, OpenAIExtractionError
from src.models import (
    ApiUsage,
    DeliveryNoteData,
    ErrorStage,
    ErrorType,
    OpenAIExtraction,
)


EXTRACTION_INSTRUCTIONS = """\
Extrae del albarán los campos numero_albaran, cif_proveedor, proveedor, fecha,
importe_total y moneda. No inventes ni deduzcas valores ausentes. Usa None cuando
un valor no pueda leerse con seguridad. Expresa fecha en formato ISO YYYY-MM-DD,
importe_total como valor numérico sin símbolo de moneda y moneda como código ISO,
por ejemplo EUR. Incluye en campos_no_leidos los nombres de los campos ausentes o
ilegibles. Usa observaciones solo para incidencias relevantes de lectura. No
compares el documento con ningún JSON ni decidas el estado final del procesamiento.
"""


class OpenAIExtractor:
    """Extrae datos estructurados de un PDF mediante la API Responses."""

    def __init__(
        self,
        config: AppConfig,
        client: OpenAI | None = None,
    ) -> None:
        """Inicializa el extractor con configuración y un cliente opcional."""

        self.config = config
        if client is not None:
            self.client = client
            return

        if not config.openai_api_key:
            raise ConfigurationError(
                "Falta configurar la clave de acceso al servicio de extracción.",
                ErrorType.AUTHENTICATION,
            )

        self.client = OpenAI(
            api_key=config.openai_api_key,
            timeout=config.openai_timeout_seconds,
            max_retries=config.openai_max_retries,
        )

    def extract(self, path: Path) -> OpenAIExtraction:
        """Lee un PDF y devuelve los datos estructurados extraídos."""

        try:
            encoded_pdf = base64.b64encode(path.read_bytes()).decode("ascii")
        except OSError:
            raise OpenAIExtractionError(
                "No se ha podido leer el documento para su extracción.",
                ErrorType.FILE,
            ) from None

        try:
            response = self.client.responses.parse(
                model=self.config.openai_model,
                reasoning={"effort": self.config.openai_reasoning_effort},
                input=[
                    {
                        "role": "system",
                        "content": EXTRACTION_INSTRUCTIONS,
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_file",
                                "filename": path.name,
                                "file_data": (
                                    "data:application/pdf;base64," + encoded_pdf
                                ),
                                "detail": self.config.pdf_detail,
                            },
                            {
                                "type": "input_text",
                                "text": "Extrae los datos del albarán adjunto.",
                            },
                        ],
                    },
                ],
                text_format=DeliveryNoteData,
            )
        except APITimeoutError:
            self._raise_api_error(ErrorType.TIMEOUT)
        except AuthenticationError:
            self._raise_api_error(ErrorType.AUTHENTICATION)
        except PermissionDeniedError:
            self._raise_api_error(ErrorType.PERMISSION_DENIED)
        except RateLimitError:
            self._raise_api_error(ErrorType.RATE_LIMIT_OR_QUOTA)
        except BadRequestError:
            self._raise_api_error(ErrorType.INVALID_REQUEST)
        except InternalServerError:
            self._raise_api_error(ErrorType.SERVICE_UNAVAILABLE)
        except APIConnectionError:
            self._raise_api_error(ErrorType.CONNECTION)
        except ValidationError:
            self._raise_invalid_response()
        except APIError:
            self._raise_api_error(ErrorType.INTERNAL)

        try:
            data = response.output_parsed
            if data is None:
                raise OpenAIExtractionError(
                    "El servicio no ha devuelto datos estructurados válidos.",
                    ErrorType.INVALID_RESPONSE,
                    ErrorStage.RESPONSE_VALIDATION,
                )

            usage = self._build_usage(getattr(response, "usage", None))
            return OpenAIExtraction(data=data, api_usage=usage)
        except OpenAIExtractionError:
            raise
        except (AttributeError, TypeError, ValidationError):
            self._raise_invalid_response()

    @staticmethod
    def _build_usage(usage: Any) -> ApiUsage | None:
        """Convierte los contadores de la API al modelo de dominio."""

        if usage is None:
            return None
        return ApiUsage(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
        )

    @staticmethod
    def _raise_api_error(error_type: ErrorType) -> NoReturn:
        """Convierte un error del SDK en un error seguro de extracción."""

        raise OpenAIExtractionError(
            "No se ha podido completar la extracción mediante el servicio.",
            error_type,
        ) from None

    @staticmethod
    def _raise_invalid_response() -> NoReturn:
        """Convierte una respuesta inválida en un error seguro de validación."""

        raise OpenAIExtractionError(
            "El servicio ha devuelto una respuesta que no se puede validar.",
            ErrorType.INVALID_RESPONSE,
            ErrorStage.RESPONSE_VALIDATION,
        ) from None
