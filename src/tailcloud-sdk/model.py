from dataclasses import dataclass, field
from typing import Literal, Callable, Any
import logging
import json
import sys
from dataclasses import asdict, is_dataclass
from enum import Enum
import traceback

def serialize(obj):
    if is_dataclass(obj):
        return {
            key: serialize(value)
            for key, value in asdict(obj).items()
            if key != "func"
        }

    if isinstance(obj, Enum):
        return obj.value

    if isinstance(obj, dict):
        return {
            key: serialize(value)
            for key, value in obj.items()
        }

    if isinstance(obj, (list, tuple, set)):
        return [serialize(value) for value in obj]

    if hasattr(obj, "__dict__"):
        return {
            key: serialize(value)
            for key, value in obj.__dict__.items()
            if key != "func"
        }

    return obj

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)

@dataclass
class Result:
    title: str
    description: str | None = None
    status: Literal["OK", "ERROR", "WARNING"] = "OK"
    button: str | None = None

@dataclass
class Field:
    id: str
    name: str
    type: Literal["str", "int", "bool"] = "str"
    description: str | None = None
    required: bool = False
    default: str | int | bool | None = None

@dataclass
class Command:
    id: str
    title: str
    color: Literal["Primary", "Red", "Gray"] = "Primary"
    description: str | None = None
    fields: list[Field] = field(default_factory=list)
    func: Callable = lambda: None


class TailModel:
    def __init__(self, debug: bool = False):
        self._commands: dict[str, Command] = {}
        self._install: Command = None

        self.debug = debug

    def command(self, command_data: Command):
        if not isinstance(command_data, Command):
            raise TypeError("request must be an instance of Command")

        logging.debug(f'Command "{command_data.title}" init')

        def decorator(func: Callable):
            command_data.func = func
            self._commands[command_data.id] = command_data
            return func

        return decorator

    def install(self, command_data: Command):
        if not isinstance(command_data, Command):
            raise TypeError("request must be an instance of Command")

        logging.debug(f'Install "{command_data.title}" init')

        def decorator(func: Callable):
            command_data.func = func
            self._install = command_data
            return func

        return decorator

    def __view_result(self, result):
        result = serialize(result)
        print(f"result={json.dumps(result, ensure_ascii=False)}")
        return result

    def init(self):
        result = {
            "commands": self._commands,
            "result": None
        }

        argv = sys.argv[1:]

        logging.debug(f"Result init - {result}")
        logging.debug(f"Arg - {argv}")

        if argv[0] == 'command' and len(argv) in [2, 3]:
            command_id = argv[1]
            command_args = json.loads(argv[2]) if len(argv) == 3 else {}

            if not self._commands.get(command_id):
                result['result'] = Result(
                    status="ERROR",
                    title="Функция не найдена",
                    description="Возможно скрипт повредился, переустановите и попробуйте снова"
                ).__dict__
                return self.__view_result(result)

            try:
                command_result = self._install.func(**command_args)
            except:
                command_result = Result(
                    status="ERROR",
                    title="Ошибка функции",
                    description=f"```{traceback.format_exc()}```"
                )
            if not isinstance(command_result, Result):
                command_result = Result("Скрипт ничего не ответил")
            result['result'] = command_result.__dict__
            return self.__view_result(result)
        elif argv[0] == 'install':
            command_args = json.loads(argv[1]) if len(argv) == 2 else {}
            if self._install is None:
                return self.__view_result(result)

            try:
                command_result = self._install.func(**command_args)
            except:
                command_result = Result(
                    status="ERROR",
                    title="Ошибка функции",
                    description=f"```{traceback.format_exc()}```"
                )
                
            if not isinstance(command_result, Result):
                command_result = None
            result['result'] = command_result.__dict__
            return self.__view_result(result)
