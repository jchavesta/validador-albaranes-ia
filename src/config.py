"""Configuración central de la aplicación y de sus rutas locales."""

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class AppConfig(BaseSettings):
    """Carga y valida la configuración desde variables de entorno y ``.env``."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    openai_api_key: str | None = None
    openai_model: str = "gpt-5.6-terra"
    openai_reasoning_effort: str = "low"
    openai_timeout_seconds: float = Field(default=90.0, gt=0)
    openai_max_retries: int = Field(default=0, ge=0)
    pdf_detail: str = "low"
    max_pdf_pages: int = Field(default=3, ge=1, validation_alias="MAX_PDF_PAGES")
    pdf_directory: Path = PROJECT_ROOT / "data" / "pdf"
    reference_path: Path = PROJECT_ROOT / "data" / "albaranes.json"
    history_path: Path = PROJECT_ROOT / "runtime" / "resultados.json"

    @field_validator("openai_api_key", mode="before")
    @classmethod
    def empty_api_key_as_none(cls, value: object) -> object:
        """Interpreta una clave vacía como una configuración sin credenciales."""

        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("pdf_directory", "reference_path", "history_path", mode="before")
    @classmethod
    def resolve_project_path(cls, value: object) -> object:
        """Resuelve las rutas relativas con respecto a la raíz del proyecto."""

        if isinstance(value, (str, Path)):
            path = Path(value).expanduser()
            return path if path.is_absolute() else PROJECT_ROOT / path
        return value
