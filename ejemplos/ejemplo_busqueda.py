"""Algoritmos de búsqueda — segundo archivo de ejemplo para pruebas."""


def busqueda_binaria(lista: list, objetivo: int) -> int:
    """Busca objetivo en lista ordenada. Devuelve el índice o -1 si no existe."""
    izq, der = 0, len(lista) - 1
    while izq <= der:
        mid = (izq + der) // 2
        if lista[mid] == objetivo:
            return mid
        elif lista[mid] < objetivo:
            izq = mid + 1
        else:
            der = mid - 1
    return -1


def invertir_cadena(s: str) -> str:
    """Invierte una cadena de texto."""
    return s[::-1]


class ColaPrioridad:
    """Cola de prioridad mínima implementada sobre una lista."""

    def __init__(self):
        self._datos: list[tuple[int, any]] = []

    def insertar(self, prioridad: int, valor) -> None:
        """Inserta un elemento con su prioridad y reordena."""
        self._datos.append((prioridad, valor))
        self._datos.sort(key=lambda x: x[0])

    def extraer_minimo(self):
        """Extrae y devuelve el valor con menor prioridad."""
        if not self._datos:
            raise IndexError("Cola vacía")
        return self._datos.pop(0)[1]

    def esta_vacia(self) -> bool:
        return len(self._datos) == 0
