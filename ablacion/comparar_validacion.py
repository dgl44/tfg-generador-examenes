"""Compara las etiquetas humanas (mis_respuestas.txt) con el juez automático.

Calcula el acuerdo (%) y el kappa de Cohen, y lista los desacuerdos. Sirve para
validar que el juez Sonnet es un sustituto razonable del criterio humano.
"""

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLAVE = REPO / "ablacion" / "validacion_clave.json"
RESP = REPO / "ablacion" / "mis_respuestas.txt"


def normaliza(v: str) -> str:
    v = v.strip().upper()
    if v.startswith("B"):
        return "BUENA"
    if v.startswith("D"):
        return "DEFECTUOSA"
    return ""


def main():
    clave = {c["n"]: c for c in json.loads(CLAVE.read_text(encoding="utf-8"))}
    humanas = {}
    for linea in RESP.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*(\d+)\s*=\s*(\w+)", linea)
        if m:
            lab = normaliza(m.group(2))
            if lab:
                humanas[int(m.group(1))] = lab

    pares = [(n, humanas[n], clave[n]["etiqueta_juez"]) for n in sorted(humanas) if n in clave]
    if not pares:
        print("No hay respuestas válidas en mis_respuestas.txt todavía.")
        return

    N = len(pares)
    acuerdos = sum(1 for _, h, j in pares if h == j)

    # Kappa de Cohen
    labels = ["BUENA", "DEFECTUOSA"]
    po = acuerdos / N
    pe = 0.0
    for L in labels:
        ph = sum(1 for _, h, _ in pares if h == L) / N
        pj = sum(1 for _, _, j in pares if j == L) / N
        pe += ph * pj
    kappa = (po - pe) / (1 - pe) if pe != 1 else 1.0

    print(f"Respuestas comparadas: {N}/15")
    print(f"Acuerdo humano-juez: {acuerdos}/{N} = {100*po:.0f}%")
    print(f"Kappa de Cohen: {kappa:.2f}  "
          f"({'casi perfecto' if kappa>=.81 else 'sustancial' if kappa>=.61 else 'moderado' if kappa>=.41 else 'débil'})")
    desac = [(n, h, j) for n, h, j in pares if h != j]
    if desac:
        print("\nDesacuerdos:")
        for n, h, j in desac:
            print(f"  P{n:02d} ({clave[n]['lenguaje']}, {clave[n]['nombre']}): humano={h} vs juez={j}")
    else:
        print("\nSin desacuerdos.")


if __name__ == "__main__":
    main()
