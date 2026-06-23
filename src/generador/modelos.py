"""Modelos de dominio del generador de exámenes.

Reúne los tipos de datos que circulan entre las capas (parser, prompts,
agentes, pipeline) sin depender de CrewAI ni de ningún LLM. Mantener este
módulo libre de dependencias pesadas permite que el futuro frontend importe
los modelos sin arrastrar la cadena de orquestación.
"""

from dataclasses import dataclass, field
from enum import Enum

from parser import UnidadCodigo


# ------------------------- Tipos de pregunta -------------------------

class TipoPregunta(str, Enum):
    TEST = "test"        # Opción múltiple con 4 opciones
    TRAZA = "traza"      # Razonamiento sobre ejecución del código
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
