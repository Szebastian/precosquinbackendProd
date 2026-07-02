from fastapi import APIRouter
from app.api.v1.endpoints import (
    auth,
    inscriptions,
    artists,
    schedule,
    jury,
    staff,
    notifications,
    contracts,
    reports,
    admin,
    dashboard,
    categories,
    storage,
    news,
)

api_router = APIRouter()

# Auth
api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])

# Dashboard
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])

# Inscriptions
api_router.include_router(inscriptions.router, prefix="/inscriptions", tags=["Inscriptions"])

# Artists
api_router.include_router(artists.router, prefix="/artists", tags=["Artists"])

# Categories
api_router.include_router(categories.router, prefix="/categories", tags=["Categories"])

# Schedule
api_router.include_router(schedule.router, prefix="/schedule", tags=["Schedule"])

# Jury
api_router.include_router(jury.router, prefix="/jury", tags=["Jury"])

# Staff
api_router.include_router(staff.router, prefix="/staff", tags=["Staff"])

# Notifications
api_router.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])

# Contracts
api_router.include_router(contracts.router, prefix="/contracts", tags=["Contracts"])

# Reports
api_router.include_router(reports.router, prefix="/reports", tags=["Reports"])

# Admin
api_router.include_router(admin.router, prefix="/admin", tags=["Admin"])

# Storage
api_router.include_router(storage.router, prefix="/storage", tags=["Storage"])

# News
api_router.include_router(news.router, prefix="/news", tags=["News"])