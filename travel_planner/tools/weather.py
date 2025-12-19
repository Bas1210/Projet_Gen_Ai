"""
Outil météo utilisant l'API Open-Meteo Forecast.
"""
import requests
from typing import List, Dict
from datetime import datetime


def get_weather(lat: float, lon: float, start_date: str, end_date: str) -> List[Dict]:
    """
    Récupère les prévisions météo pour une période.

    Args:
        lat: Latitude
        lon: Longitude
        start_date: Date de début (YYYY-MM-DD)
        end_date: Date de fin (YYYY-MM-DD)

    Returns:
        Liste de dict avec météo quotidienne:
        [{date, temp_min, temp_max, precipitation_probability, wind_speed, description}, ...]
    """
    try:
        # API Open-Meteo Forecast
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max",
            "start_date": start_date,
            "end_date": end_date,
            "timezone": "auto"
        }

        response = requests.get(url, params=params, timeout=10)

        # Vérifier le statut de la réponse
        if response.status_code != 200:
            # Erreur API (400 = dates invalides, 404, 500, etc.)
            # Retourner liste vide pour activer le mode dégradé
            return []

        data = response.json()
        daily = data.get("daily", {})

        # Parser les données
        weather_list = []
        dates = daily.get("time", [])
        temp_max = daily.get("temperature_2m_max", [])
        temp_min = daily.get("temperature_2m_min", [])
        precip_prob = daily.get("precipitation_probability_max", [])
        wind_speed = daily.get("wind_speed_10m_max", [])

        for i, date in enumerate(dates):
            t_max = temp_max[i] if i < len(temp_max) else None
            t_min = temp_min[i] if i < len(temp_min) else None
            p_prob = precip_prob[i] if i < len(precip_prob) else 0
            w_speed = wind_speed[i] if i < len(wind_speed) else 0

            # Générer description simple
            description = _generate_description(t_max, t_min, p_prob, w_speed)

            weather_list.append({
                "date": date,
                "temp_min": t_min,
                "temp_max": t_max,
                "precipitation_probability": p_prob,
                "wind_speed": w_speed,
                "description": description
            })

        return weather_list

    except requests.HTTPError as e:
        # Erreur HTTP (400, 404, 500, etc.) - dates hors limites ou paramètres invalides
        # Mode dégradé : retourner liste vide pour déclencher génération sans météo
        return []
    except requests.RequestException as e:
        # Autres erreurs réseau (timeout, connexion, etc.)
        # Mode dégradé : retourner liste vide
        return []


def _generate_description(temp_max, temp_min, precip_prob, wind_speed) -> str:
    """Génère une description textuelle simple de la météo."""
    conditions = []

    # Température
    if temp_max and temp_max > 25:
        conditions.append("Chaud")
    elif temp_max and temp_max < 10:
        conditions.append("Froid")
    else:
        conditions.append("Tempéré")

    # Précipitations
    if precip_prob and precip_prob > 70:
        conditions.append("Pluie probable")
    elif precip_prob and precip_prob > 40:
        conditions.append("Risque de pluie")
    else:
        conditions.append("Sec")

    # Vent
    if wind_speed and wind_speed > 30:
        conditions.append("Venteux")

    return " - ".join(conditions)


if __name__ == "__main__":
    # Test avec Paris (lat: 48.8566, lon: 2.3522)
    weather = get_weather(48.8566, 2.3522, "2025-01-15", "2025-01-18")
    for w in weather:
        print(f"{w['date']}: {w['temp_min']}°C - {w['temp_max']}°C | {w['description']}")
