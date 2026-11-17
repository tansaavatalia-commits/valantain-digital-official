"""Etichette stampate nelle pagine, per lingua."""

from __future__ import annotations

LANGS: dict[str, dict] = {
    "it": {
        "days": ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"],
        "days_short": ["L", "M", "M", "G", "V", "S", "D"],
        "months": ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio",
                   "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"],
        "week": "Settimana", "month": "Mese", "date": "Data", "year": "Anno",
        "notes": "Note", "priorities": "Priorità", "todo": "Da fare", "goals": "Obiettivi",
        "habit": "Abitudine", "habits": "Tracker abitudini", "budget": "Budget mensile",
        "income": "Entrate", "expenses": "Uscite", "category": "Categoria",
        "planned": "Previsto", "actual": "Effettivo", "total": "Totale", "savings": "Risparmi",
        "checklist": "Checklist", "contents": "Indice", "schedule": "Programma",
        "gratitude": "Gratitudine", "mood": "Umore", "water": "Acqua",
        "why": "Perché è importante", "steps": "Prossimi passi", "deadline": "Scadenza",
        "reward": "Ricompensa", "home": "Indice", "personal_use": "Solo per uso personale",
        "year_overview": "Panoramica annuale", "top3": "Le 3 cose più importanti",
        "reflection": "Riflessione", "owner": "Nome", "daily": "Pagina giornaliera", "goal": "Obiettivo",
    },
    "en": {
        "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "days_short": ["M", "T", "W", "T", "F", "S", "S"],
        "months": ["January", "February", "March", "April", "May", "June", "July",
                   "August", "September", "October", "November", "December"],
        "week": "Week", "month": "Month", "date": "Date", "year": "Year",
        "notes": "Notes", "priorities": "Priorities", "todo": "To do", "goals": "Goals",
        "habit": "Habit", "habits": "Habit tracker", "budget": "Monthly budget",
        "income": "Income", "expenses": "Expenses", "category": "Category",
        "planned": "Planned", "actual": "Actual", "total": "Total", "savings": "Savings",
        "checklist": "Checklist", "contents": "Contents", "schedule": "Schedule",
        "gratitude": "Gratitude", "mood": "Mood", "water": "Water",
        "why": "Why it matters", "steps": "Next steps", "deadline": "Deadline",
        "reward": "Reward", "home": "Contents", "personal_use": "For personal use only",
        "year_overview": "Year at a glance", "top3": "Top 3 priorities",
        "reflection": "Reflection", "owner": "Name", "daily": "Daily page", "goal": "Goal",
    },
    "es": {
        "days": ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"],
        "days_short": ["L", "M", "X", "J", "V", "S", "D"],
        "months": ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
                   "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"],
        "week": "Semana", "month": "Mes", "date": "Fecha", "year": "Año",
        "notes": "Notas", "priorities": "Prioridades", "todo": "Pendientes", "goals": "Objetivos",
        "habit": "Hábito", "habits": "Registro de hábitos", "budget": "Presupuesto mensual",
        "income": "Ingresos", "expenses": "Gastos", "category": "Categoría",
        "planned": "Previsto", "actual": "Real", "total": "Total", "savings": "Ahorro",
        "checklist": "Checklist", "contents": "Índice", "schedule": "Horario",
        "gratitude": "Gratitud", "mood": "Ánimo", "water": "Agua",
        "why": "Por qué importa", "steps": "Próximos pasos", "deadline": "Fecha límite",
        "reward": "Recompensa", "home": "Índice", "personal_use": "Solo para uso personal",
        "year_overview": "Resumen del año", "top3": "Las 3 prioridades",
        "reflection": "Reflexión", "owner": "Nombre", "daily": "Página diaria", "goal": "Objetivo",
    },
}


def labels(lang: str, week_start: str = "monday") -> dict:
    """Etichette per la lingua, con i giorni ruotati se la settimana parte di domenica."""
    lab = dict(LANGS[lang])
    if week_start == "sunday":
        lab["days"] = lab["days"][-1:] + lab["days"][:-1]
        lab["days_short"] = lab["days_short"][-1:] + lab["days_short"][:-1]
    return lab


# Testi usati nelle immagini di presentazione (mockup) e nelle inserzioni.
SHOP: dict[str, dict] = {
    "it": {"pages": "pagine", "download": "Download immediato", "printable": "Stampabile",
           "linked": "Link interni per GoodNotes e Notability", "inside": "Cosa trovi dentro",
           "sizes": "Formati inclusi", "themes": "Disponibile in altri colori"},
    "en": {"pages": "pages", "download": "Instant download", "printable": "Printable",
           "linked": "Hyperlinked for GoodNotes & Notability", "inside": "What's inside",
           "sizes": "Sizes included", "themes": "Available in more colors"},
    "es": {"pages": "páginas", "download": "Descarga inmediata", "printable": "Imprimible",
           "linked": "Con enlaces para GoodNotes y Notability", "inside": "Qué incluye",
           "sizes": "Formatos incluidos", "themes": "Disponible en más colores"},
}
