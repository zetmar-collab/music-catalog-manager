import time
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from music_catalog_manager.ui.worker import Worker


def test_event_loop_responsive_and_cancel():
    app = QApplication.instance() or QApplication([])
    ticks = []
    results = []
    def work(cancel, progress):
        for i in range(1000):
            if cancel.wait(0.01):
                return i
        return 1000
    worker = Worker(work)
    worker.result.connect(results.append)
    loop = QEventLoop()
    timer = QTimer()
    timer.setInterval(10)
    timer.timeout.connect(lambda: ticks.append(time.monotonic()))
    timer.start()
    QTimer.singleShot(100, worker.cancel.set)
    QTimer.singleShot(3000, loop.quit)
    worker.finished.connect(loop.quit)
    worker.start()
    loop.exec()
    timer.stop()
    worker.wait(1000)
    assert len(ticks) >= 3
    assert results and results[0] < 100


def test_finished_callback_can_start_next_job(tmp_path):
    from music_catalog_manager.database.store import Store
    from music_catalog_manager.ui.window import MainWindow
    app = QApplication.instance() or QApplication([])
    window = MainWindow(Store(tmp_path))
    loop = QEventLoop()
    results = []
    def first_done(value):
        results.append(value)
        window.start(lambda cancel, progress: 'second', lambda result: (results.append(result), loop.quit()))
    window.start(lambda cancel, progress: 'first', first_done)
    QTimer.singleShot(3000, loop.quit)
    loop.exec()
    app.processEvents()
    assert results == ['first', 'second']
    assert window.worker is None
    window.close()


def test_real_window_scans_in_background_and_cancels(tmp_path, audio_factory, monkeypatch):
    from music_catalog_manager.database.store import Store
    from music_catalog_manager.ui.window import MainWindow
    from music_catalog_manager.services import metadata
    from PySide6.QtWidgets import QMessageBox
    app = QApplication.instance() or QApplication([])
    root = tmp_path / 'music'
    for i in range(30):
        audio_factory(root / (str(i) + '.wav'))
    read = metadata.read
    def slow_read(path):
        time.sleep(0.01)
        return read(path)
    monkeypatch.setattr(metadata, 'read', slow_read)
    monkeypatch.setattr(QMessageBox, 'information', lambda *args: QMessageBox.Ok)
    store = Store(tmp_path / 'profile')
    rid = store.add_root(root)
    window = MainWindow(store)
    loop = QEventLoop()
    ticks = []
    timer = QTimer()
    timer.setInterval(10)
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start()
    window.scan_roots([{'id': rid}])
    window.worker.finished.connect(loop.quit)
    QTimer.singleShot(70, window.cancel)
    QTimer.singleShot(5000, loop.quit)
    loop.exec()
    timer.stop()
    app.processEvents()
    assert len(ticks) >= 3
    assert 0 < len(store.tracks()) < 30
    assert window.worker is None
    window.scan_roots([{'id': rid}])
    window.worker.finished.connect(loop.quit)
    QTimer.singleShot(5000, loop.quit)
    loop.exec()
    app.processEvents()
    assert len(store.tracks()) == 30
    from PySide6.QtTest import QTest
    deadline = time.monotonic() + 5
    while window.loading_library and time.monotonic() < deadline:
        QTest.qWait(10)
        time.sleep(0.001)
    assert window.proxy.rowCount() == 30
    window.close()
