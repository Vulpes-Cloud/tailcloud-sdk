# TailCloud SDK

Python SDK для интеграций, которые устанавливают ПО и управляют им на серверах
TailCloud. Интеграция описывает доступные действия и поля формы, а SDK проверяет
параметры, вызывает обработчик и возвращает JSON-ответ агенту.

Python 3.10+, без обязательных внешних зависимостей. SDK выполняется **локально
на целевом сервере**: подключение по SSH, доставка скриптов и авторизация остаются
за агентом TailCloud. Помощники установки рассчитаны на Linux.

## Установка из исходников

```bash
python -m pip install -e .
```

Имя дистрибутива — `tailcloud-sdk`, импорт — `tailcloud_sdk`.
Старый импорт `tailcloudSDK.model` из первоначального примера тоже поддерживается.

## Первая интеграция

```python
from tailcloud_sdk import Command, Field, Result, TailModel

model = TailModel()


@model.command(
    Command(
        id="greet",
        title="Приветствие",
        fields=[Field("name", "Имя", required=True)],
    )
)
def greet(name: str) -> Result:
    return Result("Готово", description=f"Привет, {name}!")


if __name__ == "__main__":
    model.init()
```

Сохраните как `integration.py`. Примеры команд для Bash:

```bash
python integration.py                        # описание доступных действий
python integration.py describe               # то же самое
python integration.py command greet '{"name": "Алексей"}'
```

Python API не печатает протокольный ответ:

```python
result = model.execute("command", {"name": "Алексей"}, command_id="greet")
metadata = model.describe()
```

## Действия и поля

Кроме `@model.command(...)`, доступны декораторы `install`, `update`, `uninstall`
и `status`. Все принимают `Command` и используют одинаковую проверку параметров.
Повторная регистрация одного действия, несовместимая сигнатура обработчика и
повторяющиеся поля приводят к ошибке при регистрации.

| Поле `Field` | Назначение |
| --- | --- |
| `id`, `name` | Имя аргумента Python и подпись в интерфейсе |
| `type` | `str`, `int` или `bool`; без неявного преобразования значений |
| `required` | Обязательное значение; обязательная строка не может быть пустой |
| `default` | Значение по умолчанию; `None` означает отсутствие значения |
| `choices` | Список или кортеж допустимых значений |
| `minimum`, `maximum` | Включительные границы для целых чисел |
| `secret` | Подсказка интерфейсу для скрытого ввода |
| `description` | Пояснение для пользователя |

Передавайте числа и логические значения соответствующими типами JSON:
`{"port": 8080, "enabled": false}`. `true` не принимается как целое число.
Неизвестные поля и явный `null` отклоняются до вызова обработчика.
Если необязательное поле не передано и у него нет `default`, SDK опускает аргумент;
обработчик должен иметь собственное значение по умолчанию.

`secret` — метаданные для интерфейса, а не шифрование или фильтр произвольного
вывода. Не помещайте пароли в `default`, `Result.data` и сообщения журнала.

Обработчик возвращает `Result` со статусом `OK`, `WARNING` или `ERROR`.
`description` и `button` сохраняют исходный формат, `data` позволяет вернуть
дополнительные JSON-данные. Возврат `None` означает успешное завершение без
дополнительных данных; другой тип возвращаемого значения считается ошибкой.
Поддерживаются синхронные обработчики.

## Запуск системных команд

```python
from tailcloud_sdk import ExecutionError, Runner

runner = Runner(timeout=60)
try:
    result = runner.run(["nginx", "-t"])
except ExecutionError as error:
    # Для завершившегося процесса доступны stdout, stderr и returncode.
    failed_process = error.result

preview = Runner(dry_run=True).run(["systemctl", "restart", "nginx"])
assert preview.skipped
assert preview.returncode is None
assert not preview.ok  # процесс не выполнялся
```

Аргументы передаются списком, без shell-интерпретации. `check=False` позволяет
самостоятельно обработать ненулевой код завершения. Таймаут и ошибка запуска
всегда вызывают `ExecutionError`. `env` дополняет окружение процесса, `cwd` задаёт
рабочую папку. SDK не вызывает `sudo`: права задаёт запускающий агент.

Вывод процесса сохраняется в памяти; `Runner` предназначен для конечных команд,
а не бесконечного чтения журналов. Таймаут завершает непосредственный процесс;
управление всем деревом дочерних процессов не реализовано. Dry-run отключает
только процессы, запускаемые через этот `Runner`, а не произвольный код обработчика.

## Пакеты Linux и службы

```python
from tailcloud_sdk import PackageManager, Runner, SystemdService

runner = Runner(timeout=600)
packages = PackageManager(runner)  # apt-get → dnf → yum → apk, по наличию в PATH
packages.refresh()
packages.install("nginx")
packages.upgrade("nginx")

service = SystemdService(runner, "nginx")
service.enable(now=True)
service.reload()
active = service.is_active()  # True / False; None при dry-run
```

Можно явно выбрать `PackageManager(runner, backend="apt-get")`. Повторная установка
пакета выполняется штатным менеджером пакетов; SDK не ведёт собственную базу
установленного ПО. `refresh()` вызывается явно. `install`, `upgrade` и `remove`
требуют конкретных имён пакетов, без шаблонов, путей и параметров командной строки.
Менеджер пакетов самостоятельно разрешает зависимости. Для apt обновление
использует `--only-upgrade`, для остальных — `upgrade` с именами пакетов.

`SystemdService` поддерживает `start`, `stop`, `restart`, `reload`, `enable`,
`disable`, `status` и `is_active`. `status()` возвращает полный `CommandResult`:
неактивная служба может иметь ненулевой код. `is_active()` отличает неактивную или
отсутствующую службу от ошибки обращения к systemd. На сервере нужен systemd;
например, наличие `apk` само по себе не означает наличие systemd.

Полная интеграция: [examples/nginx.py](examples/nginx.py). На Linux с systemd:

```bash
python examples/nginx.py describe
python examples/nginx.py install '{"refresh": true}'
python examples/nginx.py status
python examples/nginx.py command restart
python examples/nginx.py update
python examples/nginx.py uninstall
```

Проверка сценария без запуска процессов, в том числе на Windows:

```powershell
$env:TAILCLOUD_DRY_RUN = "1"
$env:TAILCLOUD_PACKAGE_MANAGER = "apt-get"
python examples/nginx.py install
```

Для Bash: `TAILCLOUD_DRY_RUN=1 TAILCLOUD_PACKAGE_MANAGER=apt-get python examples/nginx.py install`.
Пример возвращает `WARNING` при dry-run, чтобы отличить его от реальной установки.

## Протокол агента

`model.init(argv=None)` читает `sys.argv[1:]`, печатает одну строку
`result=<JSON>` и возвращает тот же словарь. Можно передать список аргументов
явно, например `model.init(["status"])`.

```json
{
  "commands": {},
  "install": {"id": "install", "title": "Установка", "color": "Primary", "description": null, "fields": []},
  "result": {"title": "Готово", "description": null, "status": "OK", "button": null, "data": null}
}
```

`commands` всегда содержит словарь обычных команд. Зарегистрированные операции
жизненного цикла добавляются отдельными ключами: `install`, `update`, `uninstall`,
`status`. При запросе описания `result` равен `null`. Функции в JSON не попадают.
Новые ключи и метаданные потребуют поддержки в интерфейсе TailCloud.

Пустые аргументы возвращают описание; неверный JSON, неизвестная команда,
неверные параметры и исключения обработчика возвращают `result.status = "ERROR"`.
Код завершения Python не заменяет протокольный статус: агент читает `result.status`.
`KeyboardInterrupt` и `SystemExit` не перехватываются.

Обычный `print()` внутри обработчика при CLI-вызове направляется в stderr.
Это перенаправление относится к Python stdout и не предназначено для параллельных
вызовов `init()` из потоков. Прямую запись в файловый дескриптор stdout обработчик
должен исключить самостоятельно. Для системных команд используйте `Runner`.

SDK не настраивает глобальное логирование. `TailModel(debug=True)` добавляет
traceback в ответ и журнал ошибок; используйте его только для диагностики,
поскольку текст исключения может содержать секреты.

## Разработка

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python -m pip install build ruff
python -m ruff check .
python -m ruff format --check .
python -m build
```

Тесты проверяют диспетчеризацию, валидацию, протокол, исключения, реальные
безопасные дочерние процессы, таймауты и планы системных команд. Установка
пакетов и управление службами в тестах не выполняются.
