"""
Application Streamlit - Planificateur de voyage autonome avec Agent ReAct.
"""
import streamlit as st
import json
import os
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

from travel_planner.agent.runner import TravelPlannerAgent
from travel_planner.agent.llm_client import LLMClient
from travel_planner.metrics import calculate_itinerary_stats, calculate_quality_score


# Configuration de la page
st.set_page_config(
    page_title="Planificateur de Voyage Autonome",
    page_icon="✈️",
    layout="wide"
)


def main():
    """Page principale de l'application."""

    # Sidebar navigation
    page = st.sidebar.radio(
        "Navigation",
        ["🗺️ Planificateur", "📄 Sujet du Projet"]
    )

    if page == "🗺️ Planificateur":
        show_planner()
    else:
        show_subject()


def show_planner():
    """Affiche le planificateur de voyage."""
    st.title("✈️ Planificateur de Voyage Autonome")
    st.markdown("**Agent intelligent avec raisonnement ReAct + Self-correction**")

    # Sidebar pour paramètres avancés
    debug_enabled = False
    enable_self_correction = True
    max_tokens_plan = 8000  # Augmenté pour éviter les troncatures JSON
    max_tokens_critic = 2000
    max_tokens_corrector = 8000  # Augmenté pour permettre de longues corrections
    mistral_timeout_s = 300  # Augmenté de 180s à 300s (5 min) pour longs itinéraires
    with st.sidebar:
        st.subheader("⚙️ Configuration")

        # Clé API Mistral
        api_key = st.text_input(
            "Clé API Mistral",
            type="password",
            help="Obtenez votre clé sur https://console.mistral.ai/",
            value=os.getenv("MISTRAL_API_KEY", "")
        )

        if not api_key:
            st.warning("⚠️ Clé API Mistral requise")
            st.markdown("[Obtenir une clé API](https://console.mistral.ai/)")

        model_name = "mistral-large-latest"
        st.caption(f"Modèle: **{model_name}**")

        st.markdown("---")
        debug_enabled = st.checkbox(
            "Afficher le journal de raisonnement (debug)",
            value=True,
            help="Affiche en temps réel les étapes THINK/ACTION/OBSERVATION et la self-correction.",
        )

        with st.expander("🧪 Réglages avancés", expanded=False):
            enable_self_correction = st.checkbox(
                "Activer la self-correction",
                value=True,
                help="Désactive si tu veux réduire le nombre d'appels LLM pour diagnostiquer un problème réseau.",
            )
            max_tokens_plan = st.slider(
                "Max tokens (PLAN)",
                min_value=1000,
                max_value=16000,
                value=8000,
                step=1000,
                help="Nombre max de tokens pour générer l'itinéraire. Augmentez si le JSON est tronqué.",
            )
            max_tokens_critic = st.slider(
                "Max tokens (CRITIC)",
                min_value=500,
                max_value=4000,
                value=2000,
                step=250,
            )
            max_tokens_corrector = st.slider(
                "Max tokens (CORRECTOR)",
                min_value=1000,
                max_value=16000,
                value=8000,
                step=1000,
            )
            mistral_timeout_s = st.slider(
                "Timeout Mistral (secondes)",
                min_value=60,
                max_value=600,
                value=300,
                step=30,
                help="Augmenter si le PLAN timeout (trajets longs). Réduire si tu veux un échec plus rapide pour debug.",
            )

    # Formulaire
    st.header("1️⃣ Informations du voyage")

    col1, col2 = st.columns(2)

    with col1:
        destination = st.text_input(
            "Destination",
            placeholder="Ex: Paris, Tokyo, New York...",
            help="Entrez le nom de la ville ou du pays"
        )

        profile = st.selectbox(
            "Profil de voyageur",
            ["solo", "couple", "famille"],
            help="Type de voyage"
        )

        budget = st.selectbox(
            "Budget",
            ["faible", "moyen", "élevé"],
            index=1
        )

    with col2:
        # Dates
        today = datetime.now().date()
        start_date = st.date_input(
            "Date de début",
            value=today + timedelta(days=7),
            min_value=today
        )

        # S'assurer que la valeur par défaut de end_date est toujours >= start_date
        # Convertir start_date en date si c'est un datetime
        if hasattr(start_date, 'date'):
            start_date_val = start_date.date()
        else:
            start_date_val = start_date

        default_end = max(start_date_val + timedelta(days=3), today + timedelta(days=10))
        end_date = st.date_input(
            "Date de fin",
            value=default_end,
            min_value=start_date
        )

        pace = st.selectbox(
            "Rythme",
            ["calme", "normal", "intense"],
            index=1,
            help="Intensité du voyage"
        )

    # Intérêts
    interests_options = [
        "musées", "nature", "gastronomie", "shopping",
        "architecture", "culture locale", "vie nocturne", "sport"
    ]
    interests = st.multiselect(
        "Centres d'intérêt",
        interests_options,
        default=["musées", "gastronomie"]
    )

    constraints = st.text_area(
        "Contraintes particulières (optionnel)",
        placeholder="Ex: mobilité réduite, enfants en bas âge, horaires spécifiques...",
        height=80
    )

    # Bouton de génération
    st.markdown("---")

    if st.button("🚀 Générer l'itinéraire", type="primary", use_container_width=True):
        if not destination:
            st.error("Veuillez entrer une destination")
            return

        # Validation des dates
        if start_date >= end_date:
            st.error("La date de fin doit être après la date de début")
            return

        # Nombre de jours
        num_days = (end_date - start_date).days
        if num_days > 14:
            st.warning("⚠️ L'API météo peut avoir des limites pour les prévisions au-delà de 14 jours")

        # Génération avec barre de progression
        progress_bar = st.progress(0)
        status_text = st.empty()
        live_logs: list[str] = []
        live_log_placeholder = None

        if debug_enabled:
            with st.expander("📋 Journal de raisonnement (live)", expanded=True):
                live_log_placeholder = st.empty()
                live_log_placeholder.code("", language="text")

        def push_log(message: str) -> None:
            live_logs.append(message)
            if live_log_placeholder is not None:
                live_log_placeholder.code("\n".join(live_logs), language="text")

        try:
            # Vérifier que la clé API est fournie
            if not api_key:
                st.error("❌ Clé API Mistral requise. Veuillez la saisir dans la barre latérale.")
                return

            # Étape 1
            status_text.text("🔍 Initialisation de l'agent...")
            progress_bar.progress(10)

            # Créer LLM client avec Mistral API
            llm_client = LLMClient(model=model_name, api_key=api_key, timeout_s=mistral_timeout_s)
            agent = TravelPlannerAgent(
                llm_client=llm_client,
                log_callback=push_log if debug_enabled else None,
                enable_self_correction=enable_self_correction,
                max_tokens_plan=max_tokens_plan,
                max_tokens_critic=max_tokens_critic,
                max_tokens_corrector=max_tokens_corrector,
            )

            # Étape 2
            status_text.text("🌍 Géocodage de la destination...")
            progress_bar.progress(25)

            # Étape 3
            status_text.text("🌤️ Récupération de la météo...")
            progress_bar.progress(40)

            # Étape 4
            status_text.text("🧠 Génération de l'itinéraire (ReAct)...")
            progress_bar.progress(60)

            # Planifier
            result = agent.plan_trip(
                destination=destination,
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
                profile=profile,
                budget=budget,
                interests=interests,
                pace=pace,
                constraints=constraints
            )

            # Étape 5
            status_text.text("✨ Self-correction et finalisation...")
            progress_bar.progress(90)

            # Terminer
            progress_bar.progress(100)
            status_text.text("✅ Génération terminée!")

            # Nettoyer
            import time
            time.sleep(0.5)
            progress_bar.empty()
            status_text.empty()

            # Afficher les résultats
            if result.get("success"):
                display_results(result)
            else:
                st.error(f"❌ Erreur lors de la génération: {result.get('error', 'Erreur inconnue')}")

                # Afficher les logs même en cas d'erreur
                with st.expander("📋 Journal de l'agent (debug)", expanded=True):
                    st.code("\n".join(result.get("logs", [])), language="text")

        except Exception as e:
            progress_bar.empty()
            status_text.empty()
            st.error(f"❌ Erreur: {str(e)}")
            st.exception(e)
            if debug_enabled and live_logs:
                with st.expander("📋 Journal de raisonnement (partiel)", expanded=True):
                    st.code("\n".join(live_logs), language="text")


def display_results(result):
    """Affiche les résultats de la planification."""
    st.success("✅ Itinéraire généré avec succès!")

    itinerary = result.get("itinerary", {})
    weather = result.get("weather", [])
    metrics = result.get("metrics", {})

    # === NOUVEAU : Métriques de Performance ===
    st.header("📊 Métriques de Génération")

    col1, col2, col3 = st.columns(3)

    with col1:
        exec_time = metrics.get("execution_time", 0)
        st.metric(
            label="⏱️ Temps d'exécution",
            value=f"{exec_time:.1f}s"
        )

    with col2:
        iterations = metrics.get("iterations", 0)
        st.metric(
            label="🔄 Itérations ReAct",
            value=iterations
        )

    with col3:
        actions = metrics.get("actions_count", 0)
        st.metric(
            label="🛠️ Actions exécutées",
            value=actions
        )

    # === NOUVEAU : Statistiques & Score de Qualité ===
    st.header("🎯 Analyse de l'Itinéraire")

    # Calculer statistiques
    stats = calculate_itinerary_stats(itinerary, weather)

    # Extraire profil/budget depuis le résultat ou utiliser défaut
    # (Idéalement on devrait les passer en paramètre, mais pour simplifier...)
    budget = "moyen"  # À améliorer si on stocke dans result
    pace = "normal"   # À améliorer si on stocke dans result

    quality = calculate_quality_score(itinerary, weather, budget, pace)

    # Afficher score global avec jauge
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        score = quality["overall_score"]
        color = "green" if score >= 80 else "orange" if score >= 60 else "red"
        st.metric(
            label="✅ Score de Qualité",
            value=f"{score}/100",
            delta="Excellent" if score >= 80 else "Bon" if score >= 60 else "À améliorer"
        )

    with col2:
        avg_cost = (stats["total_cost_min"] + stats["total_cost_max"]) / 2
        st.metric(
            label="💰 Coût Total Estimé",
            value=f"{avg_cost:.0f}€",
            delta=f"{stats['total_cost_min']:.0f}-{stats['total_cost_max']:.0f}€"
        )

    with col3:
        indoor_pct = stats["indoor_ratio"] * 100
        st.metric(
            label="🏠 Indoor",
            value=f"{indoor_pct:.0f}%"
        )

    with col4:
        outdoor_pct = stats["outdoor_ratio"] * 100
        st.metric(
            label="🌳 Outdoor",
            value=f"{outdoor_pct:.0f}%"
        )

    # Détails de validation
    with st.expander("🔍 Détails de Validation"):
        for detail in quality["details"]:
            st.markdown(detail)

    # Météo
    st.header("2️⃣ Aperçu météo")

    if weather:
        # Cartes météo
        cols = st.columns(min(len(weather), 4))
        for i, w in enumerate(weather):
            with cols[i % 4]:
                # Icône météo selon conditions
                icon = get_weather_icon(w["precipitation_probability"], w["temp_max"])
                st.metric(
                    label=f"{icon} {w['date']}",
                    value=f"{w['temp_max']:.0f}°C",
                    delta=f"{w['temp_min']:.0f}°C min"
                )
                st.caption(w["description"])
                if w["precipitation_probability"] > 50:
                    st.caption(f"☔ Pluie: {w['precipitation_probability']}%")

        # === NOUVEAU : Graphique Température ===
        st.subheader("📈 Évolution des températures")

        # Créer DataFrame pour Plotly
        df_weather = pd.DataFrame(weather)

        # Graphique température
        fig = go.Figure()

        fig.add_trace(go.Scatter(
            x=df_weather['date'],
            y=df_weather['temp_max'],
            name='Température Max',
            mode='lines+markers',
            line=dict(color='red', width=2),
            marker=dict(size=8)
        ))

        fig.add_trace(go.Scatter(
            x=df_weather['date'],
            y=df_weather['temp_min'],
            name='Température Min',
            mode='lines+markers',
            line=dict(color='blue', width=2),
            marker=dict(size=8)
        ))

        # Ajouter zone de pluie
        fig.add_trace(go.Bar(
            x=df_weather['date'],
            y=df_weather['precipitation_probability'],
            name='Probabilité de pluie (%)',
            yaxis='y2',
            marker=dict(color='lightblue', opacity=0.3)
        ))

        fig.update_layout(
            xaxis_title="Date",
            yaxis_title="Température (°C)",
            yaxis2=dict(
                title="Pluie (%)",
                overlaying='y',
                side='right',
                range=[0, 100]
            ),
            hovermode='x unified',
            height=400
        )

        st.plotly_chart(fig, use_container_width=True)

    else:
        st.warning("⚠️ **Météo indisponible** - L'itinéraire a été généré sans adaptation météo. Des dates trop éloignées ou l'API météo peuvent être en cause. Un mix d'activités indoor/outdoor a été proposé avec des alternatives.")

    # Itinéraire
    st.header("3️⃣ Itinéraire détaillé")

    itinerary = result.get("itinerary", {})
    daily_plans = itinerary.get("daily_plans", [])

    for day in daily_plans:
        with st.expander(f"**📅 Jour {day['day_number']} - {day['date']}**", expanded=True):
            col1, col2, col3 = st.columns(3)

            # Matin
            with col1:
                st.subheader("🌅 Matin")
                display_activity(day["morning"])

            # Après-midi
            with col2:
                st.subheader("☀️ Après-midi")
                display_activity(day["afternoon"])

            # Soir
            with col3:
                st.subheader("🌙 Soir")
                display_activity(day["evening"])

            # Alternatives
            if day.get("alternatives"):
                st.markdown("**🔄 Alternatives (en cas de mauvais temps)**")
                alt_cols = st.columns(len(day["alternatives"]))
                for i, alt in enumerate(day["alternatives"]):
                    with alt_cols[i]:
                        st.markdown(f"**{alt['name']}**")
                        st.caption(f"📍 {alt['location']}")
                        st.caption(f"💰 {alt['cost_estimate']}")

            # Notes
            if day.get("notes"):
                st.info(f"ℹ️ **Notes:** {day['notes']}")

    # Justifications
    st.header("4️⃣ Justifications des choix")
    justifications = itinerary.get("justifications", [])
    if justifications:
        for just in justifications:
            st.markdown(f"- {just}")

    # Checklist
    st.header("5️⃣ Checklist")
    checklist = itinerary.get("checklist", [])
    if checklist:
        for item in checklist:
            st.checkbox(item, key=f"check_{item}")

    # Journal ReAct
    with st.expander("🔍 Journal de raisonnement de l'agent (ReAct)"):
        st.markdown("**Voici comment l'agent a raisonné étape par étape:**")
        logs = result.get("logs", [])
        st.code("\n".join(logs), language="text")

    # Export
    st.header("6️⃣ Téléchargement")

    col1, col2 = st.columns(2)

    with col1:
        # Export Markdown
        markdown_content = generate_markdown(result)
        st.download_button(
            label="📄 Télécharger en Markdown",
            data=markdown_content,
            file_name="itineraire.md",
            mime="text/markdown"
        )

    with col2:
        # Export JSON
        json_content = json.dumps(itinerary, indent=2, ensure_ascii=False)
        st.download_button(
            label="📋 Télécharger en JSON",
            data=json_content,
            file_name="itineraire.json",
            mime="application/json"
        )


def get_weather_icon(precipitation_prob: int, temp: float) -> str:
    """Retourne une icône météo selon les conditions."""
    if precipitation_prob > 70:
        return "🌧️"
    elif precipitation_prob > 40:
        return "⛅"
    elif temp > 25:
        return "☀️"
    elif temp < 5:
        return "❄️"
    else:
        return "🌤️"


def display_activity(activity):
    """Affiche une activité."""
    st.markdown(f"**{activity['name']}**")
    st.markdown(f"📍 {activity['location']}")
    st.markdown(f"⏱️ {activity['duration']}")
    st.markdown(f"💰 {activity['cost_estimate']}")

    if activity.get("indoor"):
        st.caption("🏠 Intérieur")
    else:
        st.caption("🌳 Extérieur")

    if activity.get("description"):
        st.caption(activity["description"])


def generate_markdown(result):
    """Génère un export Markdown de l'itinéraire."""
    itinerary = result.get("itinerary", {})
    weather = result.get("weather", [])

    md = "# 🗺️ Itinéraire de voyage\n\n"

    # Météo
    md += "## 🌤️ Météo\n\n"
    for w in weather:
        md += f"- **{w['date']}**: {w['temp_min']:.0f}°C - {w['temp_max']:.0f}°C | {w['description']}\n"

    md += "\n## 📅 Programme\n\n"

    # Jours
    for day in itinerary.get("daily_plans", []):
        md += f"### Jour {day['day_number']} - {day['date']}\n\n"

        md += f"**🌅 Matin:** {day['morning']['name']}\n"
        md += f"- 📍 {day['morning']['location']}\n"
        md += f"- ⏱️ {day['morning']['duration']}\n"
        md += f"- 💰 {day['morning']['cost_estimate']}\n\n"

        md += f"**☀️ Après-midi:** {day['afternoon']['name']}\n"
        md += f"- 📍 {day['afternoon']['location']}\n"
        md += f"- ⏱️ {day['afternoon']['duration']}\n"
        md += f"- 💰 {day['afternoon']['cost_estimate']}\n\n"

        md += f"**🌙 Soir:** {day['evening']['name']}\n"
        md += f"- 📍 {day['evening']['location']}\n"
        md += f"- ⏱️ {day['evening']['duration']}\n"
        md += f"- 💰 {day['evening']['cost_estimate']}\n\n"

        if day.get("notes"):
            md += f"ℹ️ **Notes:** {day['notes']}\n\n"

    # Checklist
    md += "## ✅ Checklist\n\n"
    for item in itinerary.get("checklist", []):
        md += f"- [ ] {item}\n"

    return md


def show_subject():
    """Affiche la page du sujet."""
    st.title("📄 Sujet du Projet")

    sujet_path = Path(__file__).resolve().parents[2] / "docs" / "sujet.md"
    try:
        st.markdown(sujet_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        st.warning("Fichier `docs/sujet.md` introuvable.")


if __name__ == "__main__":
    main()
