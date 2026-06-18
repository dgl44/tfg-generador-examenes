"""Pipeline que procesa un archivo de código completo.

Combina el parser tree-sitter con el patrón generator-critic: filtra
unidades triviales y, por cada unidad relevante, genera una pregunta
(tipo test, traza de ejecución o abierta) adaptada al contexto académico
y la revisa con un segundo agente.
"""

import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Permitir importar otros módulos del mismo directorio cuando se ejecuta
# como script directo (`uv run python src/generador/pipeline_repositorio.py`).
sys.path.insert(0, str(Path(__file__).parent))

from crewai import Agent, Crew, LLM, Process, Task

from parser import UnidadCodigo, extraer_unidades, lenguajes_soportados

llm_haiku = LLM(
    model="bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0",
)


# ------------------------- Tipos de pregunta -------------------------

class TipoPregunta(str, Enum):
    TEST   = "test"    # Opción múltiple con 4 opciones
    TRAZA  = "traza"   # Razonamiento sobre ejecución del código
    ABIERTA = "abierta"  # Pregunta de respuesta libre


# ------------------------- Contexto académico -------------------------

@dataclass
class ContextoAcademico:
    """Parámetros configurables por el docente para adaptar las preguntas."""
    asignatura: str = "Programación"
    curso: str = "2º de Grado"
    titulacion: str = "Ingeniería Informática"
    nivel: str = "intermedio"  # básico | intermedio | avanzado
    tipos_pregunta: list[TipoPregunta] = field(
        default_factory=lambda: [TipoPregunta.TEST]
    )
    usar_revisor: bool = True  # False = solo generador (variante de ablación)

    def descripcion(self) -> str:
        return (
            f"{self.asignatura} ({self.curso}, {self.titulacion}), "
            f"nivel {self.nivel}"
        )


# ------------------------- Resultado estructurado -------------------------

class Veredicto(str, Enum):
    APROBADA = "APROBADA"
    APROBADA_SUGERENCIAS = "APROBADA CON SUGERENCIAS"
    RECHAZADA = "RECHAZADA"
    SIN_REVISAR = "SIN REVISAR"   # el revisor estaba desactivado
    DESCONOCIDO = "DESCONOCIDO"   # el revisor actuó pero no se pudo deducir


@dataclass
class ResultadoPregunta:
    """Resultado estructurado de generar y revisar una pregunta.

    Separa la pregunta generada de la crítica del revisor para que la
    capa de presentación (futuro frontend) pueda mostrarlas por separado
    y permitir al docente editar, aprobar o descartar cada pregunta de
    forma individual antes de incluirla en el examen.
    """
    unidad: UnidadCodigo
    tipo: TipoPregunta
    pregunta_generada: str
    veredicto: Veredicto
    comentario_revisor: str


def _clasificar_veredicto(fragmento: str) -> Veredicto:
    """Clasifica un fragmento de texto (en mayúsculas) en un veredicto.

    El orden importa: 'RECHAZADA' se comprueba antes que 'APROBADA' porque
    un texto que rechaza la pregunta suele mencionar también la palabra
    'aprobada' en otros contextos ('no puede ser aprobada').
    """
    if "RECHAZADA" in fragmento:
        return Veredicto.RECHAZADA
    if "SUGERENCIA" in fragmento:  # "APROBADA CON SUGERENCIAS"
        return Veredicto.APROBADA_SUGERENCIAS
    if "APROBADA" in fragmento:
        return Veredicto.APROBADA
    return Veredicto.DESCONOCIDO


def _extraer_veredicto(texto_revisor: str) -> Veredicto:
    """Deduce el veredicto a partir del texto libre del revisor.

    Heurística: se clasifica primero la ventana de texto que sigue a la
    última aparición del marcador 'VEREDICTO', ya que ahí es donde el
    revisor declara su decisión. Si no hay marcador o no es concluyente,
    se recurre a un escaneo del texto completo.
    """
    texto = texto_revisor.upper()
    pos = texto.rfind("VEREDICTO")
    if pos != -1:
        resultado = _clasificar_veredicto(texto[pos:pos + 80])
        if resultado is not Veredicto.DESCONOCIDO:
            return resultado
    return _clasificar_veredicto(texto)


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
        veredicto = _extraer_veredicto(comentario)
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


# ------------------------- Tareas por unidad -------------------------

def _prompts_por_tipo(
    tipo_pregunta: TipoPregunta,
    unidad: UnidadCodigo,
    tipo_str: str,
    docstring_info: str,
    desc: str,
    nivel: str,
) -> tuple[str, str, str, str]:
    """Devuelve (desc_generar, output_generar, desc_revisar, output_revisar)."""
    codigo_bloque = f"{docstring_info}\n\nCódigo:\n```\n{unidad.codigo}\n```"

    if tipo_pregunta == TipoPregunta.TEST:
        desc_gen = (
            f"Contexto: pregunta para {desc}.\n\n"
            f"Analiza la siguiente {tipo_str} llamada '{unidad.nombre}' y genera "
            "UNA pregunta tipo test con 4 opciones (A, B, C, D), donde solo una "
            f"es correcta. La pregunta debe evaluar comprensión a nivel {nivel}, "
            "no sintaxis trivial. Indica la respuesta correcta y justifica brevemente."
            f"{codigo_bloque}"
        )
        out_gen = (
            "Una pregunta tipo test con enunciado claro, 4 opciones etiquetadas "
            "A-D, la respuesta correcta indicada y una justificación breve."
        )
        desc_rev = (
            f"Contexto: la pregunta es para {desc}.\n\n"
            "Ten en cuenta que el código de la unidad se mostrará al estudiante "
            "junto al enunciado, por lo que NO debes penalizar que la pregunta "
            "no incluya literalmente el código.\n\n"
            "Revisa la pregunta evaluando:\n"
            "1. ¿El enunciado es claro y preciso?\n"
            "2. ¿Las 4 opciones están bien planteadas (una correcta inequívoca, "
            "distractores plausibles)?\n"
            "3. ¿La respuesta marcada es realmente correcta dado el código?\n"
            "4. ¿La justificación del generador es correcta?\n"
            f"5. ¿El nivel de dificultad es apropiado para {desc}? "
            "Rechaza preguntas trivialmente obvias para ese nivel.\n\n"
            "Veredicto: APROBADA, APROBADA CON SUGERENCIAS o RECHAZADA."
        )
        out_rev = (
            "Veredicto (APROBADA / APROBADA CON SUGERENCIAS / RECHAZADA) "
            "seguido de un comentario detallado."
        )

    elif tipo_pregunta == TipoPregunta.TRAZA:
        desc_gen = (
            f"Contexto: pregunta de traza para {desc}.\n\n"
            f"Analiza la siguiente {tipo_str} llamada '{unidad.nombre}'. "
            "Formula UNA pregunta de razonamiento sobre ejecución: proporciona "
            "una llamada concreta con argumentos reales e indica qué debe responder "
            "el estudiante (valor de retorno, valor de una variable en un punto dado, "
            "o salida impresa). Incluye la respuesta correcta y explica el razonamiento "
            "paso a paso."
            f"{codigo_bloque}"
        )
        out_gen = (
            "Enunciado con la llamada concreta, pregunta clara sobre el resultado "
            "de la ejecución, respuesta correcta y razonamiento paso a paso."
        )
        desc_rev = (
            f"Contexto: pregunta de traza para {desc}.\n\n"
            "Ten en cuenta que el código de la unidad se mostrará al estudiante "
            "junto al enunciado, por lo que NO debes penalizar que la pregunta "
            "no incluya literalmente el código.\n\n"
            "Revisa la pregunta evaluando:\n"
            "1. ¿La llamada de ejemplo es válida para el código dado?\n"
            "2. ¿La respuesta esperada es determinista e inequívoca?\n"
            "3. ¿El razonamiento paso a paso es correcto?\n"
            f"4. ¿La dificultad es adecuada para nivel {nivel}?\n\n"
            "Veredicto: APROBADA, APROBADA CON SUGERENCIAS o RECHAZADA."
        )
        out_rev = (
            "Veredicto (APROBADA / APROBADA CON SUGERENCIAS / RECHAZADA) "
            "seguido de un comentario detallado."
        )

    else:  # ABIERTA
        desc_gen = (
            f"Contexto: pregunta abierta para {desc}.\n\n"
            f"Analiza la siguiente {tipo_str} llamada '{unidad.nombre}'. "
            "Formula UNA pregunta abierta corta que requiera al estudiante razonar "
            "sobre el código: explicar una decisión de diseño, describir el propósito "
            "de un bloque concreto, identificar una limitación, o proponer cómo "
            "extenderlo para un nuevo requisito. Incluye una respuesta modelo orientativa."
            f"{codigo_bloque}"
        )
        out_gen = (
            "Pregunta abierta con enunciado claro y una respuesta modelo orientativa "
            "que el docente puede usar como referencia para la corrección."
        )
        desc_rev = (
            f"Contexto: pregunta abierta para {desc}.\n\n"
            "Ten en cuenta que el código de la unidad se mostrará al estudiante "
            "junto al enunciado, por lo que NO debes penalizar que la pregunta "
            "no incluya literalmente el código.\n\n"
            "Revisa la pregunta evaluando:\n"
            "1. ¿El enunciado está bien delimitado (no es demasiado vago)?\n"
            "2. ¿La respuesta modelo es técnicamente correcta?\n"
            "3. ¿La pregunta requiere comprensión real del código, no solo lectura "
            "superficial?\n"
            f"4. ¿La dificultad es adecuada para nivel {nivel}?\n\n"
            "Veredicto: APROBADA, APROBADA CON SUGERENCIAS o RECHAZADA."
        )
        out_rev = (
            "Veredicto (APROBADA / APROBADA CON SUGERENCIAS / RECHAZADA) "
            "seguido de un comentario detallado."
        )

    return desc_gen, out_gen, desc_rev, out_rev


def construir_crew_para_unidad(
    unidad: UnidadCodigo,
    contexto: ContextoAcademico,
    tipo_pregunta: TipoPregunta = TipoPregunta.TEST,
) -> Crew:
    """Crea un crew con las tareas de generar + revisar para una unidad."""
    tipo_str = "función" if unidad.tipo == "funcion" else "clase"
    docstring_info = f"\nDocstring: {unidad.docstring}" if unidad.docstring else ""
    desc = contexto.descripcion()

    desc_gen, out_gen, desc_rev, out_rev = _prompts_por_tipo(
        tipo_pregunta, unidad, tipo_str, docstring_info, desc, contexto.nivel
    )

    agente_generador = Agent(
        role="Docente generador de preguntas",
        goal="Crear una pregunta de examen clara y bien formulada sobre un fragmento de código.",
        backstory=(
            f"Eres un profesor con años de experiencia diseñando exámenes para "
            f"{contexto.asignatura} de {contexto.titulacion}. Tus preguntas están "
            f"calibradas para estudiantes de {contexto.curso} con nivel {contexto.nivel}: "
            "ni triviales ni esotéricas. Evalúan comprensión real del código."
        ),
        llm=llm_haiku,
        verbose=False,
    )

    tarea_generar = Task(
        description=desc_gen,
        expected_output=out_gen,
        agent=agente_generador,
    )

    agentes = [agente_generador]
    tareas = [tarea_generar]

    # El revisor es opcional: desactivarlo da la variante "sin revisión"
    # del estudio de ablación (objetivo 3).
    if contexto.usar_revisor:
        agente_revisor = Agent(
            role="Revisor pedagógico de preguntas de examen",
            goal="Validar que las preguntas son claras, técnicamente correctas y adecuadas al nivel.",
            backstory=(
                "Eres un coordinador docente experto en evaluación. Detectas errores "
                "técnicos, ambigüedades y preguntas triviales, y devuelves un veredicto "
                "claro con sugerencias concretas cuando es necesario."
            ),
            llm=llm_haiku,
            verbose=False,
        )

        tarea_revisar = Task(
            description=desc_rev,
            expected_output=out_rev,
            agent=agente_revisor,
            context=[tarea_generar],
        )

        agentes.append(agente_revisor)
        tareas.append(tarea_revisar)

    return Crew(
        agents=agentes,
        tasks=tareas,
        process=Process.sequential,
        verbose=False,
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


# Directorios que no contienen código del alumno
_DIRS_IGNORADOS = {
    ".venv", "venv", "__pycache__", ".git",
    "node_modules", "dist", "build", "migrations",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
}


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


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: uv run python src/generador/pipeline_repositorio.py <archivo_o_carpeta>")
        sys.exit(1)

    ruta = Path(sys.argv[1])
    # Contexto de ejemplo — en la versión web el docente lo configurará
    contexto = ContextoAcademico(
        asignatura="Estructuras de Datos",
        curso="2º de Grado",
        titulacion="Ingeniería Informática",
        nivel="intermedio",
        tipos_pregunta=[TipoPregunta.TEST, TipoPregunta.TRAZA, TipoPregunta.ABIERTA],
    )

    if ruta.is_dir():
        resultados = procesar_repositorio(ruta, contexto)
    else:
        resultados = procesar_archivo(ruta, contexto)

    from collections import Counter

    conteo = Counter(r.veredicto.value for r in resultados)

    print(f"\n{'#' * 60}")
    print(f"# RESUMEN: {len(resultados)} preguntas generadas")
    print(f"# Veredictos: {dict(conteo)}")
    print(f"{'#' * 60}\n")
    for i, r in enumerate(resultados, start=1):
        print(f"\n{'-' * 60}")
        print(f"Pregunta {i} [{r.tipo.value}] — {r.veredicto.value} — {r.unidad}")
        print(f"{'-' * 60}")
        print("\n>>> PREGUNTA GENERADA:\n")
        print(r.pregunta_generada)
        print("\n>>> REVISIÓN:\n")
        print(r.comentario_revisor)
