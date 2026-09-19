"""Run on a Linux server: python examples/nginx.py install '{"refresh": true}'."""

import os

from tailcloud_sdk import Command, Field, PackageManager, Result, Runner, SystemdService, TailModel

model = TailModel()
runner = Runner(dry_run=os.environ.get("TAILCLOUD_DRY_RUN") == "1")
service = SystemdService(runner, "nginx")


def packages() -> PackageManager:
    # Explicit backend also makes previews possible on development machines.
    return PackageManager(runner, backend=os.environ.get("TAILCLOUD_PACKAGE_MANAGER"))


def completed(title: str) -> Result:
    if runner.dry_run:
        return Result("Проверка dry-run завершена", "Изменения не применялись", status="WARNING")
    return Result(title)


@model.install(
    Command(
        id="install",
        title="Установить Nginx",
        fields=[Field("refresh", "Обновить список пакетов", type="bool", default=True)],
    )
)
def install(refresh: bool) -> Result:
    manager = packages()
    if refresh:
        manager.refresh()
    manager.install("nginx")
    service.enable(now=True)
    return completed("Nginx установлен и запущен")


@model.update(Command("update", "Обновить Nginx"))
def update() -> Result:
    packages().upgrade("nginx")
    service.restart()
    return completed("Nginx обновлён")


@model.uninstall(Command("uninstall", "Удалить Nginx", color="Red"))
def uninstall() -> Result:
    service.disable(now=True)
    packages().remove("nginx")
    return completed("Nginx удалён")


@model.status(Command("status", "Состояние Nginx"))
def status() -> Result:
    active = service.is_active()
    if active is None:
        return completed("Состояние Nginx")
    return Result(
        "Nginx работает" if active else "Nginx остановлен или не установлен",
        status="OK" if active else "WARNING",
        data={"active": active},
    )


@model.command(Command("restart", "Перезапустить Nginx"))
def restart() -> Result:
    service.restart()
    return completed("Nginx перезапущен")


if __name__ == "__main__":
    model.init()
