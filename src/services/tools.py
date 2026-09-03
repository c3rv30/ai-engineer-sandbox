import requests
from datetime import datetime

def get_current_time(*args, **kwargs) -> str:
    """Retorna la fecha y hora actual del sistema."""
    now = datetime.now()
    return f"La fecha y hora actual es: {now.strftime('%Y-%m-%d %H:%M:%S')}"

def get_crypto_price(symbol: str = "bitcoin", *args, **kwargs) -> str:
    """
    Obtiene el precio actual de una criptomoneda usando CoinGecko.
    Ejemplo de symbol: 'bitcoin', 'ethereum', 'solana'.
    """
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={symbol.lower()}&vs_currencies=usd"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if symbol.lower() in data:
                price = data[symbol.lower()]['usd']
                return f"El precio actual de {symbol.capitalize()} es ${price} USD."
        return f"No se pudo obtener el precio para '{symbol}'."
    except Exception as e:
        return f"Error al consultar la API de criptomonedas: {e}"

def get_github_profile(username: str, *args, **kwargs) -> str:
    """
    Obtiene la biografía pública y cantidad de repos de un usuario en GitHub.
    """
    url = f"https://api.github.com/users/{username}"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            bio = data.get("bio", "Sin biografía")
            repos = data.get("public_repos", 0)
            followers = data.get("followers", 0)
            return f"Perfil GitHub de {username}: Bio: '{bio}'. Repositorios públicos: {repos}. Seguidores: {followers}."
        return f"No se encontró el perfil de GitHub '{username}'."
    except Exception as e:
        return f"Error consultando GitHub: {e}"

# Mapa de herramientas disponibles para ejecutar por nombre
TOOLS_REGISTRY = {
    "get_current_time": get_current_time,
    "get_crypto_price": get_crypto_price,
    "get_github_profile": get_github_profile
}
