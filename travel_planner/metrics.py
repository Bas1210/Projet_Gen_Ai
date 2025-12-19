"""
Utilitaires pour l'analyse et le calcul de statistiques d'itinéraire.
"""
from typing import Dict, List, Any
import re


def calculate_itinerary_stats(itinerary: Dict[str, Any], weather: List[Dict]) -> Dict[str, Any]:
    """
    Calcule les statistiques d'un itinéraire.

    Args:
        itinerary: Itinéraire généré
        weather: Données météo

    Returns:
        Dict avec statistiques {
            "total_cost_min": float,
            "total_cost_max": float,
            "indoor_ratio": float (0-1),
            "outdoor_ratio": float (0-1),
            "total_activities": int,
            "weather_adaptation_score": int (0-100)
        }
    """
    daily_plans = itinerary.get("daily_plans", [])

    if not daily_plans:
        return {
            "total_cost_min": 0,
            "total_cost_max": 0,
            "indoor_ratio": 0,
            "outdoor_ratio": 0,
            "total_activities": 0,
            "weather_adaptation_score": 0
        }

    # Calculer coûts
    total_min, total_max = 0, 0
    indoor_count, outdoor_count = 0, 0
    total_activities = 0

    for day in daily_plans:
        for period in ["morning", "afternoon", "evening"]:
            if period in day:
                activity = day[period]
                total_activities += 1

                # Parser coût (ex: "15-20€", "Gratuit", "30€")
                cost_str = activity.get("cost_estimate", "0")
                min_cost, max_cost = parse_cost(cost_str)
                total_min += min_cost
                total_max += max_cost

                # Compter indoor/outdoor
                if activity.get("indoor"):
                    indoor_count += 1
                else:
                    outdoor_count += 1

    # Calculer ratios
    total = indoor_count + outdoor_count
    indoor_ratio = indoor_count / total if total > 0 else 0
    outdoor_ratio = outdoor_count / total if total > 0 else 0

    # Calculer score d'adaptation météo
    weather_score = calculate_weather_adaptation_score(daily_plans, weather)

    return {
        "total_cost_min": total_min,
        "total_cost_max": total_max,
        "indoor_ratio": indoor_ratio,
        "outdoor_ratio": outdoor_ratio,
        "total_activities": total_activities,
        "weather_adaptation_score": weather_score
    }


def parse_cost(cost_str: str) -> tuple:
    """
    Parse une chaîne de coût (ex: "15-20€", "Gratuit", "30€").

    Returns:
        (min, max) en euros
    """
    cost_str = cost_str.lower().strip()

    # Gratuit
    if "gratuit" in cost_str or "free" in cost_str:
        return (0, 0)

    # Extraire les nombres
    numbers = re.findall(r'\d+', cost_str)

    if not numbers:
        return (0, 0)

    if len(numbers) == 1:
        # Format "30€" -> (30, 30)
        val = int(numbers[0])
        return (val, val)
    else:
        # Format "15-20€" -> (15, 20)
        return (int(numbers[0]), int(numbers[1]))


def calculate_weather_adaptation_score(daily_plans: List[Dict], weather: List[Dict]) -> int:
    """
    Calcule un score d'adaptation météo (0-100).

    Logique:
    - Si pluie forte (>70%) et activité outdoor -> -20 points
    - Si pluie modérée (40-70%) et activité outdoor -> -10 points
    - Si temps sec et activité outdoor -> +10 points
    - Si indoor quand pluie -> +10 points
    """
    if not weather or not daily_plans:
        return 0

    score = 100
    penalties = 0
    bonuses = 0

    # Créer un dict date -> météo
    weather_by_date = {w["date"]: w for w in weather}

    for day in daily_plans:
        day_date = day.get("date")
        day_weather = weather_by_date.get(day_date)

        if not day_weather:
            continue

        precip_prob = day_weather.get("precipitation_probability", 0)

        for period in ["morning", "afternoon", "evening"]:
            if period not in day:
                continue

            activity = day[period]
            is_indoor = activity.get("indoor", False)

            # Logique de scoring
            if precip_prob > 70:  # Pluie forte
                if not is_indoor:
                    penalties += 20  # Outdoor sous pluie forte
                else:
                    bonuses += 10  # Indoor quand pluie forte (bon choix)
            elif precip_prob > 40:  # Pluie modérée
                if not is_indoor:
                    penalties += 10
                else:
                    bonuses += 5
            else:  # Temps sec
                if not is_indoor:
                    bonuses += 5  # Outdoor par beau temps

    final_score = max(0, min(100, score - penalties + bonuses))
    return int(final_score)


def calculate_quality_score(itinerary: Dict, weather: List[Dict], budget: str, pace: str) -> Dict[str, Any]:
    """
    Calcule un score de qualité global avec détails.

    Returns:
        {
            "overall_score": int (0-100),
            "checks": {
                "budget_ok": bool,
                "weather_adapted": bool,
                "alternatives_present": bool,
                "pace_respected": bool
            },
            "details": [str]  # Liste de messages explicatifs
        }
    """
    score = 100
    checks = {
        "budget_ok": True,
        "weather_adapted": True,
        "alternatives_present": True,
        "pace_respected": True
    }
    details = []

    daily_plans = itinerary.get("daily_plans", [])

    if not daily_plans:
        return {"overall_score": 0, "checks": checks, "details": ["Aucun itinéraire généré"]}

    # 1. Vérifier budget
    stats = calculate_itinerary_stats(itinerary, weather)
    avg_cost_per_day = (stats["total_cost_min"] + stats["total_cost_max"]) / 2 / len(daily_plans)

    budget_limits = {"faible": 50, "moyen": 150, "élevé": 500}
    budget_limit = budget_limits.get(budget, 150)

    if avg_cost_per_day > budget_limit:
        score -= 20
        checks["budget_ok"] = False
        details.append(f"⚠️ Coût moyen {avg_cost_per_day:.0f}€/jour dépasse budget {budget} ({budget_limit}€/jour)")
    else:
        details.append(f"✅ Budget respecté ({avg_cost_per_day:.0f}€/jour < {budget_limit}€/jour)")

    # 2. Vérifier adaptation météo
    weather_score = stats["weather_adaptation_score"]
    if weather_score < 60:
        score -= 20
        checks["weather_adapted"] = False
        details.append(f"⚠️ Score d'adaptation météo faible ({weather_score}/100)")
    else:
        details.append(f"✅ Bien adapté à la météo ({weather_score}/100)")

    # 3. Vérifier présence d'alternatives
    days_with_alternatives = sum(1 for day in daily_plans if day.get("alternatives"))
    if days_with_alternatives < len(daily_plans) * 0.5:
        score -= 15
        checks["alternatives_present"] = False
        details.append(f"⚠️ Peu d'alternatives ({days_with_alternatives}/{len(daily_plans)} jours)")
    else:
        details.append(f"✅ Alternatives présentes ({days_with_alternatives}/{len(daily_plans)} jours)")

    # 4. Vérifier rythme
    activities_per_day = stats["total_activities"] / len(daily_plans)

    pace_limits = {"calme": 2.5, "normal": 3.5, "intense": 5}
    expected_activities = pace_limits.get(pace, 3)

    if abs(activities_per_day - expected_activities) > 1:
        score -= 15
        checks["pace_respected"] = False
        details.append(f"⚠️ Rythme {pace} non respecté ({activities_per_day:.1f} activités/jour)")
    else:
        details.append(f"✅ Rythme {pace} respecté ({activities_per_day:.1f} activités/jour)")

    return {
        "overall_score": max(0, min(100, score)),
        "checks": checks,
        "details": details
    }
