"""Parser de código fuente basado en tree-sitter.

Extrae funciones y clases de nivel superior de archivos de código fuente.
La interfaz pública (UnidadCodigo, extraer_unidades) es independiente del
lenguaje; añadir soporte para un nuevo lenguaje solo requiere registrar
un nuevo backend en _BACKENDS.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser


_TIPOS_RAMA = {
    "if_statement", "for_statement", "while_statement",
    "try_statement", "with_statement",
}


def _contar_ramas(nodo: Node) -> int:
    """Cuenta recursivamente los nodos de control de flujo en un subárbol."""
    total = 1 if nodo.type in _TIPOS_RAMA else 0
    for child in nodo.children:
        total += _contar_ramas(child)
    return total


@dataclass
class UnidadCodigo:
    """Una función o clase extraída de un archivo de código fuente."""

    tipo: str          # "funcion" | "clase"
    nombre: str
    codigo: str        # Código fuente completo de la unidad
    docstring: str | None
    linea_inicio: int  # 1-indexed
    linea_fin: int     # 1-indexed
    num_ramas: int = 0  # Nodos de control de flujo (if/for/while/try/with)

    def es_trivial(self, min_ramas: int = 1, min_lineas: int = 5) -> bool:
        """Devuelve True si la unidad es demasiado simple para generar preguntas útiles."""
        lineas = self.linea_fin - self.linea_inicio + 1
        return self.num_ramas < min_ramas and lineas < min_lineas

    def __str__(self) -> str:
        return f"{self.tipo} '{self.nombre}' (líneas {self.linea_inicio}-{self.linea_fin})"


# ---------------------------------------------------------------------------
# Backend: Python
# ---------------------------------------------------------------------------

_PY_LANGUAGE = Language(tspython.language())
_PY_PARSER = Parser(_PY_LANGUAGE)


def _texto(nodo: Node, fuente: bytes) -> str:
    return fuente[nodo.start_byte:nodo.end_byte].decode()


def _extraer_docstring_py(nodo: Node, fuente: bytes) -> str | None:
    """Extrae el docstring del cuerpo de una función o clase, si existe."""
    body = nodo.child_by_field_name("body")
    if body is None:
        return None
    for child in body.children:
        if child.type == "expression_statement":
            for expr in child.children:
                if expr.type == "string":
                    raw = _texto(expr, fuente)
                    for q in ('"""', "'''", '"', "'"):
                        if raw.startswith(q) and raw.endswith(q):
                            return raw[len(q):-len(q)].strip()
            break
        elif child.type not in ("newline", "comment", "indent"):
            break
    return None


def _definicion_py(nodo: Node, fuente: bytes, tipo: str) -> UnidadCodigo:
    nombre_nodo = nodo.child_by_field_name("name")
    return UnidadCodigo(
        tipo=tipo,
        nombre=_texto(nombre_nodo, fuente),
        codigo=_texto(nodo, fuente),
        docstring=_extraer_docstring_py(nodo, fuente),
        linea_inicio=nodo.start_point[0] + 1,
        linea_fin=nodo.end_point[0] + 1,
        num_ramas=_contar_ramas(nodo),
    )


def _extraer_python(ruta: Path) -> list[UnidadCodigo]:
    fuente = ruta.read_bytes()
    tree = _PY_PARSER.parse(fuente)
    unidades: list[UnidadCodigo] = []

    for nodo in tree.root_node.children:
        if nodo.type == "function_definition":
            unidades.append(_definicion_py(nodo, fuente, "funcion"))
        elif nodo.type == "class_definition":
            unidades.append(_definicion_py(nodo, fuente, "clase"))
        elif nodo.type == "decorated_definition":
            # Función o clase con decoradores (@dataclass, @staticmethod, etc.)
            inner = nodo.child_by_field_name("definition")
            if inner is not None:
                if inner.type == "function_definition":
                    unidades.append(_definicion_py(inner, fuente, "funcion"))
                elif inner.type == "class_definition":
                    unidades.append(_definicion_py(inner, fuente, "clase"))

    return unidades


# ---------------------------------------------------------------------------
# Registro de backends — añadir soporte para un nuevo lenguaje aquí
# ---------------------------------------------------------------------------
#
# Cada backend es una función Path -> list[UnidadCodigo].
# Para añadir Java, por ejemplo:
#   1. pip install tree-sitter-java
#   2. Implementar _extraer_java(ruta) siguiendo el mismo patrón
#   3. Registrar: ".java": _extraer_java

BackendFn = Callable[[Path], list[UnidadCodigo]]

_BACKENDS: dict[str, BackendFn] = {
    ".py": _extraer_python,
    # ".java": _extraer_java,
    # ".cpp": _extraer_cpp,
    # ".js": _extraer_javascript,
}


def lenguajes_soportados() -> list[str]:
    """Devuelve las extensiones de archivo soportadas actualmente."""
    return list(_BACKENDS)


def extraer_unidades(ruta: str | Path) -> list[UnidadCodigo]:
    """Extrae funciones y clases de nivel superior del archivo dado.

    Delega en el backend correspondiente según la extensión del archivo.
    Lanza ValueError si la extensión no está soportada.
    """
    ruta = Path(ruta)
    backend = _BACKENDS.get(ruta.suffix)
    if backend is None:
        raise ValueError(
            f"Extensión {ruta.suffix!r} no soportada. "
            f"Soportadas: {lenguajes_soportados()}"
        )
    return backend(ruta)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Uso: python -m generador.parser <ruta_archivo>")
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
