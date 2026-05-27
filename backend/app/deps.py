from backend.app.services.progress import ProgressBus, get_progress_bus


def get_bus() -> ProgressBus:
    return get_progress_bus()