"""
Outil de géocodage utilisant l'API Open-Meteo Geocoding.
"""
import requests
from typing import Optional, Dict


def geocode(city: str) -> Optional[Dict[str, any]]:
    """
    Géocode une ville pour obtenir ses coordonnées.

    Args:
        city: Nom de la ville (ex: "Paris", "Tokyo")

    Returns:
        Dict avec {name, country, lat, lon} ou None si non trouvé
    """
    try:
        # API Open-Meteo Geocoding
        url = "https://geocoding-api.open-meteo.com/v1/search"
        params = {
            "name": city,
            "count": 1,  # Prendre le meilleur résultat
            "language": "fr",
            "format": "json"
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()

        if not data.get("results"):
            return None

        result = data["results"][0]

        return {
            "name": result.get("name"),
            "country": result.get("country"),
            "lat": result.get("latitude"),
            "lon": result.get("longitude"),
            "admin1": result.get("admin1", ""),  # Région/État
        }

    except requests.RequestException as e:
        print(f"Erreur géocodage: {e}")
        return None


if __name__ == "__main__":
    # Test
    result = geocode("Paris")
    print(f"Paris: {result}")

    result = geocode("Tokyo")
    print(f"Tokyo: {result}")

    result = geocode("VilleInexistante123")
    print(f"Ville inexistante: {result}")
