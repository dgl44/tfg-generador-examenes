"""Demo cualitativa de configurabilidad: una misma unidad de código genera
preguntas distintas al variar el nivel de dificultad y el tipo de pregunta.
Uso: python ablacion/demo_configurabilidad.py [nombre_unidad]
"""

import sys
from pathlib import Path

import truststore  # noqa: E402
truststore.inject_into_ssl()

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src" / "generador"))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(REPO / ".env")

from parser import extraer_unidades, firma_unidad  # noqa: E402
from modelos import ContextoAcademico, TipoPregunta  # noqa: E402
from agentes import construir_crew_para_unidad  # noqa: E402
from pipeline import _construir_resultado  # noqa: E402
from examen_comun import enunciado_visible  # noqa: E402

PLANTILLA = Path(r"C:/Users/Damian/Documents/UA_INFORMATICA/3º/SI/P1plantilla")
ALUMNO = Path(r"C:/Users/Damian/Documents/UA_INFORMATICA/3º/SI/SI-P1-ENTREGAFINAL/Fuente")

# Variantes a generar: (tipo, nivel)
VARIANTES = [
    (TipoPregunta.TEST, "básico"),
    (TipoPregunta.TEST, "avanzado"),
    (TipoPregunta.TRAZA, "intermedio"),
    (TipoPregunta.ABIERTA, "intermedio"),
]


def buscar_unidad(nombre):
    firmas_plant = set()
    for f in PLANTILLA.rglob("*.py"):
        for u in extraer_unidades(f):
            firmas_plant.add(firma_unidad(u))
    for f in sorted(ALUMNO.rglob("*.py")):
        for u in extraer_unidades(f):
            if u.nombre == nombre and firma_unidad(u) not in firmas_plant:
                return u
    raise SystemExit(f"No se encontró la unidad propia '{nombre}'")


def main():
    nombre = sys.argv[1] if len(sys.argv) > 1 else "valorCalorico"
    unidad = buscar_unidad(nombre)
    print(f"UNIDAD: {unidad.nombre}\n{'='*70}\n{unidad.codigo}\n{'='*70}\n")

    for tipo, nivel in VARIANTES:
        ctx = ContextoAcademico(asignatura="Sistemas Inteligentes", nivel=nivel,
                                usar_revisor=False)
        crew = construir_crew_para_unidad(unidad, ctx, tipo)
        r = _construir_resultado(unidad, tipo, crew.kickoff())
        print(f"\n### tipo={tipo.value}  nivel={nivel}\n{'-'*70}")
        print(enunciado_visible(r.pregunta_generada))
        print()


if __name__ == "__main__":
    main()
