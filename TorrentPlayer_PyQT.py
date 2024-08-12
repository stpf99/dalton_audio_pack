import sys
import os
import shutil
import subprocess
import tempfile
import glob
import time
import requests
import json
import shlex
import mpv
import locale
from PyQt5.QtWidgets import (QApplication, QMainWindow, QStackedWidget, QWidget, QVBoxLayout, QHBoxLayout,
                             QLineEdit, QPushButton, QListWidget, QLabel, QMessageBox, QProgressBar,
                             QFileDialog, QListWidgetItem, QSlider)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

# Ustawienie locale
locale.setlocale(locale.LC_NUMERIC, 'C')

# Definicje stałych
HOME_DIR = os.path.expanduser("~")
TORRENTS_DIR = os.path.join(HOME_DIR, "torrents")

# Upewnij się, że katalog istnieje
if not os.path.exists(TORRENTS_DIR):
    os.makedirs(TORRENTS_DIR)

# Funkcje pomocnicze
def truncate_string(s, width):
    return s[:width-3] + '...' if len(s) > width else s

def truncate_filename(filename, max_length=15):
    if len(filename) > max_length:
        name, ext = os.path.splitext(filename)
        truncated_name = name[:max_length - len(ext) - 3]
        return truncated_name + '...' + ext
    return filename

# Funkcja do wyszukiwania torrentów
def search_torrents(query, number_of_results=10, after=None):
    base_url = "https://torrents-csv.com/service/search"
    params = {
        'q': query,
        'size': number_of_results
    }
    if after:
        params['after'] = after
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        data = response.json()
        torrents = data.get('torrents', [])
        next_page = data.get('next', None)
        return torrents, next_page
    except requests.exceptions.RequestException as e:
        return None, None

# Funkcja do pobierania listy trackerów
def fetch_trackers():
    trackers_url = "https://raw.githubusercontent.com/ngosang/trackerslist/master/trackers_all.txt"
    try:
        response = requests.get(trackers_url)
        response.raise_for_status()
        trackers = response.text.splitlines()
        return trackers
    except requests.exceptions.RequestException as e:
        return []

# Funkcja do zapisywania informacji o torrencie
def save_torrent_info(torrent):
    filename = f"{torrent['name']}.json"
    file_path = os.path.join(TORRENTS_DIR, filename)
    with open(file_path, 'w') as f:
        json.dump(torrent, f, indent=4)
    return file_path

# Klasa wątku do pobierania metadanych
class MetadataDownloadThread(QThread):
    progress_update = pyqtSignal(str)
    download_complete = pyqtSignal(bool, str)

    def __init__(self, infohash, name):
        QThread.__init__(self)
        self.infohash = infohash
        self.name = name

    def run(self):
        trackers = fetch_trackers()
        if not trackers:
            self.download_complete.emit(False, "Failed to fetch trackers.")
            return

        magnet_link = f"magnet:?xt=urn:btih:{self.infohash}&dn={self.name}"
        tracker_params = "&".join(f"tr={tracker}" for tracker in trackers if tracker)
        torrent_filename = f"{self.infohash}.torrent"

        command = [
            "aria2c",
            "--bt-metadata-only=true",
            "--bt-save-metadata=true",
            "--dir=" + TORRENTS_DIR,
            "--out=" + torrent_filename,
            f"{magnet_link}&{tracker_params}"
        ]

        try:
            self.progress_update.emit(f"Downloading metadata for {self.name}...")
            result = subprocess.run(command, check=True, text=True, capture_output=True)
            new_filename = f"{self.name}.torrent"
            os.rename(os.path.join(TORRENTS_DIR, torrent_filename),
                      os.path.join(TORRENTS_DIR, new_filename))
            self.download_complete.emit(True, f"Download complete: {new_filename}")
        except subprocess.CalledProcessError as e:
            self.download_complete.emit(False, f"Error while running aria2c: {e}")

# Klasa MPVPlayer do obsługi odtwarzania wideo
class MPVPlayer(mpv.MPV):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.loop = True
        self.force_window = True

# Główne okno aplikacji
class TorrentPlayerGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Torrent Player')
        self.setGeometry(100, 100, 1280, 720)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        self.stacked_widget = QStackedWidget()
        layout.addWidget(self.stacked_widget)

        self.search_widget = SearchWidget(self)
        self.results_widget = ResultsWidget(self)
        self.file_list_widget = FileListWidget(self)
        self.player_widget = PlayerWidget(self)

        self.stacked_widget.addWidget(self.search_widget)
        self.stacked_widget.addWidget(self.results_widget)
        self.stacked_widget.addWidget(self.file_list_widget)
        self.stacked_widget.addWidget(self.player_widget)

        self.stacked_widget.setCurrentWidget(self.search_widget)

        self.create_menu()

    def play_torrent(self, file_path):
        self.player_widget.play_torrent(file_path)
        self.stacked_widget.setCurrentWidget(self.player_widget)

    def create_menu(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu('File')

        search_action = file_menu.addAction('Search Torrents')
        search_action.triggered.connect(self.show_search)

        list_action = file_menu.addAction('List Available Torrents')
        list_action.triggered.connect(self.show_torrent_list)

    def show_search(self):
        self.stacked_widget.setCurrentWidget(self.search_widget)

    def show_torrent_list(self):
        self.file_list_widget.load_local_torrents()
        self.stacked_widget.setCurrentWidget(self.file_list_widget)

    def closeEvent(self, event):
        self.file_list_widget.unmount_torrent()
        super().closeEvent(event)

class SearchWidget(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.main_window = parent  # Zapisz referencję do głównego okna
        layout = QVBoxLayout(self)
        self.search_input = QLineEdit(self)
        self.search_button = QPushButton('Search', self)
        layout.addWidget(self.search_input)
        layout.addWidget(self.search_button)

        self.search_button.clicked.connect(self.perform_search)

    def perform_search(self):
        query = self.search_input.text()
        torrents, next_page = search_torrents(query)
        if torrents is None:
            QMessageBox.warning(self, "Error", "Failed to fetch torrents.")
        else:
            self.main_window.results_widget.display_results(torrents, next_page)
            self.main_window.stacked_widget.setCurrentWidget(self.main_window.results_widget)

class ResultsWidget(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.results_list = QListWidget(self)
        layout.addWidget(self.results_list)

        self.download_button = QPushButton('Download Selected', self)
        self.download_button.clicked.connect(self.download_selected)
        layout.addWidget(self.download_button)

        self.next_page_button = QPushButton('Next Page', self)
        self.next_page_button.clicked.connect(self.load_next_page)
        layout.addWidget(self.next_page_button)

        self.current_query = ""
        self.next_page = None

    def display_results(self, torrents, next_page):
        self.results_list.clear()
        for torrent in torrents:
            item = QListWidgetItem(torrent['name'])
            item.setData(Qt.UserRole, torrent)
            self.results_list.addItem(item)
        self.next_page = next_page
        self.next_page_button.setEnabled(next_page is not None)

    def download_selected(self):
        selected_items = self.results_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Warning", "No torrent selected.")
            return

        torrent = selected_items[0].data(Qt.UserRole)
        self.download_thread = MetadataDownloadThread(torrent['infohash'], torrent['name'])
        self.download_thread.progress_update.connect(self.update_progress)
        self.download_thread.download_complete.connect(self.download_finished)
        self.download_thread.start()

    def update_progress(self, message):
        QMessageBox.information(self, "Download Progress", message)

    def download_finished(self, success, message):
        if success:
            QMessageBox.information(self, "Download Complete", message)
        else:
            QMessageBox.warning(self, "Download Failed", message)

    def load_next_page(self):
        if self.next_page:
            torrents, self.next_page = search_torrents(self.current_query, after=self.next_page)
            if torrents is not None:
                self.display_results(torrents, self.next_page)
            else:
                QMessageBox.warning(self, "Error", "Failed to fetch next page.")


class PlaylistWidget(QWidget):
    play_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.file_list = QListWidget(self)
        self.layout.addWidget(self.file_list)

        self.file_list.itemDoubleClicked.connect(self.play_selected)

    def load_content(self, directory):
        self.file_list.clear()
        for root, dirs, files in os.walk(directory):
            for file in files:
                full_path = os.path.join(root, file)
                relative_path = os.path.relpath(full_path, directory)
                item = QListWidgetItem(relative_path)
                item.setData(Qt.UserRole, full_path)
                self.file_list.addItem(item)

    def play_selected(self, item):
        file_path = item.data(Qt.UserRole)
        self.play_requested.emit(file_path)

class FileListWidget(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.main_window = parent
        layout = QVBoxLayout(self)
        self.file_list = QListWidget(self)
        layout.addWidget(self.file_list)

        self.playlist_widget = PlaylistWidget(self)
        layout.addWidget(self.playlist_widget)

        self.file_list.itemClicked.connect(self.load_torrent_content)
        self.playlist_widget.play_requested.connect(self.play_file)

        self.mountpoint = None

    def load_local_torrents(self):
        self.file_list.clear()
        torrent_files = glob.glob(os.path.join(TORRENTS_DIR, '*.torrent'))
        for file in torrent_files:
            item = QListWidgetItem(os.path.basename(file))
            item.setData(Qt.UserRole, file)
            self.file_list.addItem(item)

    def load_torrent_content(self, item):
        torrent_file = item.data(Qt.UserRole)
        self.mount_and_list_torrent(torrent_file)

    def mount_and_list_torrent(self, torrent_file):
        if self.mountpoint:
            self.unmount_torrent()

        self.mountpoint = tempfile.mkdtemp(prefix="btplay-")
        try:
            mount_command = ["btfs", torrent_file, self.mountpoint]
            subprocess.run(mount_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            if not os.path.ismount(self.mountpoint):
                raise Exception("BTFS mount failed")

            self.playlist_widget.load_content(self.mountpoint)
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))
            self.unmount_torrent()

    def unmount_torrent(self):
        if self.mountpoint:
            try:
                subprocess.run(["fusermount", "-u", self.mountpoint], check=True)
                shutil.rmtree(self.mountpoint)
            except Exception as e:
                QMessageBox.warning(self, "Cleanup Error", f"Error during cleanup: {str(e)}")
            finally:
                self.mountpoint = None

    def play_file(self, file_path):
        self.main_window.play_torrent(file_path)

    def closeEvent(self, event):
        self.unmount_torrent()
        super().closeEvent(event)

class PlayerWidget(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        self.mpv_widget = QWidget(self)
        layout.addWidget(self.mpv_widget)

        self.player = MPVPlayer(wid=str(int(self.mpv_widget.winId())))

        controls_layout = QHBoxLayout()
        self.play_pause_button = QPushButton("Play/Pause")
        self.stop_button = QPushButton("Stop")
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)

        controls_layout.addWidget(self.play_pause_button)
        controls_layout.addWidget(self.stop_button)
        controls_layout.addWidget(QLabel("Volume:"))
        controls_layout.addWidget(self.volume_slider)

        layout.addLayout(controls_layout)

        self.play_pause_button.clicked.connect(self.toggle_play_pause)
        self.stop_button.clicked.connect(self.stop)
        self.volume_slider.valueChanged.connect(self.set_volume)

    def play_torrent(self, file_path):
        self.player.play(file_path)

    def toggle_play_pause(self):
        self.player.pause = not self.player.pause

    def stop(self):
        self.player.stop()

    def set_volume(self, value):
        self.player.volume = value

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = TorrentPlayerGUI()
    ex.show()
    sys.exit(app.exec_())
