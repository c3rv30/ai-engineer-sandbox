from typing import List, Dict, Optional

# Ventana de turnos que se envía al LLM. Acota el coste en tokens: el historial
# completo de una conversación larga inflaría cada prompt sin aportar contexto
# útil para resolver una correferencia, que casi siempre apunta al turno previo.
DEFAULT_WINDOW = 4


def format_history(history: Optional[List[Dict[str, str]]], max_turns: int = DEFAULT_WINDOW) -> str:
    """Formatea los últimos turnos de la conversación como bloque para un prompt.

    Devuelve cadena vacía si no hay nada utilizable, para que el prompt no
    contenga un encabezado de historial sin contenido debajo.

    El historial lo envía el cliente, así que un turno sin 'role'/'content' —o
    que ni siquiera sea un diccionario— se descarta en lugar de tumbar la
    petición entera con un KeyError.
    """
    if not history:
        return ""

    lineas = []
    for msg in history[-max_turns:]:
        if not isinstance(msg, dict):
            continue
        role, content = msg.get("role"), msg.get("content")
        if role and content:
            lineas.append(f"- {role.upper()}: {content}")

    if not lineas:
        return ""

    return "Historial reciente de la conversación:\n" + "\n".join(lineas) + "\n"
