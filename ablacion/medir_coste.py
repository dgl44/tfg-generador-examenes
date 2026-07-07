"""Mide el coste real (tokens y $) por pregunta generada con el sistema completo.

Calca el flujo de ``correr_ablacion.py`` (mismo corpus, mismo contexto, crew
generador+revisor con Haiku), pero en lugar de guardar las preguntas, lee
``crew.usage_metrics`` tras cada ``kickoff()`` para acumular los tokens de
entrada y de salida, y calcula el coste con el precio de Claude Haiku 4.5.

Precio Claude Haiku 4.5 (Amazon Bedrock / API Anthropic, verificado 2026-07-06):
    entrada:  1,00 $ / millón de tokens
    salida:   5,00 $ / millón de tokens

- Uso: python ablacion/medir_coste.py [LIMITE]   (LIMITE opcional; por defecto 12)
  Ej.: python ablacion/medir_coste.py 56   → mide sobre todo el corpus (~15 min)
"""

import sys
import json
import time
from pathlib import Path

import truststore  # noqa: E402
truststore.inject_into_ssl()

REPO = Path(r"c:/Users/Damian/Documents/UA_INFORMATICA/tfg/tfg-generador-examenes")
sys.path.insert(0, str(REPO / "src" / "generador"))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(REPO / ".env")

from parser import UnidadCodigo  # noqa: E402
from modelos import ContextoAcademico, TipoPregunta  # noqa: E402
from agentes import construir_crew_para_unidad  # noqa: E402

# --- Precio de Claude Haiku 4.5 ($ por millón de tokens) ---
PRECIO_ENTRADA = 1.00
PRECIO_SALIDA = 5.00
USD_A_EUR = 0.92  # tipo de cambio aproximado; ajústalo al del día si quieres el € exacto

CORPUS = REPO / "ablacion" / "corpus.json"

CONTEXTO = ContextoAcademico(
    asignatura="Programación",
    curso="Grado",
    titulacion="Ingeniería Informática",
    nivel="intermedio",
    usar_revisor=True,
)
TIPOS = [TipoPregunta.TEST, TipoPregunta.TRAZA, TipoPregunta.ABIERTA]


def unidad_desde_dict(d: dict) -> UnidadCodigo:
    return UnidadCodigo(
        tipo=d["tipo"], nombre=d["nombre"], codigo=d["codigo"],
        docstring=d.get("docstring"), linea_inicio=1,
        linea_fin=d.get("lineas", 1), num_ramas=d.get("num_ramas", 0),
    )


def _tokens(metrics) -> tuple[int, int]:
    """Extrae (tokens_entrada, tokens_salida) de crew.usage_metrics, robusto a versiones."""
    entrada = getattr(metrics, "prompt_tokens", 0) or 0
    salida = getattr(metrics, "completion_tokens", 0) or 0
    return int(entrada), int(salida)


def main():
    limite = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))[:limite]

    # OJO: crew.usage_metrics es ACUMULATIVO en el proceso (suma todas las
    # preguntas anteriores), no por-crew. Por eso el total real es la última
    # lectura, y el consumo de cada pregunta es la diferencia con la anterior.
    prev_ent = prev_sal = 0
    tot_entrada = tot_salida = 0
    tiempos = []
    medidas = 0

    for i, item in enumerate(corpus, start=1):
        tipo = TIPOS[(i - 1) % len(TIPOS)]
        print(f"[{i}/{len(corpus)}] {item['nombre']} [{tipo.value}, {item['lenguaje']}] ...", end=" ")
        unidad = unidad_desde_dict(item)
        t0 = time.time()
        try:
            crew = construir_crew_para_unidad(unidad, CONTEXTO, tipo)
            crew.kickoff()
            cum_ent, cum_sal = _tokens(crew.usage_metrics)   # acumulado del proceso
            ent, sal = cum_ent - prev_ent, cum_sal - prev_sal  # consumo de ESTA pregunta
            prev_ent, prev_sal = cum_ent, cum_sal
            tot_entrada, tot_salida = cum_ent, cum_sal          # el total es el acumulado
            tiempos.append(time.time() - t0)
            medidas += 1
            print(f"entrada={ent}  salida={sal}  ({tiempos[-1]:.0f}s)")
        except Exception as e:
            print(f"ERROR: {e}")

    if not medidas:
        print("No se pudo medir ninguna pregunta.")
        return

    ent_media = tot_entrada / medidas
    sal_media = tot_salida / medidas
    coste_usd = (tot_entrada / 1e6 * PRECIO_ENTRADA) + (tot_salida / 1e6 * PRECIO_SALIDA)
    coste_pregunta_usd = coste_usd / medidas
    coste_pregunta_eur = coste_pregunta_usd * USD_A_EUR
    seg_media = sum(tiempos) / len(tiempos)

    print("\n" + "=" * 60)
    print(f"Preguntas medidas: {medidas}")
    print(f"Tokens por pregunta (gen+revisor):  entrada {ent_media:.0f}  |  salida {sal_media:.0f}")
    print(f"Tiempo medio por pregunta: {seg_media:.1f} s")
    print("-" * 60)
    print(f"Coste por PREGUNTA:  {coste_pregunta_usd*100:.3f} ¢USD   (~{coste_pregunta_eur*100:.3f} ¢EUR)")
    print(f"Coste examen de  8 preguntas:  {coste_pregunta_usd*8:.4f} $   (~{coste_pregunta_eur*8:.4f} €)")
    print(f"Coste examen de 15 preguntas:  {coste_pregunta_usd*15:.4f} $   (~{coste_pregunta_eur*15:.4f} €)")
    print(f"Coste 100 alumnos x 10 preg.:  {coste_pregunta_usd*1000:.2f} $   (~{coste_pregunta_eur*1000:.2f} €)")
    print("=" * 60)
    print(f"(Precio Haiku 4.5: {PRECIO_ENTRADA} $/M entrada, {PRECIO_SALIDA} $/M salida; "
          f"tipo de cambio usado: {USD_A_EUR} €/$)")


if __name__ == "__main__":
    main()
