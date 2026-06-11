"""Archivo Python de ejemplo para probar el parser y el pipeline.

Contiene varias funciones y una clase pequeña con distintos niveles de
complejidad. Sirve para validar que el parser extrae bien las unidades
y que el pipeline genera preguntas distintas sobre cada una.
"""


def saludar(nombre: str) -> str:
    """Devuelve un saludo personalizado."""
    return f"Hola, {nombre}!"


def factorial(n: int) -> int:
    """Calcula el factorial de n de forma recursiva."""
    if n == 0:
        return 1
    return n * factorial(n - 1)


def es_primo(n: int) -> bool:
    """Indica si n es un número primo."""
    if n < 2:
        return False
    for i in range(2, int(n**0.5) + 1):
        if n % i == 0:
            return False
    return True


class Pila:
    """Pila (LIFO) implementada sobre una lista."""

    def __init__(self) -> None:
        self._items: list = []

    def apilar(self, item) -> None:
        """Añade un elemento en la cima de la pila."""
        self._items.append(item)

    def desapilar(self):
        """Quita y devuelve el elemento de la cima de la pila."""
        if not self._items:
            raise IndexError("La pila está vacía")
        return self._items.pop()

    def cima(self):
        """Devuelve el elemento de la cima sin quitarlo."""
        if not self._items:
            raise IndexError("La pila está vacía")
        return self._items[-1]

    def __len__(self) -> int:
        return len(self._items)
