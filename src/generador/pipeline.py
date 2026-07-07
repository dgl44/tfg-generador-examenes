"""Orquestación del flujo completo: parser → filtrado → generación → revisión.

Coordina las capas inferiores para procesar un archivo o un repositorio
completo y devolver una lista de :class:`ResultadoPregunta`. No contiene
lógica de prompts ni de agentes; se limita a recorrer las unidades de código
y delegar en la capa de agentes.
"""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from agentes import construir_crew_para_unidad, extraer_veredicto
from modelos import (
    ContextoAcademico,
    ResultadoPregunta,
    TipoPregunta,
    Veredicto,
)
from parser import UnidadCodigo, extraer_unidades, firma_unidad, lenguajes_soportados


# Directorios que no contienen código del alumno
_DIRS_IGNORADOS = {
    ".venv", "venv", "__pycache__", ".git",
    "node_modules", "dist", "build", "migrations",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
}


# ------------------------- Construcción del resultado -------------------------

def _texto_tarea(task_output) -> str:
    """Extrae el texto plano de la salida de una tarea de CrewAI."""
    return getattr(task_output, "raw", str(task_output)).strip()


def _construir_resultado(
    unidad: UnidadCodigo,
    tipo: TipoPregunta,
    salida_crew,
) -> ResultadoPregunta:
    """Convierte la salida del crew (generar + revisar) en un resultado estructurado."""
    tareas = getattr(salida_crew, "tasks_output", None) or []
    pregunta = _texto_tarea(tareas[0]) if len(tareas) >= 1 else str(salida_crew).strip()
    if len(tareas) >= 2:
        comentario = _texto_tarea(tareas[1])
        veredicto = extraer_veredicto(comentario)
    else:
        comentario = ""
        veredicto = Veredicto.SIN_REVISAR
    return ResultadoPregunta(
        unidad=unidad,
        tipo=tipo,
        pregunta_generada=pregunta,
        veredicto=veredicto,
        comentario_revisor=comentario,
    )


# ------------------------- Pipeline principal -------------------------

def firmas_de_plantilla(ruta_plantilla: str | Path) -> set[str]:
    """Recopila las firmas de todas las unidades de un proyecto de plantilla.

    Sirve para descartar el código base que proporciona el docente: las unidades
    del alumno cuya firma coincida con la plantilla no se han escrito (o no se han
    modificado) y no procede evaluarlas.
    """
    carpeta = Path(ruta_plantilla)
    firmas: set[str] = set()
    for archivo in carpeta.rglob("*"):
        if archivo.is_file() and archivo.suffix in set(lenguajes_soportados()):
            firmas.update(firma_unidad(u) for u in extraer_unidades(archivo))
    return firmas


def procesar_archivo(
    ruta_archivo: str | Path,
    contexto: ContextoAcademico | None = None,
    firmas_plantilla: set[str] | None = None,
) -> list[ResultadoPregunta]:
    """Procesa un archivo: extrae unidades, filtra triviales y genera+revisa preguntas.

    Si se pasan ``firmas_plantilla``, se descartan además las unidades idénticas a
    las de la plantilla (código base que el alumno no ha escrito).
    """
    if contexto is None:
        contexto = ContextoAcademico()
    firmas_plantilla = firmas_plantilla or set()

    unidades = extraer_unidades(ruta_archivo)

    def es_plantilla(u):
        return firma_unidad(u) in firmas_plantilla

    triviales = [u for u in unidades if u.es_trivial()]
    de_plantilla = [u for u in unidades if not u.es_trivial() and es_plantilla(u)]
    a_procesar = [u for u in unidades if not u.es_trivial() and not es_plantilla(u)]

    print(f"\n{'#' * 60}")
    print(f"# Encontradas {len(unidades)} unidades en {ruta_archivo}")
    print(f"# Contexto: {contexto.descripcion()}")
    if triviales:
        print(f"# Descartadas {len(triviales)} triviales: {[u.nombre for u in triviales]}")
    if de_plantilla:
        print(f"# Descartadas {len(de_plantilla)} de plantilla: {[u.nombre for u in de_plantilla]}")
    print(f"# A procesar: {len(a_procesar)}")
    print(f"{'#' * 60}\n")

    tipos = contexto.tipos_pregunta
    resultados: list[ResultadoPregunta] = []
    fallos = 0
    ultimo_error: Exception | None = None
    for i, unidad in enumerate(a_procesar, start=1):
        tipo = tipos[(i - 1) % len(tipos)]
        print(f"\n{'=' * 60}")
        print(f"UNIDAD {i}/{len(a_procesar)}: {unidad}  [tipo: {tipo.value}]")
        print(f"{'=' * 60}")
        # La generación depende de un servicio externo no determinista: si una
        # unidad falla (error del modelo o de la red), se omite y se continúa con
        # las demás, de modo que un fallo puntual no invalide todo el examen.
        try:
            crew = construir_crew_para_unidad(unidad, contexto, tipo)
            salida = crew.kickoff()
            resultados.append(_construir_resultado(unidad, tipo, salida))
        except Exception as e:
            fallos += 1
            ultimo_error = e
            print(f"  [aviso] unidad '{unidad.nombre}' omitida por un error: {e}")

    # Si había unidades que procesar y TODAS fallaron, no es una ausencia de
    # unidades evaluables sino un fallo sistémico (credenciales, red o servicio
    # no disponible): se propaga para que la capa de presentación lo distinga.
    if a_procesar and not resultados and fallos:
        raise RuntimeError(
            f"No se pudo generar ninguna pregunta: fallaron las {fallos} "
            f"unidades procesadas. Último error: {ultimo_error}"
        )

    return resultados


def procesar_repositorio(
    ruta_carpeta: str | Path,
    contexto: ContextoAcademico | None = None,
    ruta_plantilla: str | Path | None = None,
) -> list[ResultadoPregunta]:
    """Procesa todos los archivos soportados de una carpeta recursivamente.

    Si se indica ``ruta_plantilla`` (el código base que entrega el docente), se
    descartan las unidades del alumno idénticas a las de esa plantilla, de modo
    que solo se evalúa el código que el estudiante ha escrito o modificado.
    """
    if contexto is None:
        contexto = ContextoAcademico()

    carpeta = Path(ruta_carpeta)
    extensiones = set(lenguajes_soportados())
    firmas_plantilla = firmas_de_plantilla(ruta_plantilla) if ruta_plantilla else set()

    archivos = [
        p for p in carpeta.rglob("*")
        if p.is_file()
        and p.suffix in extensiones
        and not any(parte in _DIRS_IGNORADOS for parte in p.parts)
    ]

    print(f"\n{'#' * 60}")
    print(f"# Repositorio: {carpeta}")
    print(f"# Archivos encontrados: {len(archivos)}")
    print(f"# Contexto: {contexto.descripcion()}")
    if firmas_plantilla:
        print(f"# Plantilla: {ruta_plantilla} ({len(firmas_plantilla)} unidades base)")
    print(f"{'#' * 60}\n")

    todos: list[ResultadoPregunta] = []
    for archivo in sorted(archivos):
        todos.extend(procesar_archivo(archivo, contexto, firmas_plantilla))

    return todos
