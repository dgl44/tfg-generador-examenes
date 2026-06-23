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
from parser import UnidadCodigo, extraer_unidades, lenguajes_soportados


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

def procesar_archivo(
    ruta_archivo: str | Path,
    contexto: ContextoAcademico | None = None,
) -> list[ResultadoPregunta]:
    """Procesa un archivo: extrae unidades, filtra triviales y genera+revisa preguntas."""
    if contexto is None:
        contexto = ContextoAcademico()

    unidades = extraer_unidades(ruta_archivo)

    triviales = [u for u in unidades if u.es_trivial()]
    a_procesar = [u for u in unidades if not u.es_trivial()]

    print(f"\n{'#' * 60}")
    print(f"# Encontradas {len(unidades)} unidades en {ruta_archivo}")
    print(f"# Contexto: {contexto.descripcion()}")
    if triviales:
        print(f"# Descartadas {len(triviales)} triviales: {[u.nombre for u in triviales]}")
    print(f"# A procesar: {len(a_procesar)}")
    print(f"{'#' * 60}\n")

    tipos = contexto.tipos_pregunta
    resultados: list[ResultadoPregunta] = []
    for i, unidad in enumerate(a_procesar, start=1):
        tipo = tipos[(i - 1) % len(tipos)]
        print(f"\n{'=' * 60}")
        print(f"UNIDAD {i}/{len(a_procesar)}: {unidad}  [tipo: {tipo.value}]")
        print(f"{'=' * 60}")
        crew = construir_crew_para_unidad(unidad, contexto, tipo)
        salida = crew.kickoff()
        resultados.append(_construir_resultado(unidad, tipo, salida))

    return resultados


def procesar_repositorio(
    ruta_carpeta: str | Path,
    contexto: ContextoAcademico | None = None,
) -> list[ResultadoPregunta]:
    """Procesa todos los archivos soportados de una carpeta recursivamente."""
    if contexto is None:
        contexto = ContextoAcademico()

    carpeta = Path(ruta_carpeta)
    extensiones = set(lenguajes_soportados())

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
    print(f"{'#' * 60}\n")

    todos: list[ResultadoPregunta] = []
    for archivo in sorted(archivos):
        todos.extend(procesar_archivo(archivo, contexto))

    return todos
