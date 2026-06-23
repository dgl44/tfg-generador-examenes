"""Punto de entrada por línea de comandos del generador de exámenes.

Uso:
    uv run python -m generador <archivo_o_carpeta>

Procesa un archivo o un repositorio completo con un contexto académico de
ejemplo e imprime las preguntas generadas junto a su revisión. En la versión
web este contexto lo configurará el docente.
"""

import sys
from collections import Counter
from pathlib import Path

# Permitir las importaciones planas (from parser import ...) de los módulos del
# paquete tanto al ejecutar como módulo (python -m generador) como en script.
sys.path.insert(0, str(Path(__file__).parent))

from modelos import ContextoAcademico, TipoPregunta
from pipeline import procesar_archivo, procesar_repositorio


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Uso: uv run python -m generador <archivo_o_carpeta>")
        return 1

    ruta = Path(argv[1])

    # Contexto de ejemplo — en la versión web el docente lo configurará.
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

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
