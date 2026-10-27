"""List model feeding the project tiles."""

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt


class ProjectModel(QAbstractListModel):
    IdRole = Qt.ItemDataRole.UserRole + 1
    NameRole = IdRole + 1
    ColorRole = IdRole + 2
    TodayRole = IdRole + 3
    ElapsedRole = IdRole + 4
    RunningRole = IdRole + 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[dict] = []

    def roleNames(self):
        return {
            self.IdRole: b"projectId",
            self.NameRole: b"projectName",
            self.ColorRole: b"tileColor",
            self.TodayRole: b"today",
            self.ElapsedRole: b"elapsed",
            self.RunningRole: b"running",
        }

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        row = self._rows[index.row()]
        return {
            self.IdRole: row["id"],
            self.NameRole: row["name"],
            self.ColorRole: row["color"],
            self.TodayRole: row["today"],
            self.ElapsedRole: row["elapsed"],
            self.RunningRole: row["running"],
        }.get(role)

    def project_id(self, row: int) -> int:
        return self._rows[row]["id"]

    def set_projects(self, projects: list[dict]) -> None:
        self.beginResetModel()
        self._rows = [dict(p, today=0, elapsed=0, running=False) for p in projects]
        self.endResetModel()

    def set_times(self, today: dict[int, int], running_id: int | None, elapsed: int) -> None:
        """Update the live columns without resetting the view."""
        for r in self._rows:
            r["today"] = today.get(r["id"], 0)
            r["running"] = r["id"] == running_id
            r["elapsed"] = elapsed if r["running"] else 0
        if self._rows:
            self.dataChanged.emit(
                self.index(0), self.index(len(self._rows) - 1),
                [self.TodayRole, self.ElapsedRole, self.RunningRole],
            )
