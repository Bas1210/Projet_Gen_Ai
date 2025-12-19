"""
Runner ReAct pour l'agent de planification de voyage.
"""
import json
import time
from typing import Dict, List, Any, Optional, Callable

from pydantic import ValidationError

from travel_planner.agent.llm_client import LLMClient, JSONParseError
from travel_planner.agent.prompts import (
    SYSTEM_PROMPT,
    REACT_PLANNER_PROMPT,
    ITINERARY_GENERATOR_PROMPT,
    CRITIC_PROMPT,
    CORRECTOR_PROMPT
)
from travel_planner.models import Itinerary
from travel_planner.tools.geocode import geocode
from travel_planner.tools.weather import get_weather


class TravelPlannerAgent:
    """Agent ReAct pour planifier des voyages."""

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        log_callback: Optional[Callable[[str], None]] = None,
        *,
        max_iterations: int = 5,
        enable_self_correction: bool = True,
        max_tokens_plan: int = 8000,  # Augmenté pour permettre de longs itinéraires sans troncature
        max_tokens_critic: int = 2000,
        max_tokens_corrector: int = 8000,  # Augmenté pour permettre de longues corrections
    ):
        self.llm = llm_client or LLMClient()
        self.max_iterations = max_iterations
        self.action_history = []
        self.collected_info = {}
        self.log_callback = log_callback
        self.enable_self_correction = enable_self_correction
        self.max_tokens_plan = max_tokens_plan
        self.max_tokens_critic = max_tokens_critic
        self.max_tokens_corrector = max_tokens_corrector

    def _log(self, logs: List[str], message: str) -> None:
        logs.append(message)
        if self.log_callback:
            self.log_callback(message)

    def plan_trip(
        self,
        destination: str,
        start_date: str,
        end_date: str,
        profile: str = "solo",
        budget: str = "moyen",
        interests: List[str] = None,
        pace: str = "normal",
        constraints: str = ""
    ) -> Dict[str, Any]:
        """
        Planifie un voyage complet avec ReAct + Self-correction.

        Returns:
            Dict avec {
                "itinerary": {...},
                "logs": [...],  # Logs ReAct pour démo
                "weather": [...],
                "success": bool
            }
        """
        interests = interests or []

        # Démarrer le chronomètre
        start_time = time.time()

        # Préparer la requête utilisateur
        user_request = f"""
Destination: {destination}
Dates: {start_date} au {end_date}
Profil: {profile}
Budget: {budget}
Intérêts: {', '.join(interests)}
Rythme: {pace}
Contraintes: {constraints or 'Aucune'}
        """.strip()

        # Reset state
        self.action_history = []
        self.collected_info = {
            "destination": destination,
            "start_date": start_date,
            "end_date": end_date,
            "profile": profile,
            "budget": budget,
            "interests": interests,
            "pace": pace,
            "constraints": constraints
        }

        logs = []

        # Boucle ReAct
        for iteration in range(self.max_iterations):
            self._log(logs, f"\n--- Itération {iteration + 1} ---")

            # Décider de l'action suivante
            action_history_str = "\n".join(self.action_history) if self.action_history else "Aucune action encore"
            collected_info_str = json.dumps(self.collected_info, indent=2, ensure_ascii=False)

            prompt = REACT_PLANNER_PROMPT.format(
                user_request=user_request,
                collected_info=collected_info_str,
                action_history=action_history_str
            )

            try:
                decision = self.llm.generate_json(prompt, system=SYSTEM_PROMPT, temperature=0.3)

                thought = decision.get("thought", "")
                action = decision.get("action", "")
                action_input = decision.get("action_input", {})

                self._log(logs, f"THOUGHT: {thought}")

                # Sauvegarder l'action originale pour le log
                original_action = action
                original_input = action_input

                # OVERRIDE 1: Si GEOCODE déjà fait, ne pas le refaire
                if action == "GEOCODE" and "geocode" in self.collected_info:
                    self._log(logs, f"ACTION: {original_action} {original_input}")
                    self._log(logs, "⚠️  OVERRIDE: Géocodage déjà effectué, passage à WEATHER ou PLAN")
                    # Si pas encore de météo, faire WEATHER, sinon PLAN
                    if "weather" not in self.collected_info:
                        action = "WEATHER"
                        geocode_data = self.collected_info["geocode"]
                        action_input = {
                            "lat": geocode_data["lat"],
                            "lon": geocode_data["lon"],
                            "start_date": self.collected_info["start_date"],
                            "end_date": self.collected_info["end_date"]
                        }
                        self._log(logs, f"→ NOUVELLE ACTION: {action} {action_input}")
                    else:
                        action = "PLAN"
                        action_input = {}
                        self._log(logs, f"→ NOUVELLE ACTION: {action}")

                # OVERRIDE 2: Si WEATHER déjà réussi, ne pas le refaire
                elif action == "WEATHER" and "weather" in self.collected_info and not self.collected_info.get("weather_unavailable"):
                    self._log(logs, f"ACTION: {original_action} {original_input}")
                    self._log(logs, "⚠️  OVERRIDE: Météo déjà récupérée, passage direct à PLAN")
                    action = "PLAN"
                    action_input = {}
                    self._log(logs, f"→ NOUVELLE ACTION: {action}")

                # OVERRIDE 3: Si météo a échoué et que l'agent redemande WEATHER, forcer PLAN
                elif action == "WEATHER" and self.collected_info.get("weather_unavailable"):
                    self._log(logs, f"ACTION: {original_action} {original_input}")
                    self._log(logs, "⚠️  OVERRIDE: Météo déjà indisponible, passage direct à PLAN (mode dégradé)")
                    action = "PLAN"
                    action_input = {}
                    self._log(logs, f"→ NOUVELLE ACTION: {action}")
                else:
                    # Pas d'override, action normale
                    self._log(logs, f"ACTION: {action} {action_input}")

                # Exécuter l'action
                if action == "GEOCODE":
                    result = self._execute_geocode(action_input, logs)
                elif action == "WEATHER":
                    result = self._execute_weather(action_input, logs)
                elif action == "PLAN":
                    result = self._execute_plan(logs)
                    # Après PLAN, faire self-correction (optionnel)
                    final_itinerary = (
                        self._self_correct(result, logs) if self.enable_self_correction else result
                    )

                    # Calculer temps d'exécution
                    execution_time = time.time() - start_time

                    return {
                        "itinerary": final_itinerary,
                        "logs": logs,
                        "weather": self.collected_info.get("weather", []),
                        "success": True,
                        "metrics": {
                            "execution_time": execution_time,
                            "iterations": iteration + 1,
                            "actions_count": len(self.action_history)
                        }
                    }
                elif action == "FINISH":
                    self._log(logs, "FINISH: Agent terminé")
                    return {
                        "itinerary": self.collected_info.get("itinerary", {}),
                        "logs": logs,
                        "weather": self.collected_info.get("weather", []),
                        "success": True
                    }
                else:
                    self._log(logs, f"ERREUR: Action inconnue '{action}'")
                    result = None

                # Enregistrer dans l'historique
                self.action_history.append(f"{action}: {action_input} -> {result}")

            except Exception as e:
                self._log(logs, f"ERREUR: {str(e)}")
                return {
                    "itinerary": {},
                    "logs": logs,
                    "weather": [],
                    "success": False,
                    "error": str(e)
                }

        # Si on arrive ici, max iterations atteintes
        self._log(logs, "ATTENTION: Nombre max d'itérations atteint")
        return {
            "itinerary": self.collected_info.get("itinerary", {}),
            "logs": logs,
            "weather": self.collected_info.get("weather", []),
            "success": False,
            "error": "Max iterations"
        }

    def _execute_geocode(self, action_input: Dict, logs: List[str]) -> Optional[Dict]:
        """Exécute l'action GEOCODE."""
        city = action_input.get("city")
        if not city:
            self._log(logs, "ERREUR: Pas de ville spécifiée pour GEOCODE")
            return None

        result = geocode(city)
        if result:
            self.collected_info["geocode"] = result
            self._log(logs, f"OBSERVATION: {city} -> lat={result['lat']}, lon={result['lon']}, pays={result['country']}")
            return result
        else:
            self._log(logs, f"ERREUR: Ville '{city}' non trouvée")
            return None

    def _execute_weather(self, action_input: Dict, logs: List[str]) -> Optional[List[Dict]]:
        """Exécute l'action WEATHER."""
        lat = action_input.get("lat")
        lon = action_input.get("lon")
        start_date = action_input.get("start_date")
        end_date = action_input.get("end_date")

        if not all([lat, lon, start_date, end_date]):
            self._log(logs, "ERREUR: Paramètres manquants pour WEATHER")
            return None

        weather = get_weather(lat, lon, start_date, end_date)
        if weather:
            self.collected_info["weather"] = weather
            summary = "\n".join([f"  {w['date']}: {w['description']}" for w in weather[:3]])
            self._log(logs, f"OBSERVATION: Météo récupérée:\n{summary}")
            return weather
        else:
            self._log(logs, "AVERTISSEMENT: Impossible de récupérer la météo (API indisponible ou dates hors limites)")
            self._log(logs, "→ L'itinéraire sera généré sans adaptation météo")
            self.collected_info["weather"] = []
            self.collected_info["weather_unavailable"] = True
            return []

    def _execute_plan(self, logs: List[str]) -> Dict:
        """Exécute l'action PLAN (génération itinéraire)."""
        self._log(logs, "ACTION: Génération de l'itinéraire...")

        # Formatter météo pour le prompt
        weather_data = self.collected_info.get("weather", [])
        weather_unavailable = self.collected_info.get("weather_unavailable", False)

        if weather_unavailable or not weather_data:
            weather_str = "⚠️ MÉTÉO NON DISPONIBLE - Propose un itinéraire équilibré avec un mix d'activités indoor/outdoor. Inclus des alternatives pour chaque jour."
            self._log(logs, "Mode dégradé: génération sans données météo")
        else:
            weather_str = "\n".join([
                f"{w['date']}: {w['temp_min']}°C-{w['temp_max']}°C, "
                f"Pluie: {w['precipitation_probability']}%, "
                f"{w['description']}"
                for w in weather_data
            ])

        prompt = ITINERARY_GENERATOR_PROMPT.format(
            destination=self.collected_info["destination"],
            start_date=self.collected_info["start_date"],
            end_date=self.collected_info["end_date"],
            profile=self.collected_info["profile"],
            budget=self.collected_info["budget"],
            interests=", ".join(self.collected_info["interests"]),
            pace=self.collected_info["pace"],
            constraints=self.collected_info["constraints"] or "Aucune",
            weather_data=weather_str
        )

        # Pour Mistral, utiliser plus de tokens pour itinéraires longs (7+ jours)
        # Retry jusqu'à 2 fois en cas d'erreur JSON
        max_retries = 2
        for attempt in range(max_retries):
            try:
                itinerary = self.llm.generate_json(
                    prompt,
                    temperature=0.5,
                    max_tokens=self.max_tokens_plan,
                    max_continuations=3  # Jusqu'à 3 continuations si le JSON est tronqué
                )
                itinerary = Itinerary.model_validate(itinerary).model_dump()
                self.collected_info["itinerary"] = itinerary
                self._log(logs, f"OBSERVATION: Itinéraire généré avec {len(itinerary.get('daily_plans', []))} jours")
                return itinerary
            except JSONParseError as e:
                self._log(
                    logs,
                    f"⚠️  Réponse du modèle non-JSON{e.location()} (tentative {attempt + 1}/{max_retries}). Extrait:\n{e.excerpt()}",
                )
                if attempt < max_retries - 1:
                    self._log(logs, "⚠️  Erreur JSON, retry...")
                else:
                    self._log(logs, f"ERREUR: {str(e)}")
                    raise
            except (ValueError, ValidationError) as e:
                if attempt < max_retries - 1:
                    self._log(logs, f"⚠️  Erreur JSON (tentative {attempt + 1}/{max_retries}), retry...")
                else:
                    self._log(logs, f"ERREUR: {str(e)}")
                    raise

    def _self_correct(self, itinerary: Dict, logs: List[str]) -> Dict:
        """Critique et corrige l'itinéraire (self-correction)."""
        self._log(logs, "\n--- SELF-CORRECTION ---")

        # Formatter météo
        weather_data = self.collected_info.get("weather", [])
        weather_unavailable = self.collected_info.get("weather_unavailable", False)

        if weather_unavailable or not weather_data:
            weather_str = "⚠️ MÉTÉO NON DISPONIBLE - Ne vérifie PAS la cohérence météo. Vérifie uniquement: budget, rythme, présence d'alternatives indoor/outdoor."
            self._log(logs, "Critique en mode dégradé (sans météo)")
        else:
            weather_str = "\n".join([
                f"{w['date']}: {w['description']}, Pluie: {w['precipitation_probability']}%"
                for w in weather_data
            ])

        # Critique
        self._log(logs, "Critique de l'itinéraire...")
        critique_prompt = CRITIC_PROMPT.format(
            itinerary=json.dumps(itinerary, ensure_ascii=False, indent=2),
            weather_data=weather_str,
            budget=self.collected_info["budget"],
            pace=self.collected_info["pace"]
        )

        try:
            critique = self.llm.generate_json(
                critique_prompt, temperature=0.2, max_tokens=self.max_tokens_critic
            )

            is_valid = critique.get("is_valid", False)
            issues = critique.get("issues", [])
            suggestions = critique.get("suggestions", [])

            if is_valid and not issues:
                self._log(logs, "VALIDATION: Itinéraire OK, aucune correction nécessaire")
                return itinerary

            # Problèmes détectés
            self._log(logs, f"PROBLÈMES DÉTECTÉS: {len(issues)}")
            for issue in issues:
                self._log(logs, f"  - [{issue.get('type')}] {issue.get('description')}")

            # Correction
            self._log(logs, "Correction de l'itinéraire...")
            corrector_prompt = CORRECTOR_PROMPT.format(
                original_itinerary=json.dumps(itinerary, ensure_ascii=False, indent=2),
                issues=json.dumps(issues, ensure_ascii=False, indent=2),
                suggestions=json.dumps(suggestions, ensure_ascii=False, indent=2)
            )

            corrected = self.llm.generate_json(
                corrector_prompt, temperature=0.4, max_tokens=self.max_tokens_corrector
            )
            self._log(logs, "CORRECTION: Itinéraire corrigé")
            return corrected

        except Exception as e:
            self._log(logs, f"ERREUR lors de la self-correction: {e}")
            self._log(logs, "Retour de l'itinéraire original")
            return itinerary


if __name__ == "__main__":
    # Test
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

    print("\n".join(result["logs"]))
    print("\n=== ITINÉRAIRE ===")
    print(json.dumps(result["itinerary"], indent=2, ensure_ascii=False))
