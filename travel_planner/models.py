"""
Modèles Pydantic (validation des données).
"""
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict


class Activity(BaseModel):
    model_config = ConfigDict(extra="ignore")

    """Une activité dans l'itinéraire."""
    name: str
    location: str
    duration: str  # Ex: "2h", "3h30"
    cost_estimate: str  # Ex: "15-20€", "Gratuit"
    indoor: bool
    description: Optional[str] = None


class DayPlan(BaseModel):
    model_config = ConfigDict(extra="ignore")

    """Plan pour une journée."""
    day_number: int
    date: str
    morning: Activity
    afternoon: Activity
    evening: Activity
    alternatives: List[Activity] = Field(default_factory=list, description="Activités alternatives en cas de mauvais temps")
    notes: Optional[str] = None  # Transport, réservations


class Itinerary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    """Itinéraire complet."""
    daily_plans: List[DayPlan]
    justifications: List[str] = Field(default_factory=list)
    checklist: List[str] = Field(default_factory=list)
