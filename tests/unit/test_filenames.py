"""Regresión del nombre de archivo en la ingesta (SEC-04).

El nombre lo controla el cliente. Con '../' se escribía, y el finally borraba, fuera
del directorio temporal; ahora solo se conserva su último componente como metadato.
"""
import pytest

from src.services.filenames import source_name


@pytest.mark.parametrize("enviado, esperado", [
    ("cv.pdf", "cv.pdf"),
    ("../../etc/passwd.txt", "passwd.txt"),
    ("/var/folders/v2/T/cv.txt", "cv.txt"),
    ("..\\..\\Windows\\win.ini.md", "win.ini.md"),
    ("carpeta/sub\\mixto/../informe.pdf", "informe.pdf"),
    ("nombre con espacios.md", "nombre con espacios.md"),
])
def test_solo_el_ultimo_componente(enviado, esperado):
    assert source_name(enviado) == esperado


@pytest.mark.parametrize("enviado", ["../../etc/passwd.txt", "..\\secreto.txt", "/abs/ruta.md", "a/../b.pdf"])
def test_sin_separadores_ni_componentes_de_ruta(enviado):
    resultado = source_name(enviado)
    assert "/" not in resultado and "\\" not in resultado and resultado not in ("..", ".")
