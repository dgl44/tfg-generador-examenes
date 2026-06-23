"""Capa de agentes: configuración del LLM, construcción del crew y veredicto.

Concentra todo el acoplamiento con CrewAI y AWS Bedrock. El resto del sistema
trabaja con los modelos de dominio y nunca importa CrewAI directamente, de modo
que cambiar de framework de orquestación o de modelo quedaría confinado aquí.
"""

from crewai import Agent, Crew, LLM, Process, Task

from modelos import ContextoAcademico, TipoPregunta, Veredicto
from parser import UnidadCodigo
from prompts import construir_prompts


# Modelo en desarrollo: Claude Haiku 4.5 (inference profile cross-region) en
# us-east-1. La validación final se hace con Sonnet 4.6 cambiando este identificador.
llm_haiku = LLM(
    model="bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0",
)


# ------------------------- Extracción de veredicto -------------------------

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


def extraer_veredicto(texto_revisor: str) -> Veredicto:
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


# ------------------------- Construcción del crew -------------------------

def construir_crew_para_unidad(
    unidad: UnidadCodigo,
    contexto: ContextoAcademico,
    tipo_pregunta: TipoPregunta = TipoPregunta.TEST,
) -> Crew:
    """Crea un crew con las tareas de generar + revisar para una unidad.

    Si ``contexto.usar_revisor`` es False, el crew contiene solo el generador
    (variante "sin revisión" del estudio de ablación del objetivo 3).
    """
    prompts = construir_prompts(
        tipo_pregunta, unidad, contexto.descripcion(), contexto.nivel
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
        description=prompts.desc_generar,
        expected_output=prompts.output_generar,
        agent=agente_generador,
    )

    agentes = [agente_generador]
    tareas = [tarea_generar]

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
            description=prompts.desc_revisar,
            expected_output=prompts.output_revisar,
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
