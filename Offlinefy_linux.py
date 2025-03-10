from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QLabel, QLineEdit, QTextEdit, QFileDialog
from PyQt6.QtGui import QFont
from PyQt6.QtCore import QThread, pyqtSignal
import sys, os, pathlib, yt_dlp, zipfile, shutil
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1
from cryptography.fernet import Fernet

# Load environment variables
load_dotenv()

# Decrypt Spotify credentials
key = os.getenv('KEY').encode()
cipher = Fernet(key)
encrypted_credentials = os.getenv('ENCRYPTED_KEY').encode()
cid, secret = cipher.decrypt(encrypted_credentials).decode().split(':')
client_credentials_manager = SpotifyClientCredentials(client_id=cid, client_secret=secret)
sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)

# Set default download directory
DEFAULT_DOWNLOAD_DIR = pathlib.Path.home() / "Music"
DEFAULT_DOWNLOAD_DIR.mkdir(exist_ok=True)

class DownloadThread(QThread):
    update_signal = pyqtSignal(str)

    def __init__(self, url, download_directory):
        super().__init__()
        self.url = url
        self.download_directory = download_directory

    def run(self):
        try:
            queries = self.get_queries(self.url)
            
            if queries is None:
                self.update_signal.emit("Invalid URL or failed to fetch song details.")
                return
            
            if isinstance(queries, tuple):  # Playlist case
                tracks, playlist_name = queries
                playlist_dir = pathlib.Path(self.download_directory) / playlist_name
                playlist_dir.mkdir(exist_ok=True)
                
                for song_name, artist_name in tracks:
                    self.download_song(song_name, artist_name, playlist_dir)
                
                zip_path = str(playlist_dir) + ".zip"
                with zipfile.ZipFile(zip_path, 'w') as zipf:
                    for file in playlist_dir.glob("*.mp3"):
                        zipf.write(file, file.name)
                
                shutil.rmtree(playlist_dir)
                self.update_signal.emit(f"Playlist '{playlist_name}' downloaded and zipped successfully!")
            
            else:  # Single song case
                song_name, artist_name = queries[0]
                self.download_song(song_name, artist_name, self.download_directory)
        
        except Exception as e:
            self.update_signal.emit(f'Error: {e}')
    
    def get_queries(self, url):
        """Extract song name and artist from Spotify track or playlist URL."""
        try:
            if 'open.spotify.com/track/' in url:
                track_id = url.split('/')[-1].split('?')[0]
                track = sp.track(track_id)
                song_name = track["name"].replace("/", "-")
                artist_name = track["artists"][0]["name"].replace("/", "-")
                return [(song_name, artist_name)]

            elif 'open.spotify.com/playlist/' in url:
                playlist_id = url.split('/')[-1].split('?')[0]
                playlist = sp.playlist(playlist_id)
                playlist_name = playlist['name'].replace("/", "-")
                
                tracks = []
                for item in playlist['tracks']['items']:
                    track = item['track']
                    if track:
                        song_name = track["name"].replace("/", "-")
                        artist_name = track["artists"][0]["name"].replace("/", "-")
                        tracks.append((song_name, artist_name))
                
                return tracks, playlist_name
        
        except Exception as e:
            self.update_signal.emit(f'Error fetching song/playlist details: {e}')
        
        return None, None

class MusicDownloaderApp(QWidget):
    def __init__(self):
        super().__init__()
        self.download_directory = str(DEFAULT_DOWNLOAD_DIR)
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Offlinefy - Spotify & YouTube Downloader')
        self.setGeometry(100, 100, 500, 450)
        
        layout = QVBoxLayout()
        
        self.label = QLabel('Enter Spotify/YouTube URL or Song Name:')
        layout.addWidget(self.label)
        
        self.inputField = QLineEdit(self)
        layout.addWidget(self.inputField)
        
        self.selectDirButton = QPushButton(f'Select Download Directory (Default: {self.download_directory})')
        self.selectDirButton.clicked.connect(self.selectDirectory)
        layout.addWidget(self.selectDirButton)
        
        self.downloadButton = QPushButton('Download')
        self.downloadButton.clicked.connect(self.startDownload)
        layout.addWidget(self.downloadButton)
        
        self.statusText = QTextEdit()
        self.statusText.setReadOnly(True)
        layout.addWidget(self.statusText)
        
        self.setLayout(layout)

    def selectDirectory(self):
        directory = QFileDialog.getExistingDirectory(self, 'Select Download Directory')
        if directory:
            self.download_directory = directory
            self.statusText.append(f'Selected Directory: {directory}')

    def startDownload(self):
        url = self.inputField.text().strip()
        if url:
            self.statusText.append(f'Starting download for: {url}\nSaving to: {self.download_directory}')
            self.downloadThread = DownloadThread(url, self.download_directory)
            self.downloadThread.update_signal.connect(self.updateStatus)
            self.downloadThread.start()
        else:
            self.statusText.append('Please enter a valid URL or song name.')
    
    def updateStatus(self, message):
        self.statusText.append(message)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MusicDownloaderApp()
    window.show()
    sys.exit(app.exec())
