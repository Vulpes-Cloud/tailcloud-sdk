
import os
import platform
from pathlib import Path

from src.tailcloud_sdk import Command, Field, PackageManager, Result, Runner, SystemdService, TailModel

model = TailModel()
runner = Runner(timeout=600, dry_run=True)
service = SystemdService(runner, "docker")


def check_environment() -> None:
    if runner.dry_run:
        return
    if platform.system() != "Linux":
        raise RuntimeError("Этот пример предназначен для Ubuntu/Debian, не Windows.")
    release = dict(
        line.split("=", 1)
        for line in Path("/etc/os-release").read_text().splitlines()
        if "=" in line
    )
    if release.get("ID", "").strip('"') not in {"ubuntu", "debian"}:
        raise RuntimeError("Этот пример поддерживает только Ubuntu и Debian.")
    if os.geteuid() != 0:
        raise RuntimeError("Запустите действие от root (например, через sudo).")
    if not Path("/run/systemd/system").is_dir():
        raise RuntimeError("Для управления службой Docker необходим systemd.")


@model.install(Command(
    id="install",
    title="Установить Docker",
    fields=[Field("refresh", "Обновить список пакетов", type="bool", default=True)],
))
def install(refresh: bool = True) -> Result:
    check_environment()
    manager = PackageManager(runner, backend="apt-get")
    if refresh:
        manager.refresh()
    manager.install("docker.io")
    service.enable(now=True)
    check = runner.run(["docker", "info"])
    if runner.dry_run:
        return Result("Dry-run завершён", "Изменения не применялись", status="WARNING")
    return Result("Docker установлен и запущен", data={"info": check.stdout})


@model.status(Command("status", "Состояние Docker"))
def status() -> Result:
    check_environment()
    active = service.is_active()
    if active is None:
        return Result("Dry-run завершён", "Состояние не проверялось", status="WARNING")
    return Result(
        "Docker работает" if active else "Docker остановлен или не установлен",
        status="OK" if active else "WARNING",
        data={"active": active},
    )


if __name__ == "__main__":
    model.init()
