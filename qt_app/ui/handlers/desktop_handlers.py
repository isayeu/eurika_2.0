"""Launch the standalone Eurika Desktop shell from the legacy Qt client."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QMessageBox

from qt_app.services.desktop_launcher import desktop_launch_spec

if TYPE_CHECKING:
    from ..main_window import MainWindow


def launch_desktop(main: MainWindow) -> None:
    spec = desktop_launch_spec(main.root_edit.text().strip() or ".")
    error = spec.get("error")
    if error:
        QMessageBox.warning(main, "Eurika Desktop", str(error))
        main.status_label.setText(str(error))
        return
    try:
        subprocess.Popen(
            [str(spec["program"]), *[str(item) for item in spec.get("args", [])]],
            cwd=str(spec["cwd"]),
            env=spec["env"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        QMessageBox.warning(main, "Eurika Desktop", f"Не удалось запустить: {exc}")
        main.status_label.setText(f"Desktop launch failed: {exc}")
        return
    main.status_label.setText(
        f"Eurika Desktop запущена ({spec.get('source', 'launcher')})"
    )
