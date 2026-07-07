"""Interfaz web del generador de exámenes (RF9).

Permite al docente subir el código de un proyecto, configurar el contexto
académico, revisar las preguntas generadas junto a la valoración del
revisor, seleccionar las que desea conservar y descargar el examen en
Word o PDF.

Ejecutar con:
    uv run --native-tls streamlit run app.py
"""

import io
import sys
import tempfile
import zipfile
from pathlib import Path

# Permite importar el paquete 'generador' desde src/ al ejecutar con Streamlit.
sys.path.insert(0, str(Path(__file__).parent / "src"))

# TLS: usar el almacén de certificados de Windows para las llamadas a Bedrock
# (evita el fallo de verificación de certificado tras interceptores TLS locales).
import truststore  # noqa: E402
truststore.inject_into_ssl()

import streamlit as st

from generador import (
    ContextoAcademico,
    TipoPregunta,
    Veredicto,
    procesar_repositorio,
)
from generador.examen_comun import titulo_examen
from generador.examen_docx import generar_examen_docx
from generador.examen_pdf import generar_examen_pdf


# Etiqueta y clase de estilo (sin iconos) para cada veredicto.
_ESTILO_VEREDICTO = {
    Veredicto.APROBADA: ("badge-ok", "Aprobada"),
    Veredicto.APROBADA_SUGERENCIAS: ("badge-warn", "Aprobada con sugerencias"),
    Veredicto.RECHAZADA: ("badge-bad", "Rechazada"),
    Veredicto.SIN_REVISAR: ("badge-neutral", "Sin revisar"),
    Veredicto.DESCONOCIDO: ("badge-neutral", "Sin determinar"),
}

_INCLUIR_POR_DEFECTO = {
    Veredicto.APROBADA,
    Veredicto.APROBADA_SUGERENCIAS,
    Veredicto.SIN_REVISAR,
}

_TODOS_LOS_TIPOS = {
    "Tipo test": TipoPregunta.TEST,
    "Traza de ejecución": TipoPregunta.TRAZA,
    "Respuesta abierta": TipoPregunta.ABIERTA,
}


st.set_page_config(page_title="Generador de exámenes", layout="wide")

st.markdown(
    """
    <style>
      #MainMenu, header, footer { visibility: hidden; }
      .block-container { padding-top: 2.5rem; padding-bottom: 3rem; max-width: 1040px; }
      h1 { font-weight: 700; letter-spacing: -0.4px; }
      .subtitulo { color: #6c757d; font-size: 0.95rem; margin: -0.4rem 0 1.6rem 0; }
      .seccion { font-size: 0.78rem; font-weight: 700; letter-spacing: 0.6px;
                 text-transform: uppercase; color: #8a929b; margin: 1.4rem 0 0.4rem 0; }
      .unidad { font-weight: 600; font-size: 1.02rem; }
      .meta { color: #6c757d; font-size: 0.86rem; }
      .badge { display: inline-block; padding: 2px 10px; border-radius: 12px;
               font-size: 0.76rem; font-weight: 600; white-space: nowrap; }
      .badge-ok { background: #e6f4ea; color: #1e7e34; }
      .badge-warn { background: #fff4e0; color: #b07d12; }
      .badge-bad { background: #fdecea; color: #b02a37; }
      .badge-neutral { background: #eceff1; color: #546e7a; }
      .stDownloadButton button, .stButton button { border-radius: 8px; font-weight: 600; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Generador de exámenes")
st.markdown(
    '<p class="subtitulo">Genera preguntas a partir del código de un proyecto, '
    "revísalas y descarga el examen en Word o PDF.</p>",
    unsafe_allow_html=True,
)


# ------------------------- Configuración (barra lateral) -------------------------

with st.sidebar:
    st.markdown("#### Configuración")
    asignatura = st.text_input("Asignatura", "Programación")
    curso = st.text_input("Curso", "2º de Grado")
    titulacion = st.text_input("Titulación", "Ingeniería Informática")
    nivel = st.selectbox("Nivel", ["básico", "intermedio", "avanzado"], index=1)
    tipos_sel = st.multiselect(
        "Tipos de pregunta",
        list(_TODOS_LOS_TIPOS.keys()),
        default=["Tipo test"],
    )
    usar_revisor = st.toggle(
        "Revisar las preguntas",
        value=True,
        help="Un segundo agente revisa cada pregunta y emite un veredicto de calidad.",
    )


def _construir_contexto() -> ContextoAcademico:
    tipos = [_TODOS_LOS_TIPOS[t] for t in tipos_sel] or [TipoPregunta.TEST]
    return ContextoAcademico(
        asignatura=asignatura,
        curso=curso,
        titulacion=titulacion,
        nivel=nivel,
        tipos_pregunta=tipos,
        usar_revisor=usar_revisor,
    )


# ------------------------- Entrada de código -------------------------

st.markdown('<p class="seccion">Código del proyecto</p>', unsafe_allow_html=True)

if "generando" not in st.session_state:
    st.session_state.generando = False

archivos = st.file_uploader(
    "Sube el proyecto en un .zip (o selecciona archivos .py/.java sueltos)",
    type=["zip", "py", "java"],
    accept_multiple_files=True,
    disabled=st.session_state.generando,
)

generar = st.button(
    "Generar preguntas",
    type="primary",
    disabled=st.session_state.generando or not archivos,
)

# Fase 1: al pulsar, se guardan los bytes de los archivos y se entra en estado
# "generando". Guardar los bytes evita depender del widget, que el docente
# podría cambiar durante la generación.
if generar and archivos:
    st.session_state["_archivos"] = [(a.name, a.getvalue()) for a in archivos]
    st.session_state["resultados"] = None
    st.session_state["_aviso"] = None
    st.session_state.generando = True
    st.rerun()

# Fase 2: se genera con los controles ya deshabilitados (rerun anterior), de modo
# que la interfaz no se pueda alterar a mitad de la generación.
if st.session_state.generando:
    contexto = _construir_contexto()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            carpeta = Path(tmp)
            for nombre, datos in st.session_state.get("_archivos", []):
                if nombre.lower().endswith(".zip"):
                    with zipfile.ZipFile(io.BytesIO(datos)) as z:
                        z.extractall(carpeta)
                else:
                    (carpeta / nombre).write_bytes(datos)
            with st.spinner("Generando preguntas. Puede tardar según el número de unidades."):
                resultados = procesar_repositorio(carpeta, contexto)
        st.session_state["resultados"] = resultados
        if not resultados:
            st.session_state["_aviso"] = ("warning", None)
    except Exception as e:
        # La generación depende de un servicio externo no determinista (Amazon
        # Bedrock): ante un fallo de conexión, credenciales o del modelo, se
        # informa al docente en lugar de mostrar un error técnico sin contexto.
        # Se distingue el fallo de autenticación (token/credenciales) del resto.
        st.session_state["resultados"] = None
        _texto = str(e).lower()
        _es_auth = any(
            clave in _texto
            for clave in ("accessdenied", "authentication", "api key",
                          "credential", "unauthorized", "not authorized", "token")
        )
        st.session_state["_aviso"] = ("error_auth" if _es_auth else "error", e)
    finally:
        st.session_state.generando = False
        st.rerun()

# Aviso persistido tras la generación (superviviente al rerun de la fase 2).
_aviso = st.session_state.get("_aviso")
if _aviso:
    _clase, _detalle = _aviso
    if _clase == "warning":
        st.warning(
            "No se ha generado ninguna pregunta. Puede que el proyecto no "
            "contenga unidades de código evaluables (todas triviales o de "
            "plantilla), o que el archivo subido no sea válido."
        )
    else:
        if _clase == "error_auth":
            st.error(
                "No se han podido generar las preguntas: el acceso al servicio "
                "de generación (Amazon Bedrock) ha sido denegado. Comprueba que "
                "las credenciales de acceso ---el token de Bedrock--- sean "
                "correctas y sigan vigentes."
            )
        else:
            st.error(
                "No se han podido generar las preguntas. El servicio de generación "
                "(Amazon Bedrock) puede estar temporalmente no disponible o haber "
                "devuelto un error. Vuelve a intentarlo; si el problema persiste, "
                "revisa la conexión y las credenciales de acceso."
            )
        if _detalle is not None:
            with st.expander("Ver detalle técnico"):
                st.exception(_detalle)


# ------------------------- Revisión y selección -------------------------

resultados = st.session_state.get("resultados")

if resultados:
    st.markdown('<p class="seccion">Revisión de preguntas</p>', unsafe_allow_html=True)
    st.caption(f"Se han generado {len(resultados)} preguntas.")

    for idx, r in enumerate(resultados):
        clase, etiqueta = _ESTILO_VEREDICTO.get(r.veredicto, ("badge-neutral", "Sin determinar"))
        with st.container(border=True):
            izq, der = st.columns([0.74, 0.26])
            with izq:
                st.markdown(
                    f'<span class="unidad">{r.unidad.nombre}</span> '
                    f'<span class="meta">· {r.tipo.value}</span> &nbsp; '
                    f'<span class="badge {clase}">{etiqueta}</span>',
                    unsafe_allow_html=True,
                )
            with der:
                st.checkbox(
                    "Incluir en el examen",
                    value=r.veredicto in _INCLUIR_POR_DEFECTO,
                    key=f"incluir_{idx}",
                )
            st.markdown(r.pregunta_generada)
            if r.comentario_revisor:
                with st.expander("Ver revisión del agente"):
                    st.markdown(r.comentario_revisor)

    # ------------------------- Descarga -------------------------

    st.markdown('<p class="seccion">Descargar examen</p>', unsafe_allow_html=True)

    contexto = _construir_contexto()
    titulo = st.text_input(
        "Título del examen",
        value=titulo_examen(None, asignatura),
    )

    seleccionadas = [
        r for idx, r in enumerate(resultados)
        if st.session_state.get(f"incluir_{idx}")
    ]
    st.caption(f"Preguntas seleccionadas: {len(seleccionadas)}")

    if seleccionadas:
        col_word, col_pdf = st.columns(2)
        with col_word:
            st.download_button(
                "Descargar en Word",
                data=generar_examen_docx(seleccionadas, contexto, titulo),
                file_name="examen.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                type="primary",
                use_container_width=True,
            )
        with col_pdf:
            st.download_button(
                "Descargar en PDF",
                data=generar_examen_pdf(seleccionadas, contexto, titulo),
                file_name="examen.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
    else:
        st.info("Marca al menos una pregunta para generar el examen.")
