import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_ROOT = Path("logs")
JARVIS_DIR = LOG_ROOT / "Jarvis"
MCP_DIR = LOG_ROOT / "mcp"
AGENTS_DIR = LOG_ROOT / "Agents"

_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_MAX_BYTES = 2_000_000
_BACKUP_COUNT = 5


def _build_logger(name: str, log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.ERROR)
    handler = RotatingFileHandler(
        log_path,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(logging.ERROR)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def get_jarvis_logger() -> logging.Logger:
    return _build_logger("jarvis", JARVIS_DIR / "jarvis.log")


def get_mcp_logger(mcp_name: str) -> logging.Logger:
    safe_name = mcp_name.lower().removesuffix("_mcp").removesuffix("mcp")
    return _build_logger(f"mcp.{safe_name}", MCP_DIR / f"{safe_name}.log")


def get_agent_logger(agent_name: str) -> logging.Logger:
    safe_name = agent_name.lower().removesuffix("_agent").removesuffix("agent")
    return _build_logger(f"agent.{safe_name}", AGENTS_DIR / f"{safe_name}.log")


def install_global_exception_hook() -> None:
    """Route uncaught exceptions to the Jarvis log."""
    jarvis_log = get_jarvis_logger()
    original_hook = sys.excepthook

    def _hook(exc_type, exc_value, exc_tb):
        if exc_type is KeyboardInterrupt:
            original_hook(exc_type, exc_value, exc_tb)
            return
        jarvis_log.critical(
            "Uncaught exception",
            exc_info=(exc_type, exc_value, exc_tb),
        )
        original_hook(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook
