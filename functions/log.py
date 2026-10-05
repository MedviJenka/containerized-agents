from dataclasses import dataclass
from typing import Literal
import logfire
from settings import Config

LogLevel = Literal["info", "error", "debug", "warning", "fatal"]


@dataclass
class Logger:

    name: str

    def __post_init__(self) -> None:
        self.config = logfire.configure(token=Config.LOGFIRE_WRITE_TOKEN)

    def fire(self, message: str, level: LogLevel | None = 'info', **attributes: object) -> None:
        with self.config.span(self.name):
            match level:
                case "info":
                    self.config.info(message, **attributes)
                case "error":
                    self.config.error(message, **attributes)
                case "debug":
                    self.config.debug(message, **attributes)
                case "warning":
                    self.config.warning(message, **attributes)
                case "fatal":
                    self.config.fatal(message, **attributes)
                case _:
                    self.config.info(message, **attributes)


if __name__ == "__main__":
    logger = Logger(name="app")
    logger.fire(message="hi")
