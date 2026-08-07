# Especificación de requisitos — Comprobador inteligente de albaranes

| Propiedad | Valor |
|---|---|
| Documento | Especificación de requisitos de software |
| Proyecto | Comprobador inteligente de albaranes |
| Versión | 1.2 |
| Estado | Aprobado para diseño del MVP |
| Fecha | 2026-08-06 |

### Historial de versiones

| Versión | Fecha | Cambios |
|---|---|---|
| 1.0 | 2026-08-06 | Especificación inicial del MVP. |
| 1.1 | 2026-08-06 | Persistencia local del historial, redondeo de importes, unicidad de referencias, errores controlados y definición de intentos registrables. |
| 1.2 | 2026-08-06 | Límite de una llamada por intento, normalización exacta del número de albarán y configuración mediante variables de entorno. |

## 1. Propósito

Este documento define los requisitos del producto mínimo viable (MVP) de una aplicación que extrae datos de albaranes en PDF mediante la API de OpenAI y los compara con registros almacenados en un fichero JSON.

La aplicación estará orientada a una demostración académica con tres PDF ficticios. Deberá ser sencilla de ejecutar, probar y evaluar desde un repositorio de GitHub.

## 2. Objetivos

- Automatizar la lectura de los campos principales de un albarán.
- Comprobar si el documento corresponde a un albarán registrado.
- Detectar diferencias entre el PDF y los datos de referencia.
- Evitar que una extracción de IA modifique los datos de referencia.
- Mantener un historial trazable de todos los intentos.
- Permitir que una persona externa instale y ejecute el proyecto siguiendo el README.

## 3. Alcance

### 3.1 Incluido en el MVP

- Aplicación local desarrollada en Python con interfaz Streamlit.
- Detección de PDF incluidos en una carpeta del proyecto.
- Selección y procesamiento individual de documentos.
- Validación previa del formato y número de páginas.
- Extracción estructurada mediante la API de OpenAI.
- Normalización y validación de los campos extraídos.
- Comparación con `albaranes.json`.
- Clasificación del resultado mediante estados definidos.
- Historial persistente generado localmente en `runtime/resultados.json`.
- Reprocesamiento con aviso y conservación de intentos anteriores.
- Consulta del historial y detalle de cada intento.
- Entrega mediante GitHub, documentación y vídeo demostrativo.

### 3.2 Excluido del MVP

- Procesamiento automático o masivo de todos los PDF.
- Procesamiento garantizado de PDF escaneados.
- Base de datos, ERP o almacenamiento remoto.
- Inicio de sesión y gestión de usuarios.
- Uso simultáneo por múltiples usuarios.
- Edición de `albaranes.json` desde la interfaz.
- Eliminación o edición del historial desde la interfaz.
- Incorporación automática de albaranes no encontrados.
- Despliegue público de la aplicación.

## 4. Actores

| Actor | Descripción |
|---|---|
| Usuario | Selecciona albaranes, inicia el procesamiento y consulta resultados e historial. |
| API de OpenAI | Extrae los datos estructurados del PDF. |
| Profesor/evaluador | Clona el repositorio, configura opcionalmente su clave API y prueba la aplicación. |

## 5. Supuestos y dependencias

- Los PDF del MVP contienen texto extraíble y no información real o confidencial.
- El proyecto incluirá tres PDF de prueba.
- Para efectuar una extracción real se requiere conexión a Internet y una clave válida de OpenAI.
- Si el evaluador no dispone de clave, podrá revisar el vídeo de demostración.
- La comparación será determinista y se realizará mediante código local, no mediante el modelo de IA.

## 6. Datos del albarán

| Campo | Tipo normalizado | Obligatorio | Uso |
|---|---|---:|---|
| `numero_albaran` | Cadena | Sí | Identificación |
| `cif_proveedor` | Cadena | Sí | Identificación |
| `proveedor` | Cadena | Sí | Comparación |
| `fecha` | Fecha `AAAA-MM-DD` | Sí | Comparación |
| `importe_total` | Decimal | Sí | Comparación |
| `moneda` | Código de moneda | Sí | Comparación |

La clave lógica de búsqueda será la combinación de `cif_proveedor` y `numero_albaran`.

## 7. Requisitos funcionales

### 7.1 Documentos e interfaz

| ID | Requisito | Prioridad |
|---|---|---|
| RF-01 | El sistema deberá detectar los archivos PDF disponibles en la carpeta configurada del proyecto. | Alta |
| RF-02 | El sistema deberá mostrar los PDF detectados en un listado seleccionable. | Alta |
| RF-03 | El usuario deberá poder seleccionar un único PDF para procesarlo. | Alta |
| RF-04 | El sistema deberá mostrar nombre, tamaño y número de páginas del PDF seleccionado. | Alta |
| RF-05 | La interfaz deberá disponer de las secciones `Procesar albarán`, `Historial` e `Información`. | Media |

### 7.2 Validación del PDF

| ID | Requisito | Prioridad |
|---|---|---|
| RF-06 | El sistema deberá validar que el archivo existe, tiene extensión PDF y puede abrirse. | Alta |
| RF-07 | El sistema deberá detectar si el PDF está vacío o protegido mediante contraseña. | Alta |
| RF-08 | El sistema deberá comprobar que el PDF contiene entre una y tres páginas. | Alta |
| RF-09 | El sistema deberá comprobar que el PDF contiene texto extraíble para el alcance del MVP. | Alta |
| RF-10 | El sistema no deberá llamar a OpenAI cuando el documento no supere las validaciones previas. | Alta |

### 7.3 Extracción y validación de datos

| ID | Requisito | Prioridad |
|---|---|---|
| RF-11 | El sistema deberá enviar únicamente el PDF seleccionado a la API de OpenAI. | Alta |
| RF-12 | El sistema deberá solicitar una salida estructurada con todos los campos definidos en la sección 6. | Alta |
| RF-13 | El sistema deberá representar mediante `null` cualquier campo que no pueda extraerse claramente. | Alta |
| RF-14 | El sistema deberá registrar los campos no leídos y las observaciones comunicadas por la extracción. | Alta |
| RF-15 | El sistema deberá validar la presencia y el tipo de los campos obligatorios antes de comparar. | Alta |
| RF-16 | El sistema deberá mostrar instrucciones comprensibles cuando no exista una clave API configurada. | Alta |

### 7.4 Normalización y comparación

| ID | Requisito | Prioridad |
|---|---|---|
| RF-17 | El sistema deberá normalizar CIF, número de albarán, proveedor, fecha, importe mediante `Decimal` y moneda antes de comparar. | Alta |
| RF-18 | El sistema deberá buscar el registro utilizando CIF y número de albarán. | Alta |
| RF-19 | Cuando exista el registro, el sistema deberá comparar proveedor, fecha, importe total y moneda. | Alta |
| RF-20 | El sistema deberá mostrar los valores del PDF y del JSON para cada campo diferente. | Alta |
| RF-21 | El sistema deberá asignar un único estado final a cada intento. | Alta |

### 7.5 Historial y reprocesamiento

| ID | Requisito | Prioridad |
|---|---|---|
| RF-22 | El sistema deberá calcular una huella SHA-256 del contenido del PDF. | Alta |
| RF-23 | El sistema deberá identificar mediante la huella si el documento se procesó anteriormente, aunque se haya renombrado. | Alta |
| RF-24 | Antes de reprocesar un documento conocido, el sistema deberá mostrar su último estado, número de intentos y opciones para consultar, reprocesar o cancelar. | Alta |
| RF-25 | Cada procesamiento iniciado deberá añadir un registro nuevo a `runtime/resultados.json` sin sobrescribir intentos anteriores. | Alta |
| RF-26 | El estado actual de un documento deberá corresponder al intento más reciente. | Alta |
| RF-27 | El usuario deberá poder consultar una tabla con todos los intentos del historial. | Alta |
| RF-28 | El usuario deberá poder filtrar el historial por estado y nombre del archivo. | Media |
| RF-29 | El usuario deberá poder consultar el detalle de un intento, incluidos datos extraídos, referencia, diferencias, campos no leídos, fecha, duración y mensaje. | Alta |

### 7.6 Entrega y evaluación

| ID | Requisito | Prioridad |
|---|---|---|
| RF-30 | El repositorio deberá incluir PDF ficticios que permitan demostrar los estados `VALIDADO`, `CON_DIFERENCIAS` y `NO_ENCONTRADO`. | Alta |
| RF-31 | El repositorio deberá incluir `.env.example` sin credenciales reales. | Alta |
| RF-32 | El README deberá explicar instalación, configuración, ejecución, pruebas, documentos de ejemplo, estados y limitaciones. | Alta |
| RF-33 | El README deberá enlazar la especificación de requisitos, arquitectura, guía de usuario, pruebas y vídeo demostrativo. | Alta |
| RF-34 | El proyecto deberá incluir un vídeo que muestre el flujo completo, el reprocesamiento y la consulta del historial. | Alta |

### 7.7 Persistencia, referencias y errores

| ID | Requisito | Prioridad |
|---|---|---|
| RF-35 | El sistema deberá crear automáticamente `runtime/resultados.json` con una estructura vacía válida cuando no exista. | Alta |
| RF-36 | El repositorio deberá incluir `data/resultados.example.json` como plantilla y ejemplo del historial. | Alta |
| RF-37 | `runtime/resultados.json` deberá excluirse del control de versiones para que cada instalación mantenga su propio historial. | Alta |
| RF-38 | El sistema deberá distinguir los errores conocidos de la API y mostrar mensajes comprensibles para autenticación, permisos, conexión, límite o cuota, tiempo de espera, solicitud inválida, servicio no disponible y respuesta inválida. | Alta |
| RF-39 | Los errores ocurridos después de iniciar el procesamiento deberán registrarse indicando, como mínimo, la etapa y el tipo de error. | Alta |
| RF-40 | Los mensajes y registros de error no deberán exponer claves, credenciales ni otros datos sensibles de configuración. | Alta |
| RF-41 | El sistema deberá comprobar que no existen registros duplicados con la misma combinación CIF + número de albarán en `albaranes.json`. | Alta |

## 8. Requisitos no funcionales

| ID | Categoría | Requisito | Prioridad |
|---|---|---|---|
| RNF-01 | Usabilidad | La interfaz deberá ser comprensible para una persona sin conocimientos de programación. | Alta |
| RNF-02 | Compatibilidad | El proyecto deberá poder ejecutarse en Windows y macOS con una versión de Python documentada. | Alta |
| RNF-03 | Instalación | Una persona externa deberá poder ejecutar el proyecto siguiendo únicamente el README. | Alta |
| RNF-04 | Persistencia | El historial deberá conservarse después de cerrar y volver a abrir la aplicación. | Alta |
| RNF-05 | Integridad | Los intentos registrados deberán tratarse como inmutables. | Alta |
| RNF-06 | Seguridad | La clave API deberá almacenarse en `.env` y no se incluirá en GitHub, registros ni mensajes de error. | Alta |
| RNF-07 | Privacidad | Los PDF incluidos deberán ser ficticios y no contener datos personales o empresariales reales. | Alta |
| RNF-08 | Fiabilidad | Los errores de validación, conexión, API y lectura deberán producir mensajes controlados y no cerrar inesperadamente la aplicación. | Alta |
| RNF-09 | Mantenibilidad | La lógica de validación, extracción, normalización, comparación e historial deberá estar separada en módulos. | Alta |
| RNF-10 | Testabilidad | Las reglas de validación, normalización, comparación e historial deberán poder probarse sin realizar llamadas reales a OpenAI. | Alta |
| RNF-11 | Trazabilidad | Los requisitos funcionales y reglas de negocio deberán relacionarse con sus correspondientes pruebas. | Media |
| RNF-12 | Rendimiento | Para los PDF del MVP, la interfaz deberá permanecer informativa durante el procesamiento y mostrar un indicador de actividad. | Media |
| RNF-13 | Auditabilidad | Cada intento deberá incluir identificador, fecha, huella, número de intento, resultado y detalle suficiente para reconstruir la decisión. | Alta |
| RNF-14 | Integridad | La escritura del historial deberá realizarse de manera segura, de modo que un fallo no sobrescriba ni corrompa los registros existentes. | Alta |
| RNF-15 | Configurabilidad | El modelo de OpenAI, el tiempo máximo de espera, los reintentos, el nivel de detalle del PDF y el máximo de páginas deberán poder configurarse mediante variables de entorno sin modificar el código fuente. | Alta |

## 9. Reglas de negocio

| ID | Regla de negocio |
|---|---|
| RN-01 | La identidad de un albarán estará formada por `cif_proveedor + numero_albaran`. |
| RN-02 | En el MVP solamente podrán procesarse PDF de una a tres páginas. |
| RN-03 | Un valor ilegible deberá representarse como `null`; no se permitirá completar por suposición un campo obligatorio. |
| RN-04 | Si falta el CIF o el número de albarán, no se realizará la búsqueda en `albaranes.json`. |
| RN-05 | Si CIF y número están completos pero no existe la combinación, el estado será `NO_ENCONTRADO`. |
| RN-06 | Si existe la combinación pero difiere cualquier campo comparado, el estado será `CON_DIFERENCIAS`. |
| RN-07 | El estado `VALIDADO` solamente se asignará si todos los campos obligatorios están presentes y coinciden. |
| RN-08 | Un documento que no supere la validación previa tendrá estado `DOCUMENTO_INVALIDO`. |
| RN-09 | Un fallo de conexión, API o aplicación tendrá estado `ERROR_TECNICO` y podrá reintentarse. |
| RN-10 | Si falta un campo obligatorio después de la extracción, el estado será `EXTRACCION_INCOMPLETA`. |
| RN-11 | `albaranes.json` será la fuente de referencia y no se modificará automáticamente. |
| RN-12 | Cada reprocesamiento generará un intento nuevo y conservará todos los anteriores. |
| RN-13 | El estado actual será el estado del intento más reciente para la misma huella. |
| RN-14 | Un documento validado podrá dejar de aparecer como pendiente, pero permanecerá accesible en el historial. |
| RN-15 | El sistema no añadirá automáticamente albaranes no encontrados. |
| RN-16 | La comparación se realizará mediante reglas programadas después de normalizar los valores. |
| RN-17 | Los importes se convertirán a `Decimal`, se redondearán a dos decimales mediante `ROUND_HALF_UP` y se compararán exactamente después de normalizarse. |
| RN-18 | La combinación CIF + número de albarán deberá ser única en `albaranes.json`. |
| RN-19 | Si existen registros duplicados para dicha combinación, no se elegirá ninguno y el estado será `ERROR_DATOS_REFERENCIA`. |
| RN-20 | Un intento comenzará cuando el usuario pulse `Procesar` y se cumplan las precondiciones de configuración necesarias para iniciar el flujo. |
| RN-21 | Si el usuario inicia el procesamiento y el PDF resulta inválido, el intento se registrará con estado `DOCUMENTO_INVALIDO`. |
| RN-22 | Los errores de API producidos después de iniciar el flujo se registrarán con estado `ERROR_TECNICO`. |
| RN-23 | Seleccionar un archivo, consultar su información, cancelar un reprocesamiento o abrir el historial no generará un intento. |
| RN-24 | Pulsar `Procesar` sin tener configurada la clave API no generará un intento. |
| RN-25 | Cada intento que alcance la fase de extracción realizará como máximo una llamada a OpenAI. La aplicación no efectuará reintentos automáticos; un nuevo intento requerirá una acción expresa del usuario. |
| RN-26 | El número de albarán se convertirá a mayúsculas y se normalizarán sus espacios, conservando los guiones, barras y puntos internos. |

## 10. Estados del sistema

| Estado | Condición | Acción permitida |
|---|---|---|
| `PENDIENTE` | El documento todavía no tiene intentos. | Procesar |
| `VALIDADO` | Todos los campos obligatorios están presentes y coinciden. | Ver historial o reprocesar |
| `EXTRACCION_INCOMPLETA` | Falta al menos un campo obligatorio. | Revisar o reprocesar |
| `NO_ENCONTRADO` | No existe la combinación CIF + número. | Revisar o reprocesar |
| `CON_DIFERENCIAS` | Existe el registro, pero difiere algún campo. | Ver diferencias o reprocesar |
| `DOCUMENTO_INVALIDO` | El PDF no supera la validación previa. | Corregir o seleccionar otro |
| `ERROR_TECNICO` | Se produjo un fallo técnico. | Reintentar |
| `ERROR_DATOS_REFERENCIA` | Los datos de referencia incumplen la unicidad o no permiten una comparación fiable. | Corregir los datos y reintentar |

## 11. Estructuras de datos

### 11.1 Registro de referencia

```json
{
  "numero_albaran": "ALB-00125",
  "cif_proveedor": "B12345678",
  "proveedor": "Distribuciones Ejemplo SL",
  "fecha": "2026-08-06",
  "importe_total": 1250.75,
  "moneda": "EUR"
}
```

### 11.2 Resultado de extracción

```json
{
  "numero_albaran": "ALB-00125",
  "cif_proveedor": "B12345678",
  "proveedor": "Distribuciones Ejemplo SL",
  "fecha": "2026-08-06",
  "importe_total": 1250.75,
  "moneda": "EUR",
  "campos_no_leidos": [],
  "observaciones": []
}
```

### 11.3 Registro de historial

Cada registro deberá contener como mínimo:

- `id_procesamiento`
- `archivo`
- `huella_archivo`
- `fecha_procesamiento`
- `numero_intento`
- `estado`
- `datos_extraidos`
- `datos_referencia`, cuando exista coincidencia de identidad
- `campos_no_leidos`
- `diferencias`
- `mensaje`
- `duracion_segundos`
- `uso_api`, cuando la API proporcione información de consumo
- `etapa_error`, cuando exista un error
- `tipo_error`, cuando exista un error

## 12. Criterios de aceptación

| ID | Requisitos relacionados | Escenario de aceptación |
|---|---|---|
| CA-01 | RF-01 a RF-04 | Dado que existen PDF en la carpeta, al abrir la aplicación se muestran sus nombres y, al seleccionar uno, aparecen nombre, tamaño y páginas. |
| CA-02 | RF-06 a RF-10, RF-25, RN-02, RN-08, RN-21 | Dado un PDF de cuatro páginas, al pulsar `Procesar` se asigna `DOCUMENTO_INVALIDO`, no se llama a OpenAI y se guarda el intento. |
| CA-03 | RF-11 a RF-15, RN-03 | Dado un PDF válido, la extracción devuelve la estructura definida y utiliza `null` para un campo que no puede leer claramente. |
| CA-04 | RF-15, RN-04, RN-10 | Dada una extracción sin CIF o número, se asigna `EXTRACCION_INCOMPLETA` y no se busca en el fichero de referencia. |
| CA-05 | RF-17 a RF-21, RN-05 | Dada una combinación CIF + número inexistente, se asigna `NO_ENCONTRADO`. |
| CA-06 | RF-17 a RF-21, RN-06 | Dada una combinación existente con importe diferente, se asigna `CON_DIFERENCIAS` y se muestran ambos importes. |
| CA-07 | RF-17 a RF-21, RN-07 | Dado un albarán cuyos campos coinciden tras normalizarse, se asigna `VALIDADO`. |
| CA-08 | RF-22 a RF-26, RN-12, RN-13 | Dado un PDF procesado, al seleccionarlo de nuevo aparece el aviso; al confirmar, se conserva el intento anterior y se añade el siguiente a `runtime/resultados.json`. |
| CA-09 | RF-27 a RF-29 | Dado que existen varios intentos, el usuario puede filtrarlos y abrir el detalle de cualquiera de ellos. |
| CA-10 | RF-16, RF-31, RNF-06 | Dado que no existe `.env` o no contiene una clave, se muestran instrucciones y no se expone ninguna credencial. |
| CA-11 | RF-30 a RF-34, RNF-03 | Dado un clon limpio, el evaluador puede instalar y ejecutar el proyecto siguiendo el README o consultar el vídeo sin disponer de clave. |
| CA-12 | RN-11, RN-15 | Después de cualquier procesamiento, `albaranes.json` mantiene exactamente sus datos originales. |
| CA-13 | RF-35 a RF-37 | Dado un clon limpio sin historial, al iniciar la aplicación se crea `runtime/resultados.json`; el archivo permanece excluido de Git. |
| CA-14 | RF-17, RN-17 | Dados importes con más de dos decimales, ambos se redondean mediante `ROUND_HALF_UP` y se comparan exactamente después de normalizarse. |
| CA-15 | RF-41, RN-18, RN-19 | Dados dos registros con el mismo CIF y número, no se elige ninguno y se asigna `ERROR_DATOS_REFERENCIA`. |
| CA-16 | RF-38 a RF-40, RN-22 | Dado un error de API después de iniciar el flujo, se registra `ERROR_TECNICO` con etapa y tipo, y se muestra un mensaje sin información sensible. |
| CA-17 | RF-16, RN-24 | Dado que falta la clave API, al pulsar `Procesar` se muestran instrucciones y no se genera un intento. |
| CA-18 | RNF-14 | Dado un fallo durante la escritura del historial, los registros anteriores permanecen íntegros. |
| CA-19 | RN-22, RN-25 | Dado un error de conexión o tiempo de espera durante la extracción, la aplicación registra `ERROR_TECNICO` y no realiza una segunda llamada automáticamente. |
| CA-20 | RF-17, RN-26 | Dados dos números de albarán que solo difieren en mayúsculas o espacios, se consideran equivalentes después de normalizarse; sus guiones, barras y puntos internos se conservan. |

## 13. Matriz inicial de trazabilidad

| Área | Requisitos | Módulo previsto | Pruebas previstas |
|---|---|---|---|
| Validación de PDF | RF-06 a RF-10 | `src/pdf_validator.py` | `tests/test_pdf_validator.py` |
| Extracción | RF-11 a RF-16 | `src/openai_extractor.py` | `tests/test_openai_extractor.py` con dobles de prueba |
| Normalización | RF-17, RN-17, RN-26 | `src/normalizer.py` | `tests/test_normalizer.py`, incluidos `test_redondeo_financiero_half_up` y `test_conserva_separadores_numero_albaran` |
| Comparación y estados | RF-19 a RF-21 | `src/comparator.py` y `src/processing_service.py` | `tests/test_comparator.py` y `tests/test_processing_service.py` |
| Datos de referencia | RF-18, RF-41, RN-18, RN-19 | `src/reference_repository.py` | `tests/test_reference_repository.py`, incluido `test_detecta_referencias_duplicadas` |
| Historial | RF-22 a RF-29, RF-35 a RF-37 | `src/history_repository.py` | `tests/test_history_repository.py`, incluidas creación inicial y escritura segura |
| Errores y configuración de API | RF-16, RF-38 a RF-40, RN-22, RN-24, RN-25 | `src/openai_extractor.py` y `src/processing_service.py` | Pruebas de autenticación, permisos, conexión, límite o cuota, tiempo de espera, solicitud inválida, servicio no disponible, respuesta inválida, ausencia de clave y ausencia de reintentos con dobles de prueba |
| Interfaz | RF-01 a RF-05 | `app.py` | Pruebas manuales documentadas |

La matriz se completará durante el diseño y la implementación, conservando los identificadores definidos en este documento.

## 14. Entrega y documentación

El repositorio deberá incluir como mínimo:

```text
comprobador-albaranes/
├── app.py
├── src/
├── data/
│   ├── pdf/
│   ├── albaranes.json
│   └── resultados.example.json
├── runtime/
│   └── .gitkeep
├── tests/
├── docs/
│   ├── requisitos.md
│   ├── arquitectura.md
│   ├── guia_usuario.md
│   └── pruebas.md
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

`runtime/resultados.json` no formará parte del repositorio. La aplicación lo creará automáticamente con una estructura vacía válida durante la primera ejecución y permanecerá excluido de Git mediante `.gitignore`.

El README contendrá un resumen y enlazará este documento. La especificación completa permanecerá en `docs/requisitos.md` como fuente única de los requisitos.

## 15. Aprobación de la fase

Esta especificación se considerará preparada para la fase de diseño cuando estén aceptados:

- el alcance del MVP;
- los campos obligatorios;
- la identidad CIF + número de albarán;
- los estados y sus reglas;
- la conservación inmutable del historial;
- el reprocesamiento con confirmación;
- la forma de entrega y evaluación.

Los cambios posteriores deberán registrarse modificando la versión y documentando qué requisitos se han añadido, cambiado o eliminado.
