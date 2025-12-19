"""
Script de test pour vérifier l'intégration Mistral AI.
"""
import os
from travel_planner.agent.llm_client import LLMClient


def test_mistral_connection():
    """Test de connexion à l'API Mistral."""
    print("=== Test de connexion Mistral AI ===\n")

    # Vérifier la clé API
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        print("❌ ERREUR: MISTRAL_API_KEY non définie")
        print("\nDéfinissez la variable d'environnement:")
        print("  export MISTRAL_API_KEY='votre_clé_api'")
        return False

    print(f"✅ Clé API trouvée: {api_key[:10]}...{api_key[-4:]}\n")

    # Créer le client
    try:
        client = LLMClient(model="mistral-large-latest", api_key=api_key)
        print("✅ Client LLM initialisé\n")
    except Exception as e:
        print(f"❌ Erreur lors de l'initialisation: {e}")
        return False

    # Test simple
    print("--- Test 1: Génération simple ---")
    try:
        response = client.generate(
            prompt="Quelle est la capitale de la France?",
            temperature=0.3,
            max_tokens=100
        )
        print(f"✅ Réponse: {response[:150]}...\n")
    except Exception as e:
        print(f"❌ Erreur: {e}\n")
        return False

    # Test JSON
    print("--- Test 2: Génération JSON ---")
    try:
        json_response = client.generate_json(
            prompt='Liste 3 villes françaises au format: {"cities": ["ville1", "ville2", "ville3"]}',
            temperature=0.3,
            max_tokens=200
        )
        print(f"✅ Réponse JSON: {json_response}\n")

        # Vérifier que c'est bien un dict
        if isinstance(json_response, dict):
            print("✅ Format JSON valide\n")
        else:
            print(f"❌ Format incorrect: {type(json_response)}\n")
            return False

    except Exception as e:
        print(f"❌ Erreur: {e}\n")
        return False

    # Test avec system prompt
    print("--- Test 3: System prompt ---")
    try:
        response = client.generate(
            prompt="Quel est ton rôle?",
            system="Tu es un assistant de voyage expert.",
            temperature=0.3,
            max_tokens=100
        )
        print(f"✅ Réponse: {response[:150]}...\n")
    except Exception as e:
        print(f"❌ Erreur: {e}\n")
        return False

    print("=" * 50)
    print("✅ TOUS LES TESTS ONT RÉUSSI!")
    print("=" * 50)
    return True


if __name__ == "__main__":
    success = test_mistral_connection()
    exit(0 if success else 1)
