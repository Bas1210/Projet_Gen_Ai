# ✈️ Planificateur de Voyage Autonome

**Agent intelligent avec raisonnement ReAct + Self-Correction**

---

## 📖 Description

Agent de planification de voyages autonome qui génère des itinéraires personnalisés en s'adaptant à la météo en temps réel. L'agent utilise des techniques avancées de raisonnement pour créer des plans cohérents et justifiés.

**Ce n'est pas un simple chatbot** : l'agent raisonne explicitement (visible dans les logs), utilise des outils externes (météo, géocodage), et critique ses propres propositions avant de les présenter.

---

## 🚀 Installation & Lancement

### Prérequis
- Python 3.10+
- Clé API Mistral AI ([obtenir ici](https://console.mistral.ai/))

### Installation

```bash
# Installer les dépendances
pip install -r requirements.txt

# Configurer la clé API
export MISTRAL_API_KEY="votre_clé_api_ici"

# Lancer l'application
streamlit run app.py
```

L'application s'ouvre à `http://localhost:8501`.

---

## 🎯 Utilisation

1. Remplir le formulaire (destination, dates, budget, centres d'intérêt)
2. Cliquer sur "Générer l'itinéraire"
3. Observer le raisonnement en temps réel (logs ReAct)
4. Consulter l'itinéraire jour par jour
5. Télécharger en Markdown ou JSON

### Exemple de raisonnement

```
--- Itération 1 ---
THOUGHT: Je dois obtenir les coordonnées de Paris pour récupérer la météo
ACTION: GEOCODE {"city": "Paris"}
OBSERVATION: Paris -> lat=48.85, lon=2.35, pays=France

--- Itération 2 ---
THOUGHT: Je récupère la météo pour les dates du voyage
ACTION: WEATHER {"lat": 48.85, "lon": 2.35, ...}
OBSERVATION: Météo récupérée: Jour 1: Froid-Sec, Jour 2: Pluie probable

--- Itération 3 ---
THOUGHT: J'ai toutes les infos, je génère l'itinéraire adapté à la météo
ACTION: PLAN {}
OBSERVATION: Itinéraire généré avec 3 jours

--- SELF-CORRECTION ---
Critique: Détection de problèmes (activité outdoor le jour de pluie)
Correction: Version corrigée avec activités indoor
```

---

## 🧠 Techniques de Raisonnement

### 1. ReAct (Reason + Act)

Boucle itérative qui combine raisonnement et action :

```
THINK → ACT (outil) → OBSERVE → DECIDE → THINK → ...
```

**Implémentation** :
- L'agent analyse la situation et décide de l'action suivante
- Exécute des actions (GEOCODE, WEATHER, PLAN)
- Observe les résultats et adapte sa stratégie
- Toutes les étapes sont loggées et visibles dans l'interface

**Avantages** :
- Planification explicite avant l'action
- Interaction avec des outils externes (API météo, géocodage)
- Adaptabilité selon les observations
- Transparence totale du processus

**Référence** : [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629) (Yao et al., 2022)

### 2. Self-Correction (Réflexion)

Après génération, l'agent critique et améliore sa proposition :

```
Génération → Critique → Détection de problèmes → Correction → Version finale
```

**Critères de vérification** :
- Cohérence avec la météo (pas d'activités outdoor si pluie)
- Respect du budget et du rythme demandé
- Présence d'alternatives indoor/outdoor
- Détection d'hallucinations (lieux inventés)
- Logique horaire (pas de conflits)

**Avantages** :
- Réduit les erreurs et incohérences
- Détecte et corrige les hallucinations
- Garantit le respect des contraintes utilisateur

**Référence** : [Reflexion: Language Agents with Verbal Reinforcement Learning](https://arxiv.org/abs/2303.11366) (Shinn et al., 2023)

### 3. Mode Dégradé (Robustesse)

L'agent continue même en cas de problème :

```
Météo indisponible → Mode dégradé activé → Génération équilibrée indoor/outdoor
```

**Cas d'usage** :
- API météo indisponible
- Dates trop éloignées (>16 jours)
- Problème réseau

L'agent détecte l'échec, log un avertissement, et génère un itinéraire équilibré avec alternatives.

---

## 🧩 Architecture

```
projet/
├── app.py                      # Point d'entrée Streamlit
├── travel_planner/
│   ├── models.py               # Modèles Pydantic (validation)
│   ├── metrics.py              # Scoring qualité
│   ├── ui/
│   │   └── streamlit_app.py    # Interface utilisateur
│   ├── agent/
│   │   ├── runner.py           # Orchestrateur ReAct + Self-Correction
│   │   ├── llm_client.py       # Client Mistral AI API
│   │   └── prompts.py          # Prompts (ReAct/Critique/Correction)
│   └── tools/
│       ├── geocode.py          # Géocodage (Open-Meteo)
│       └── weather.py          # Météo (Open-Meteo Forecast)
├── requirements.txt
└── README.md
```

---

## ✨ Fonctionnalités

- **Formulaire complet** : destination, dates, profil, budget, centres d'intérêt, rythme, contraintes
- **Raisonnement ReAct** : boucle THINK/ACT/OBSERVE visible en temps réel
- **Self-Correction** : critique et amélioration automatique
- **Outils externes** : intégration météo + géocodage
- **Itinéraire structuré** : matin/après-midi/soir avec détails (lieu, durée, coût, indoor/outdoor)
- **Alternatives** : activités de remplacement si mauvais temps
- **Justifications** : explications des choix stratégiques
- **Export** : téléchargement Markdown ou JSON
- **Statistiques** : graphiques interactifs (Plotly) + score qualité
- **Mode dégradé** : robuste, continue même sans météo

---

## 📦 Dépendances

```txt
streamlit>=1.28.0      # Interface utilisateur
requests>=2.31.0       # Appels API
pydantic>=2.5.0        # Validation JSON
plotly>=5.18.0         # Visualisations
python-dateutil>=2.8.2 # Gestion dates
```

---

## 📊 Exemple de Sortie

```markdown
### Jour 1 - 2025-12-20

🌅 Matin : Musée d'Orsay
📍 1 Rue de la Légion d'Honneur, 75007 Paris
⏱️ 2.5h | 💰 16€ | 🏠 Intérieur

☀️ Après-midi : Déjeuner gastronomique
📍 Quartier du Marais
⏱️ 2h | 💰 30-40€ | 🏠 Intérieur

🌙 Soir : Croisière sur la Seine
📍 Port de la Conférence
⏱️ 1h | 💰 15€ | 🌳 Extérieur

🔄 Alternatives : Musée Rodin, Galeries Lafayette...
```

**Justifications** :
- Jour 1 : Temps sec prévu → mix indoor/outdoor
- Jour 2 : Pluie probable → activités indoor privilégiées
- Budget moyen respecté
- Rythme normal : 2-3h par activité

---

## 🐛 Dépannage

**Erreur : "MISTRAL_API_KEY manquante"**
→ Configurez `export MISTRAL_API_KEY="..."` ou saisissez dans la sidebar

**Météo indisponible**
→ Normal pour dates >16 jours, l'agent passe en mode dégradé

**Génération lente**
→ 30-60s normales (géocodage + météo + ReAct + self-correction)

---

## 📚 Références

- [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629) (Yao et al., 2022)
- [Reflexion: Language Agents with Verbal Reinforcement Learning](https://arxiv.org/abs/2303.11366) (Shinn et al., 2023)
- [Mistral AI Documentation](https://docs.mistral.ai/)
- [Open-Meteo Documentation](https://open-meteo.com/en/docs)

---

## 👥 Contributeurs

Basile Sorrel
Wadih Ben Abdesselem

---

## 📄 Licence

Projet réalisé dans le cadre du cours IA Générative.
