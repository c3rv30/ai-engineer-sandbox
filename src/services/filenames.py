"""Tratamiento del nombre de archivo que envía el cliente en la ingesta (SEC-04).

Fuera de src/api/routers/ingest.py para poder comprobarlo sin importar el motor de
ingesta, que carga modelos y clientes al importarse (BUG-07).
"""
import os


def source_name(filename: str) -> str:
    """Nombre con el que se registra el origen de un documento subido.

    El nombre lo controla el cliente: se reduce a su último componente, tanto con
    separadores '/' como '\\', para que ningún '../' ni ruta absoluta llegue a los
    metadatos. Nunca se usa como ruta en disco.
    """
    return os.path.basename(filename.replace("\\", "/"))
