"""
Client LLM pour Mistral AI API.
"""
import json
import os
import re
import requests
from typing import Optional, Dict, Any


class JSONParseError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        response: str,
        cleaned: str,
        parse_error: Optional[json.JSONDecodeError] = None,
    ):
        super().__init__(message)
        self.response = response
        self.cleaned = cleaned
        self.parse_error = parse_error

    def excerpt(self, max_chars: int = 2000) -> str:
        text = (self.cleaned or self.response or "").strip()
        if len(text) <= max_chars:
            return text
        head = text[: max_chars // 2]
        tail = text[-max_chars // 2 :]
        return f"{head}\n...\n{tail}"

    def location(self) -> str:
        if not self.parse_error:
            return ""
        return f" (ligne {self.parse_error.lineno}, colonne {self.parse_error.colno})"


def _strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


def _extract_json_object(text: str) -> Optional[str]:
    """
    Extrait la première structure JSON objet `{...}` d'un texte.
    Utile quand le modèle ajoute du texte avant/après malgré le mode JSON.
    """
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1].strip()

def _find_first_complete_json_object(text: str) -> Optional[str]:
    """
    Retourne le premier objet JSON complet `{...}` trouvé dans `text` (en respectant les strings).
    Si l'objet est tronqué, retourne None.
    """
    if not text:
        return None

    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False

    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1].strip()

    return None


def _escape_control_chars_in_strings(text: str) -> str:
    """
    Rend un JSON "presque valide" parseable quand le modèle met des retours à la ligne
    bruts dans des strings (non échappés), ex: "ligne1\nligne2" au lieu de "\\n".
    """
    if not text:
        return text

    out: list[str] = []
    in_string = False
    escaped = False
    i = 0
    while i < len(text):
        ch = text[i]

        if in_string:
            if escaped:
                out.append(ch)
                escaped = False
            else:
                if ch == "\\":
                    out.append(ch)
                    escaped = True
                elif ch == '"':
                    out.append(ch)
                    in_string = False
                elif ch == "\r":
                    # Convert CR/LF to JSON escape
                    if i + 1 < len(text) and text[i + 1] == "\n":
                        i += 1
                    out.append("\\n")
                elif ch == "\n":
                    out.append("\\n")
                elif ch == "\t":
                    out.append("\\t")
                elif ord(ch) < 0x20:
                    # Autres caractères de contrôle -> unicode escape
                    out.append(f"\\u{ord(ch):04x}")
                else:
                    out.append(ch)
        else:
            out.append(ch)
            if ch == '"':
                in_string = True

        i += 1

    return "".join(out)


_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


def _remove_trailing_commas(text: str) -> str:
    if not text:
        return text
    previous = None
    current = text
    while previous != current:
        previous = current
        current = _TRAILING_COMMA_RE.sub(r"\1", current)
    return current

def _is_likely_truncated_json(text: str) -> bool:
    """
    Heuristique: on a vu un '{' mais pas d'objet JSON complet.
    """
    if not text or "{" not in text:
        return False
    return _find_first_complete_json_object(text) is None


class LLMClient:
    """Client pour interagir avec Mistral AI API."""

    def __init__(
        self,
        model: str = "mistral-large-latest",
        provider: str = "mistral",
        api_key: Optional[str] = None,
        timeout_s: int = 300,  # Augmenté de 180s à 300s (5 minutes)
    ):
        self.model = model
        self.provider = provider
        self.api_key = api_key or os.getenv("MISTRAL_API_KEY")
        self.timeout_s = int(os.getenv("MISTRAL_TIMEOUT_S", str(timeout_s)))

        if not self.api_key and provider == "mistral":
            raise ValueError(
                "MISTRAL_API_KEY manquante. "
                "Définissez la variable d'environnement MISTRAL_API_KEY "
                "ou passez api_key au constructeur."
            )

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        json_mode: bool = False,
        max_tokens: int = 2000
    ) -> str:
        """
        Génère une réponse du LLM.

        Args:
            prompt: Le prompt utilisateur
            system: Le prompt système (optionnel)
            temperature: Température (0-1)
            json_mode: Force le format JSON
            max_tokens: Nombre max de tokens

        Returns:
            Réponse du modèle (str)
        """
        return self._generate_mistral(prompt, system, temperature, json_mode, max_tokens)

    def _generate_mistral(
        self,
        prompt: str,
        system: Optional[str],
        temperature: float,
        json_mode: bool,
        max_tokens: int
    ) -> str:
        """Génère via Mistral AI API."""
        url = "https://api.mistral.ai/v1/chat/completions"

        # Construire les messages
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        # Forcer format JSON si demandé
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json; charset=utf-8"
        }

        # Retry automatique pour les erreurs réseau transitoires
        max_retries = 5  # Augmenté de 3 à 5 pour plus de robustesse
        last_error = None

        for attempt in range(max_retries):
            try:
                # Encoder explicitement en UTF-8 pour éviter les problèmes avec les emojis
                response = requests.post(
                    url,
                    data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                    headers=headers,
                    timeout=self.timeout_s,
                )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"].strip()

            except requests.Timeout:
                raise RuntimeError(
                    f"Timeout Mistral AI après {self.timeout_s}s. "
                    f"La génération avec {max_tokens} tokens peut prendre du temps. "
                    f"Réessayez ou réduisez le nombre de jours."
                )
            except (requests.ConnectionError, requests.exceptions.ChunkedEncodingError) as e:
                # Erreurs réseau transitoires - retry avec backoff exponentiel
                last_error = e
                if attempt < max_retries - 1:
                    import time
                    wait_time = (attempt + 1) * 3  # Backoff augmenté: 3s, 6s, 9s, 12s, 15s
                    time.sleep(wait_time)
                    continue
                else:
                    raise RuntimeError(
                        f"Erreur réseau Mistral AI après {max_retries} tentatives: {e}. "
                        f"Vérifiez votre connexion internet et réessayez. "
                        f"Si le problème persiste, essayez avec moins de jours."
                    )
            except requests.HTTPError as e:
                # Erreurs HTTP (401, 429, 500, etc.) - ne pas retry
                status_code = e.response.status_code if e.response else "unknown"
                if status_code == 429:
                    raise RuntimeError(
                        f"Rate limit Mistral AI dépassé (429). "
                        f"Attendez quelques secondes et réessayez."
                    )
                elif status_code == 401:
                    raise RuntimeError(
                        f"Clé API Mistral invalide (401). "
                        f"Vérifiez votre MISTRAL_API_KEY."
                    )
                else:
                    raise RuntimeError(f"Erreur HTTP Mistral AI ({status_code}): {e}")
            except requests.RequestException as e:
                # Autres erreurs requests
                raise RuntimeError(f"Erreur Mistral AI: {e}")

    def generate_json(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 8000,
        *,
        max_continuations: int = 1,
    ) -> Dict[str, Any]:
        """
        Génère et parse une réponse JSON.

        Returns:
            Dict parsé (ou lève exception si parsing échoue)
        """
        response = self.generate(
            prompt=prompt,
            system=system,
            temperature=temperature,
            json_mode=True,
            max_tokens=max_tokens,
        )

        # Parfois, le modèle renvoie du texte autour. On tente d'abord d'isoler un JSON complet.
        cleaned0 = _strip_code_fences(response)
        complete0 = _find_first_complete_json_object(cleaned0)
        if complete0:
            try:
                return json.loads(complete0)
            except json.JSONDecodeError:
                pass

        try:
            return json.loads(response)
        except json.JSONDecodeError as e:
            cleaned = _strip_code_fences(response)

            # 1) Retry direct sur cleaned
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                pass

            # 2) Extraire un objet JSON noyé dans du texte
            extracted = _extract_json_object(cleaned)
            if extracted:
                try:
                    return json.loads(extracted)
                except json.JSONDecodeError:
                    pass

            # 2bis) Essayer d'isoler le premier objet JSON complet, s'il existe
            complete = _find_first_complete_json_object(cleaned)
            if complete:
                try:
                    return json.loads(complete)
                except json.JSONDecodeError:
                    pass

            # 3) Si l'objet semble tronqué, demander une continuation (évite de relancer un PLAN complet)
            combined = cleaned
            if max_continuations > 0 and _is_likely_truncated_json(cleaned):
                tail = cleaned[-1000:]  # Augmenté de 800 à 1000 pour plus de contexte
                for i in range(max_continuations):
                    continuation = self.generate(
                        prompt=(
                            "La réponse JSON précédente était tronquée. Continue EXACTEMENT où tu t'es arrêté "
                            "pour compléter le même objet JSON. Ne répète RIEN, ajoute uniquement la suite manquante.\n"
                            "Réponds uniquement avec les caractères JSON restants (pas de markdown, pas d'explications).\n\n"
                            f"FIN DE LA RÉPONSE PRÉCÉDENTE:\n{tail}"
                        ),
                        system=system,
                        temperature=0.0,
                        json_mode=False,
                        max_tokens=max(500, min(2000, max_tokens)),  # Plus de tokens pour les continuations
                    )
                    combined = combined + _strip_code_fences(continuation)
                    complete_after = _find_first_complete_json_object(combined)
                    if complete_after:
                        try:
                            return json.loads(complete_after)
                        except json.JSONDecodeError:
                            # Si parsing échoue après continuation, continuer à essayer
                            if i < max_continuations - 1:
                                continue
                            break

            # 3) Tentative de "repair" (contrôle chars + trailing commas)
            candidate = complete or extracted or combined
            repaired = _remove_trailing_commas(_escape_control_chars_in_strings(candidate))
            try:
                return json.loads(repaired)
            except json.JSONDecodeError as e2:
                raise JSONParseError(
                f"Impossible de parser JSON (max_tokens={max_tokens})",
                response=response,
                cleaned=repaired if repaired else cleaned,
                parse_error=e2,
            ) from e


if __name__ == "__main__":
    # Test
    client = LLMClient()

    # Test simple
    print("=== Test génération simple ===")
    response = client.generate("Quelle est la capitale de la France?", temperature=0.3)
    print(response[:200])

    # Test JSON
    print("\n=== Test génération JSON ===")
    json_response = client.generate_json(
        prompt='Liste 3 villes françaises au format: {"cities": ["ville1", "ville2", "ville3"]}',
        temperature=0.3
    )
    print(json_response)
