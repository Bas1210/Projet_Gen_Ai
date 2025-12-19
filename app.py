"""
Point d'entrée Streamlit.

Conserve `streamlit run app.py` tout en gardant le code UI dans `travel_planner/`.
"""

from travel_planner.ui.streamlit_app import main


if __name__ == "__main__":
    main()
