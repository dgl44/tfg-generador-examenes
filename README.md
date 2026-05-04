# tfg-generador-examenes

Herramienta web para la generación automática de exámenes a partir de
repositorios de código fuente, mediante un sistema multi-agente con LLMs.

Trabajo Fin de Grado — Ingeniería Informática, Universidad de Alicante
(defensa Julio 2026).

## Requisitos

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) como gestor de dependencias
- Cuenta AWS con acceso a Bedrock (modelos Claude habilitados)

## Instalación

```bash
uv sync
```

## Configuración

Copia `.env.example` a `.env` y rellena tus credenciales AWS:

```bash
copy .env.example .env
```

## Ejecución

Prueba inicial de conexión con Bedrock:

```bash
uv run python src/generador/prueba_bedrock.py
```
