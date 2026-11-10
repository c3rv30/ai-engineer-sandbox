import requests
from datetime import datetime

def get_current_time(*args, **kwargs) -> str:
    """Returns the system's current date and time."""
    now = datetime.now()
    return f"The current date and time is: {now.strftime('%Y-%m-%d %H:%M:%S')}"

def get_crypto_price(symbol: str = "bitcoin", *args, **kwargs) -> str:
    """
    Gets the current price of a cryptocurrency from CoinGecko.
    Example symbols: 'bitcoin', 'ethereum', 'solana'.
    """
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={symbol.lower()}&vs_currencies=usd"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if symbol.lower() in data:
                price = data[symbol.lower()]['usd']
                return f"The current price of {symbol.capitalize()} is ${price} USD."
        return f"Could not get the price for '{symbol}'."
    except Exception as e:
        return f"Error querying the cryptocurrency API: {e}"

def get_github_profile(username: str, *args, **kwargs) -> str:
    """
    Gets the public bio and repository count of a GitHub user.
    """
    url = f"https://api.github.com/users/{username}"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            bio = data.get("bio", "No bio")
            repos = data.get("public_repos", 0)
            followers = data.get("followers", 0)
            return f"GitHub profile of {username}: Bio: '{bio}'. Public repositories: {repos}. Followers: {followers}."
        return f"GitHub profile '{username}' not found."
    except Exception as e:
        return f"Error querying GitHub: {e}"

# Map of the tools available to run by name
TOOLS_REGISTRY = {
    "get_current_time": get_current_time,
    "get_crypto_price": get_crypto_price,
    "get_github_profile": get_github_profile
}
