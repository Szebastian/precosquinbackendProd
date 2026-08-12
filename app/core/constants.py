from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    ORGANIZADOR = "organizador"
    STAFF = "staff"
    JURADO = "jurado"
    GESTOR_STANDS = "gestor_stands"


class InscriptionStatus(str, Enum):
    PENDIENTE = "PENDIENTE"
    EN_REVISION = "EN_REVISION"
    APROBADA = "APROBADA"
    RECHAZADA = "RECHAZADA"
    CONTRATO_FIRMADO = "CONTRATO_FIRMADO"
