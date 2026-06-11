"""Parser AST de archivos Python.

Extrae las funciones y clases de nivel superior de un archivo `.py`,
junto con su código fuente, su docstring y sus números de línea.

Usa el módulo `ast` built-in de Python, sin dependencias externas.
"""

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass
class UnidadCodigo:
    """Una función o clase extraída de un archivo Python."""

    tipo: str  # "funcion" | "clase"
    nombre: str
    codigo: str
    docstring: str | None
    linea_inicio: int
    linea_fin: int

    def __str__(self) -> str:
        return f"{self.tipo} '{self.nombre}' (líneas {self.linea_inicio}-{self.linea_fin})"


def extraer_unidades(ruta_archivo: str | Path) -> list[UnidadCodigo]:
    """Extrae las funciones y clases de nivel superior del archivo dado.

    Solo considera definiciones de nivel superior. Los métodos dentro de
    una clase se incluyen como parte del código de esa clase, no como
    unidades independientes.
    """
    ruta = Path(ruta_archivo)
    codigo_fuente = ruta.read_text(encoding="utf-8")

    arbol = ast.parse(codigo_fuente, filename=str(ruta))
    lineas = codigo_fuente.splitlines(keepends=True)

    unidades: list[UnidadCodigo] = []

    for nodo in arbol.body:
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            tipo = "clase" if isinstance(nodo, ast.ClassDef) else "funcion"
            inicio = nodo.lineno
            fin = nodo.end_lineno or inicio
            codigo_unidad = "".join(lineas[inicio - 1 : fin])

            unidades.append(
                UnidadCodigo(
                    tipo=tipo,
                    nombre=nodo.name,
                    codigo=codigo_unidad,
                    docstring=ast.get_docstring(nodo),
                    linea_inicio=inicio,
                    linea_fin=fin,
                )
            )

    return unidades


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Uso: python -m generador.parser <ruta_archivo.py>")
        sys.exit(1)

    ruta = sys.argv[1]
    unidades = extraer_unidades(ruta)

    print(f"Encontradas {len(unidades)} unidades en {ruta}:\n")
    for u in unidades:
        print(f"  - {u}")
        if u.docstring:
            primera_linea = u.docstring.splitlines()[0]
            print(f"      docstring: {primera_linea}")
        print()
