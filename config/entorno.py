"""
Lee un archivo .env (si existe) y pasa sus valores a variables de entorno.
En tu computador: copia .env.ejemplo como .env. En Railway no hay .env: las variables
se configuran en el panel de Railway, y las que ya existen nunca se sobrescriben.
"""
import os
from pathlib import Path


def cargar(ruta: Path):
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


def booleano(nombre, por_defecto=False):
    return os.environ.get(nombre, "1" if por_defecto else "0").strip().lower() in ("1", "true", "si", "sí", "yes")


def lista(nombre, por_defecto=""):
    return [x.strip() for x in os.environ.get(nombre, por_defecto).split(",") if x.strip()]
