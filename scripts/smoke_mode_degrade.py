"""
Test rapide du mode dégradé (sans météo).
"""
from travel_planner.agent.runner import TravelPlannerAgent


def test_mode_degrade():
    """Test avec dates lointaines (météo indisponible)."""
    print("🧪 TEST MODE DÉGRADÉ (sans météo)\n")
    print("Dates lointaines : 2025-12-23 → 2026-01-05")
    print("L'agent devrait détecter l'échec météo et continuer avec PLAN\n")
    print("=" * 60)

    agent = TravelPlannerAgent()

    result = agent.plan_trip(
        destination="Paris",
        start_date="2025-12-23",
        end_date="2026-01-05",
        profile="couple",
        budget="moyen",
        interests=["musées", "gastronomie"],
        pace="calme"
    )

    # Afficher les logs
    print("\n📋 LOGS:\n")
    for log in result["logs"]:
        print(log)

    # Résultat
    print("\n" + "=" * 60)
    print(f"\n✅ Succès: {result['success']}")
    print(f"📅 Itinéraire généré: {len(result.get('itinerary', {}).get('daily_plans', []))} jours")
    print(f"🌤️  Météo disponible: {len(result.get('weather', []))} jours")
    print(f"⚠️  Mode dégradé: {'OUI' if result.get('success') and len(result.get('weather', [])) == 0 else 'NON'}")

    if not result['success']:
        print(f"\n❌ ERREUR: {result.get('error')}")
        print("\n⚠️  L'agent n'a pas réussi à générer l'itinéraire")
    else:
        print("\n✅ SUCCESS! L'agent a généré l'itinéraire malgré l'absence de météo")

    return result['success']


if __name__ == "__main__":
    import sys

    success = test_mode_degrade()

    sys.exit(0 if success else 1)
