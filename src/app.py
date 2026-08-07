"""Interfaz Streamlit del validador inteligente de albaranes."""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

import streamlit as st

from src.comparator import DeliveryNoteComparator
from src.config import AppConfig
from src.exceptions import (
    AppError,
    ConfigurationError,
    HistoryError,
    PdfValidationError,
    ReprocessingConfirmationError,
)
from src.history_repository import HistoryRepository
from src.models import DeliveryNoteData, ProcessingResult, ProcessingStatus
from src.normalizer import Normalizer
from src.openai_client import OpenAIExtractor
from src.pdf_validator import PdfValidator
from src.processing_service import ProcessingService
from src.reference_repository import ReferenceRepository


LAST_RESULT_KEY = "last_processing_result"
INVALID_CONFIRMATION_KEY = "invalid_reprocessing_confirmation_file"


def create_dependencies(
    config: AppConfig,
) -> tuple[ProcessingService, HistoryRepository]:
    """Construye y conecta las dependencias de la aplicación."""

    pdf_validator = PdfValidator(config.max_pdf_pages)
    normalizer = Normalizer()
    comparator = DeliveryNoteComparator()
    reference_repository = ReferenceRepository(config.reference_path, normalizer)
    history_repository = HistoryRepository(config.history_path)
    extractor = OpenAIExtractor(config) if config.openai_api_key else None
    service = ProcessingService(
        config=config,
        pdf_validator=pdf_validator,
        extractor=extractor,
        normalizer=normalizer,
        comparator=comparator,
        reference_repository=reference_repository,
        history_repository=history_repository,
    )
    return service, history_repository


def list_pdf_files(pdf_directory: Path) -> list[Path]:
    """Lista los PDF disponibles sin revelar detalles del sistema de archivos."""

    try:
        if not pdf_directory.exists() or not pdf_directory.is_dir():
            return []
        pdf_files = [
            path
            for path in pdf_directory.iterdir()
            if path.is_file() and path.suffix.lower() == ".pdf"
        ]
    except OSError:
        raise AppError(
            "No se pudo acceder a la carpeta de documentos PDF."
        ) from None
    return sorted(pdf_files, key=lambda path: path.name.casefold())


def format_value(value: Any) -> str:
    """Convierte un valor de dominio en texto comprensible para la interfaz."""

    if value is None:
        return "No disponible"
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def build_sidebar_details(config: AppConfig) -> dict[str, str]:
    """Construye información pública de configuración para la barra lateral."""

    return {
        "Modelo": config.openai_model,
        "Máximo de páginas": str(config.max_pdf_pages),
        "Estado de API": (
            "API configurada" if config.openai_api_key else "API no configurada"
        ),
    }


def delivery_note_rows(data: DeliveryNoteData) -> list[dict[str, str]]:
    """Transforma un albarán en filas presentables sin modificarlo."""

    fields = (
        ("Número de albarán", data.numero_albaran),
        ("CIF del proveedor", data.cif_proveedor),
        ("Proveedor", data.proveedor),
        ("Fecha", data.fecha),
        ("Importe total", data.importe_total),
        ("Moneda", data.moneda),
        ("Observaciones", ", ".join(data.observaciones) or None),
    )
    return [
        {"Campo": label, "Valor": format_value(value)}
        for label, value in fields
    ]


def history_summary_rows(
    results: list[ProcessingResult],
) -> list[dict[str, str | int]]:
    """Construye el resumen histórico del más reciente al más antiguo."""

    ordered_results = sorted(
        results,
        key=lambda result: result.fecha_procesamiento,
        reverse=True,
    )
    return [
        {
            "Fecha": format_value(result.fecha_procesamiento),
            "Archivo": result.archivo,
            "Intento": result.numero_intento,
            "Estado": result.estado.value,
            "Mensaje": result.mensaje,
            "Duración (s)": format_value(result.duracion_segundos),
            "Tokens totales": (
                result.uso_api.total_tokens
                if result.uso_api is not None
                else "No disponible"
            ),
        }
        for result in ordered_results
    ]


def render_result(result: ProcessingResult) -> None:
    """Muestra el detalle seguro de un resultado de procesamiento."""

    status_renderers = {
        ProcessingStatus.VALIDATED: st.success,
        ProcessingStatus.HAS_DIFFERENCES: st.warning,
        ProcessingStatus.INCOMPLETE_EXTRACTION: st.warning,
        ProcessingStatus.NOT_FOUND: st.info,
        ProcessingStatus.INVALID_DOCUMENT: st.error,
        ProcessingStatus.TECHNICAL_ERROR: st.error,
        ProcessingStatus.REFERENCE_DATA_ERROR: st.error,
    }
    renderer = status_renderers.get(result.estado, st.info)
    renderer(f"{result.estado.value}: {result.mensaje}")

    first_column, second_column, third_column = st.columns(3)
    first_column.metric("Archivo", result.archivo)
    second_column.metric("Intento", result.numero_intento)
    third_column.metric("Duración", f"{format_value(result.duracion_segundos)} s")
    st.caption(f"Fecha: {format_value(result.fecha_procesamiento)}")

    if result.datos_extraidos is not None:
        st.subheader("Datos extraídos")
        st.dataframe(
            delivery_note_rows(result.datos_extraidos),
            use_container_width=True,
            hide_index=True,
        )

    if result.datos_referencia is not None:
        st.subheader("Datos de referencia")
        st.dataframe(
            delivery_note_rows(result.datos_referencia),
            use_container_width=True,
            hide_index=True,
        )

    if result.campos_no_leidos:
        st.warning(
            "Campos no leídos: " + ", ".join(result.campos_no_leidos)
        )

    if result.diferencias:
        st.subheader("Diferencias")
        difference_rows = [
            {
                "Campo": difference.campo,
                "Valor del PDF": format_value(difference.valor_pdf),
                "Valor de referencia": format_value(
                    difference.valor_referencia
                ),
            }
            for difference in result.diferencias
        ]
        st.dataframe(
            difference_rows,
            use_container_width=True,
            hide_index=True,
        )

    if result.uso_api is not None:
        st.subheader("Uso de API")
        input_column, output_column, total_column = st.columns(3)
        input_column.metric("Tokens de entrada", result.uso_api.input_tokens)
        output_column.metric("Tokens de salida", result.uso_api.output_tokens)
        total_column.metric("Tokens totales", result.uso_api.total_tokens)


def render_processing_page(
    config: AppConfig,
    service: ProcessingService,
) -> None:
    """Muestra la selección, preparación y procesamiento de un PDF."""

    st.title("Procesar albarán")
    try:
        pdf_files = list_pdf_files(config.pdf_directory)
    except AppError as error:
        st.error(error.message)
        return

    if not pdf_files:
        st.warning("Añade documentos PDF a la carpeta data/pdf para comenzar.")
        return

    selected_path = st.selectbox(
        "Selecciona un PDF",
        options=pdf_files,
        format_func=lambda path: path.name,
    )
    if selected_path is None:
        return

    invalid_confirmation_required = (
        st.session_state.get(INVALID_CONFIRMATION_KEY) == selected_path.name
    )
    preparation = None
    validation_error: PdfValidationError | None = None
    try:
        preparation = service.prepare_document(selected_path)
        st.session_state.pop(INVALID_CONFIRMATION_KEY, None)
        invalid_confirmation_required = False
    except PdfValidationError as error:
        validation_error = error
        st.error(error.message)
    except (HistoryError, AppError) as error:
        st.error(error.message)
        return
    except Exception:
        st.error("No se pudo preparar el documento seleccionado.")
        return

    confirmation = False
    if preparation is not None:
        pdf_info = preparation.pdf_info
        document_columns = st.columns(4)
        document_columns[0].metric("Archivo", pdf_info.file_name)
        document_columns[1].metric("Tamaño", f"{pdf_info.size_bytes} bytes")
        document_columns[2].metric("Páginas", pdf_info.page_count)
        document_columns[3].metric("Siguiente intento", preparation.next_attempt_number)
        st.caption(f"Huella: {pdf_info.file_hash[:12]}…")

        if preparation.previously_processed:
            latest_status = (
                preparation.latest_result.estado.value
                if preparation.latest_result is not None
                else "No disponible"
            )
            st.warning(
                "Este documento ya fue procesado. "
                f"Último estado: {latest_status}."
            )
            confirmation = st.checkbox(
                "Confirmo que deseo volver a procesar este documento."
            )
    elif validation_error is not None and invalid_confirmation_required:
        st.warning("Este documento inválido ya fue registrado anteriormente.")
        confirmation = st.checkbox(
            "Confirmo que deseo volver a registrar este documento inválido."
        )

    if not config.openai_api_key:
        st.info(
            "Configura OPENAI_API_KEY en el archivo .env para procesar documentos."
        )

    needs_confirmation = bool(
        (
            preparation is not None
            and preparation.requires_confirmation
            and not confirmation
        )
        or (invalid_confirmation_required and not confirmation)
    )
    button_disabled = not config.openai_api_key or needs_confirmation
    if st.button("Procesar albarán", disabled=button_disabled):
        try:
            with st.spinner("Procesando el documento..."):
                result = service.process(
                    selected_path,
                    reprocessing_confirmed=confirmation,
                )
            st.session_state.pop(INVALID_CONFIRMATION_KEY, None)
            st.session_state[LAST_RESULT_KEY] = result
        except ReprocessingConfirmationError as error:
            st.session_state[INVALID_CONFIRMATION_KEY] = selected_path.name
            st.warning(error.message)
            st.rerun()
        except (
            ConfigurationError,
            PdfValidationError,
            HistoryError,
            AppError,
        ) as error:
            st.error(error.message)
        except Exception:
            st.error("Se produjo un error inesperado durante el procesamiento.")

    if validation_error is not None and not config.openai_api_key:
        st.caption("El documento inválido no se registrará sin configurar la API.")

    last_result = st.session_state.get(LAST_RESULT_KEY)
    if isinstance(last_result, ProcessingResult):
        st.divider()
        st.subheader("Último resultado procesado")
        render_result(last_result)


def render_history_page(history_repository: HistoryRepository) -> None:
    """Muestra y permite reiniciar el historial local."""

    st.title("Historial")
    try:
        results = history_repository.load()
    except HistoryError as error:
        st.error(error.message)
        return
    except Exception:
        st.error("No se pudo consultar el historial local.")
        return

    if not results:
        st.info("Todavía no hay intentos registrados.")
    else:
        ordered_results = sorted(
            results,
            key=lambda result: result.fecha_procesamiento,
            reverse=True,
        )
        st.dataframe(
            history_summary_rows(ordered_results),
            use_container_width=True,
            hide_index=True,
        )
        selected_index = st.selectbox(
            "Selecciona un intento para consultar su detalle",
            options=range(len(ordered_results)),
            format_func=lambda index: (
                f"{ordered_results[index].archivo} · "
                f"intento {ordered_results[index].numero_intento} · "
                f"{ordered_results[index].estado.value}"
            ),
        )
        render_result(ordered_results[selected_index])

    st.divider()
    st.subheader("Reiniciar historial para la demostración")
    clear_confirmed = st.checkbox(
        "Confirmo que deseo borrar todo el historial local."
    )
    if st.button("Borrar historial", disabled=not clear_confirmed):
        try:
            history_repository.clear()
            st.session_state.pop(LAST_RESULT_KEY, None)
            st.session_state.pop(INVALID_CONFIRMATION_KEY, None)
            st.success("El historial local se ha reiniciado correctamente.")
            st.rerun()
        except HistoryError as error:
            st.error(error.message)
        except Exception:
            st.error("No se pudo reiniciar el historial local.")


def render_about_page(config: AppConfig) -> None:
    """Muestra el propósito y las restricciones principales del proyecto."""

    st.title("Acerca del proyecto")
    st.write(
        "Esta aplicación extrae número de albarán, CIF, proveedor, fecha, "
        "importe total y moneda de documentos PDF ficticios."
    )
    st.write(
        "La comparación se realiza localmente con un archivo JSON de referencia; "
        "la inteligencia artificial no decide el resultado final."
    )
    st.write(
        f"Cada PDF puede contener como máximo {config.max_pdf_pages} páginas y "
        "debe incluir texto extraíble."
    )
    st.write(
        "El historial se guarda localmente. La API key se configura en .env y "
        "no debe subirse a GitHub."
    )


def main() -> None:
    """Configura y ejecuta la interfaz principal de Streamlit."""

    st.set_page_config(
        page_title="Validador de albaranes IA",
        page_icon="📄",
        layout="wide",
    )
    try:
        config = AppConfig()
        service, history_repository = create_dependencies(config)
    except AppError as error:
        st.error(error.message)
        return
    except Exception:
        st.error("No se pudo iniciar la aplicación con la configuración actual.")
        return

    page = st.sidebar.selectbox(
        "Navegación",
        ("Procesar PDF", "Historial", "Acerca del proyecto"),
    )
    st.sidebar.divider()
    for label, value in build_sidebar_details(config).items():
        st.sidebar.write(f"**{label}:** {value}")

    if page == "Procesar PDF":
        render_processing_page(config, service)
    elif page == "Historial":
        render_history_page(history_repository)
    else:
        render_about_page(config)


if __name__ == "__main__":
    main()
