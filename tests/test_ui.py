import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from top_heroes_auto.ui.window import Window


def test_gui_selection_protection_filters_and_close(rig, tmp_path, monkeypatch):
    manager, _, store = rig
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(Window, "discover_ld", lambda self: None)
    window = Window(store, tmp_path)
    window.manager = manager
    window.instances = manager.refresh()
    window.show()
    app.processEvents()
    window.render()
    assert window.table.rowCount() == 2
    assert not window.table.cellWidget(0, 0).isEnabled()
    window.select_visible(True)
    assert not store.metadata(manager.namespace, 0).selected
    window.search.setText("Farm")
    assert window.table.rowCount() == 1
    window.select_visible(False)
    assert window.target.count() == 0
    assert not any(b.isEnabled() for b in window.action_buttons)
    window.close()
    assert store.get("window_geometry")
