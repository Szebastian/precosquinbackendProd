from fastapi import APIRouter
from app.api.v1.endpoints import (
    auth,
    inscriptions,
    artists,
    schedule,
    jury,
    staff,
    notifications,
    communications,
    contracts,
    reports,
    admin,
    dashboard,
    categories,
    storage,
    news,
    messages,
    email_webhook,
    cronograma,
    acreditaciones,
    gallery,
    stands,
    chat,
    pena_acreditaciones,
    sorteo_avistaje,
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

# Communications (email send/schedule/jobs)
api_router.include_router(communications.router, prefix="/communications", tags=["Communications"])

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

# Messages (contact form)
api_router.include_router(messages.router, prefix="/messages", tags=["Messages"])

# Email webhook (incoming emails from ForwardEmail)
api_router.include_router(email_webhook.router, prefix="/email", tags=["Email Webhook"])

# Cronograma
api_router.include_router(cronograma.router, prefix="/cronograma", tags=["Cronograma"])

# Acreditaciones
api_router.include_router(acreditaciones.router, prefix="/acreditaciones", tags=["Acreditaciones"])

# Gallery
api_router.include_router(gallery.router, prefix="/gallery", tags=["Gallery"])

# Stands
api_router.include_router(stands.router, prefix="/stands", tags=["Stands"])

# Chat (AI chatbot)
api_router.include_router(chat.router, prefix="/chat", tags=["Chat"])

# Peña Acreditaciones (público + admin)
api_router.include_router(pena_acreditaciones.router, prefix="/pena-acreditaciones", tags=["Peña Acreditaciones"])

# Sorteo Avistaje de Ballenas (público + admin)
api_router.include_router(sorteo_avistaje.router, prefix="/sorteo-avistaje", tags=["Sorteo Avistaje"])