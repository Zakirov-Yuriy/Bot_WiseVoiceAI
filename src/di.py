"""Dependency Injection Container для управления зависимостями приложения"""

from dependency_injector import containers, providers
from .services import (
    AssemblyAITranscriptionService,
    YooMoneyPaymentService,
    LocalFileProcessingService,
    TranscriptionServiceInterface,
    PaymentServiceInterface,
    FileProcessingServiceInterface
)
from . import database


class Container(containers.DeclarativeContainer):
    """Главный DI контейнер приложения"""

    # Database provider
    database = providers.Resource(database.init_db)

    # Service providers
    transcription_service = providers.Singleton(
        AssemblyAITranscriptionService
    )

    payment_service = providers.Singleton(
        YooMoneyPaymentService
    )

    file_processing_service = providers.Singleton(
        LocalFileProcessingService
    )


# Глобальный экземпляр контейнера
container = Container()

# Функции для получения сервисов
def get_transcription_service() -> TranscriptionServiceInterface:
    """Получить сервис транскрибации"""
    return container.transcription_service()

def get_payment_service() -> PaymentServiceInterface:
    """Получить сервис платежей"""
    return container.payment_service()

def get_file_processing_service() -> FileProcessingServiceInterface:
    """Получить сервис обработки файлов"""
    return container.file_processing_service()

# Инициализация контейнера
def init_container():
    """Инициализировать DI контейнер"""
    container.init_resources()
