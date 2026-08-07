"""Excepciones controladas de la aplicación."""

from src.models import ErrorStage, ErrorType


class AppError(Exception):
    """Error base con un mensaje seguro para mostrar en la interfaz."""

    def __init__(
        self,
        message: str,
        error_type: ErrorType = ErrorType.INTERNAL,
        error_stage: ErrorStage | None = None,
    ) -> None:
        """Inicializa un error controlado con su tipo y etapa."""

        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.error_stage = error_stage


class ConfigurationError(AppError):
    """Error de configuración previo al inicio de un intento."""

    def __init__(
        self,
        message: str,
        error_type: ErrorType = ErrorType.INTERNAL,
    ) -> None:
        """Inicializa un error de configuración sin etapa asociada."""

        super().__init__(message, error_type, None)


class PdfValidationError(AppError):
    """Error controlado durante la validación de un PDF."""

    def __init__(
        self,
        message: str,
        error_type: ErrorType = ErrorType.FILE,
        error_stage: ErrorStage = ErrorStage.PDF_VALIDATION,
    ) -> None:
        """Inicializa un error de archivo en la etapa de validación."""

        super().__init__(message, error_type, error_stage)


class OpenAIExtractionError(AppError):
    """Error controlado de extracción o validación de respuesta."""

    def __init__(
        self,
        message: str,
        error_type: ErrorType,
        error_stage: ErrorStage = ErrorStage.OPENAI_EXTRACTION,
    ) -> None:
        """Inicializa un error de OpenAI con una etapa configurable."""

        super().__init__(message, error_type, error_stage)


class ReferenceDataError(AppError):
    """Error controlado al cargar los datos de referencia."""

    def __init__(
        self,
        message: str,
        error_type: ErrorType = ErrorType.REFERENCE_DATA,
        error_stage: ErrorStage = ErrorStage.REFERENCE_LOADING,
    ) -> None:
        """Inicializa un error de datos en la etapa de carga."""

        super().__init__(message, error_type, error_stage)


class HistoryError(AppError):
    """Error controlado durante la escritura del historial."""

    def __init__(
        self,
        message: str,
        error_type: ErrorType = ErrorType.INTERNAL,
        error_stage: ErrorStage = ErrorStage.HISTORY_WRITE,
    ) -> None:
        """Inicializa un error interno en la etapa de guardado."""

        super().__init__(message, error_type, error_stage)


class ReprocessingConfirmationError(AppError):
    """Indica que un reprocesamiento necesita confirmación expresa."""

    def __init__(
        self,
        message: str = (
            "El documento ya fue procesado. "
            "Confirma expresamente si deseas volver a procesarlo."
        ),
    ) -> None:
        """Inicializa el control de flujo previo al inicio del intento."""

        super().__init__(message, ErrorType.INTERNAL, None)
