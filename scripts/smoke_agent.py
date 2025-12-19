"""
Script de test rapide pour l'agent (sans Streamlit).
"""
import json
from travel_planner.agent.runner import TravelPlannerAgent


def test_agent_with_weather():
    """Test avec météo disponible (dates proches)."""
    print("=== TEST 1: Avec météo (dates proches) ===\n")

    agent = TravelPlannerAgent()

    result = agent.plan_trip(
        destination="Paris",
        start_date="2025-12-20",
        end_date="2025-12-22",
        profile="couple",
        budget="moyen",
        interests=["musées", "gastronomie"],
        pace="calme"
    )

    print("\n--- LOGS ---")
    print("\n".join(result["logs"]))

    print("\n--- SUCCÈS ---")
    print(f"Succès: {result['success']}")

    if result.get("itinerary"):
        print(f"Nombre de jours: {len(result['itinerary'].get('daily_plans', []))}")
        print(f"Météo disponible: {len(result.get('weather', []))} jours")


def test_agent_without_weather():
    """Test sans météo (dates très lointaines)."""
    print("\n\n=== TEST 2: Sans météo (dates lointaines - mode dégradé) ===\n")

    agent = TravelPlannerAgent()

    result = agent.plan_trip(
        destination="Tokyo",
        start_date="2026-06-01",  # Dates très lointaines
        end_date="2026-06-04",
        profile="solo",
        budget="moyen",
        interests=["culture locale", "nature"],
        pace="normal"
    )

    print("\n--- LOGS ---")
    print("\n".join(result["logs"]))

    print("\n--- SUCCÈS ---")
    print(f"Succès: {result['success']}")

    if result.get("itinerary"):
        print(f"Nombre de jours: {len(result['itinerary'].get('daily_plans', []))}")
        print(f"Météo disponible: {len(result.get('weather', []))} jours")
        print(f"Mode dégradé: {'OUI' if len(result.get('weather', [])) == 0 else 'NON'}")


if __name__ == "__main__":
    print("🧪 Test de l'agent de planification\n")
    print("⚠️  Ce test peut prendre 2-5 minutes selon votre machine...\n")

    # Test 1: Avec météo
    test_agent_with_weather()

    # Test 2: Sans météo (mode dégradé)
    # Décommentez pour tester le mode dégradé:
    # test_agent_without_weather()

    print("\n✅ Tests terminés!")
