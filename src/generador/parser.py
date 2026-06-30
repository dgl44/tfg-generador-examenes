"""Parser de código fuente basado en tree-sitter.

Extrae funciones y clases de nivel superior de archivos de código fuente.
La interfaz pública (UnidadCodigo, extraer_unidades) es independiente del
lenguaje; añadir soporte para un nuevo lenguaje solo requiere registrar
un nuevo backend en _BACKENDS.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import tree_sitter_java as tsjava
import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser


_TIPOS_RAMA = {
    "if_statement", "for_statement", "while_statement",
    "try_statement", "with_statement",
}

_TIPOS_RAMA_JAVA = {
    "if_statement", "for_statement", "enhanced_for_statement",
    "while_statement", "do_statement", "try_statement",
    "catch_clause", "switch_expression", "switch_statement",
}


def _contar_ramas(nodo: Node, tipos: set[str] = _TIPOS_RAMA) -> int:
    """Cuenta recursivamente los nodos de control de flujo en un subárbol."""
    total = 1 if nodo.type in tipos else 0
    for child in nodo.children:
        total += _contar_ramas(child, tipos)
    return total


@dataclass
class UnidadCodigo:
    """Una función o clase extraída de un archivo de código fuente."""

    tipo: str          # "funcion" | "clase" | "metodo"
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


# Una clase con más líneas que este umbral se considera demasiado grande para
# evaluarla como un todo: en su lugar se extraen sus métodos individualmente.
_MAX_LINEAS_CLASE_ENTERA = 40


def _nombre(nodo: Node, fuente: bytes) -> str:
    return _texto(nodo.child_by_field_name("name"), fuente)


def _definicion_py(
    nodo: Node, fuente: bytes, tipo: str, prefijo: str = ""
) -> UnidadCodigo:
    nombre = _nombre(nodo, fuente)
    return UnidadCodigo(
        tipo=tipo,
        nombre=f"{prefijo}{nombre}" if prefijo else nombre,
        codigo=_texto(nodo, fuente),
        docstring=_extraer_docstring_py(nodo, fuente),
        linea_inicio=nodo.start_point[0] + 1,
        linea_fin=nodo.end_point[0] + 1,
        num_ramas=_contar_ramas(nodo),
    )


def _desenvolver(nodo: Node) -> Node:
    """Devuelve la definición interna si el nodo lleva decoradores."""
    if nodo.type == "decorated_definition":
        inner = nodo.child_by_field_name("definition")
        return inner if inner is not None else nodo
    return nodo


def _es_dunder(nombre: str) -> bool:
    return nombre.startswith("__") and nombre.endswith("__")


def _extraer_clase(nodo: Node, fuente: bytes, unidades: list[UnidadCodigo]) -> None:
    """Añade una clase como unidad si es pequeña; si es grande, sus métodos.

    Una clase pequeña y cohesionada se evalúa como un todo; una clase extensa
    se descompone en sus métodos con lógica, que llevan el nombre `Clase.metodo`
    para conservar el contexto. Los métodos especiales (dunder) se omiten.
    """
    lineas = nodo.end_point[0] - nodo.start_point[0] + 1
    if lineas <= _MAX_LINEAS_CLASE_ENTERA:
        unidades.append(_definicion_py(nodo, fuente, "clase"))
        return

    nombre_clase = _nombre(nodo, fuente)
    body = nodo.child_by_field_name("body")
    if body is None:
        return
    for hijo in body.children:
        metodo = _desenvolver(hijo)
        if metodo.type != "function_definition":
            continue
        if _es_dunder(_nombre(metodo, fuente)):
            continue
        unidades.append(
            _definicion_py(metodo, fuente, "metodo", prefijo=f"{nombre_clase}.")
        )


def _extraer_python(ruta: Path) -> list[UnidadCodigo]:
    fuente = ruta.read_bytes()
    tree = _PY_PARSER.parse(fuente)
    unidades: list[UnidadCodigo] = []

    for nodo in tree.root_node.children:
        # Funciones y clases de nivel superior, lleven o no decoradores.
        definicion = _desenvolver(nodo)
        if definicion.type == "function_definition":
            unidades.append(_definicion_py(definicion, fuente, "funcion"))
        elif definicion.type == "class_definition":
            _extraer_clase(definicion, fuente, unidades)

    return unidades


# ---------------------------------------------------------------------------
# Backend: Java
# ---------------------------------------------------------------------------

_JAVA_LANGUAGE = Language(tsjava.language())
_JAVA_PARSER = Parser(_JAVA_LANGUAGE)


def _javadoc_java(nodo: Node, fuente: bytes) -> str | None:
    """Extrae el Javadoc (bloque /** */) que precede a la declaración, si existe."""
    previo = nodo.prev_named_sibling
    if previo is None or previo.type != "block_comment":
        return None
    crudo = _texto(previo, fuente)
    if not crudo.startswith("/**"):
        return None
    cuerpo = crudo.removeprefix("/**").removesuffix("*/")
    lineas = [ln.strip().lstrip("*").strip() for ln in cuerpo.splitlines()]
    return "\n".join(ln for ln in lineas if ln).strip() or None


def _definicion_java(
    nodo: Node, fuente: bytes, tipo: str, prefijo: str = ""
) -> UnidadCodigo:
    nombre = _nombre(nodo, fuente)
    return UnidadCodigo(
        tipo=tipo,
        nombre=f"{prefijo}{nombre}" if prefijo else nombre,
        codigo=_texto(nodo, fuente),
        docstring=_javadoc_java(nodo, fuente),
        linea_inicio=nodo.start_point[0] + 1,
        linea_fin=nodo.end_point[0] + 1,
        num_ramas=_contar_ramas(nodo, _TIPOS_RAMA_JAVA),
    )


def _extraer_tipo_java(nodo: Node, fuente: bytes, unidades: list[UnidadCodigo]) -> None:
    """Añade una clase/interfaz pequeña entera; si es grande, sus métodos.

    Mismo criterio que en Python: una clase pequeña se evalúa como un todo y una
    extensa se descompone en sus métodos (nombrados `Clase.metodo`). En Java no
    hay métodos especiales tipo dunder; los accesores triviales los descarta el
    filtro posterior.
    """
    lineas = nodo.end_point[0] - nodo.start_point[0] + 1
    if lineas <= _MAX_LINEAS_CLASE_ENTERA:
        unidades.append(_definicion_java(nodo, fuente, "clase"))
        return

    nombre_tipo = _nombre(nodo, fuente)
    body = nodo.child_by_field_name("body")
    if body is None:
        return
    for hijo in body.children:
        if hijo.type == "method_declaration":
            unidades.append(
                _definicion_java(hijo, fuente, "metodo", prefijo=f"{nombre_tipo}.")
            )


def _extraer_java(ruta: Path) -> list[UnidadCodigo]:
    fuente = ruta.read_bytes()
    tree = _JAVA_PARSER.parse(fuente)
    unidades: list[UnidadCodigo] = []

    for nodo in tree.root_node.children:
        if nodo.type in ("class_declaration", "interface_declaration"):
            _extraer_tipo_java(nodo, fuente, unidades)

    return unidades


# ---------------------------------------------------------------------------
# Registro de backends — añadir soporte para un nuevo lenguaje aquí
# ---------------------------------------------------------------------------
#
# Cada backend es una función Path -> list[UnidadCodigo]. Añadir un lenguaje se
# reduce a implementar su _extraer_X siguiendo el mismo patrón y registrarlo aquí.

BackendFn = Callable[[Path], list[UnidadCodigo]]

_BACKENDS: dict[str, BackendFn] = {
    ".py": _extraer_python,
    ".java": _extraer_java,
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
