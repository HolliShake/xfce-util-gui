import shutil


def detect_polkit() -> str | None:
    return shutil.which("pkexec")
