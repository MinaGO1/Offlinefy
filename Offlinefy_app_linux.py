from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QLabel, QLineEdit, QTextEdit, QFileDialog
from PyQt6.QtGui import QFont, QPalette, QColor
from PyQt6.QtCore import QThread, pyqtSignal
import sys, os, pathlib, yt_dlp, spotipy, zipfile
from spotipy.oauth2 import SpotifyClientCredentials
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC
import requests
from cryptography.fernet import Fernet
import shutil
from PyQt6.QtGui import QIcon


# Load environment variables

# Decrypt Spotify credentials
key = 'xxxxxxxxxxxxx'
cipher = Fernet(key)
encrypted_credentials = 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
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
            queries, playlist_name = self.get_queries(self.url)
            if queries is None:
                self.update_signal.emit('Error: Unable to fetch song details.')
                return

            if isinstance(queries, list):
                # Handle playlist
                playlist_dir = pathlib.Path(self.download_directory) / playlist_name
                playlist_dir.mkdir(parents=True, exist_ok=True)
                zip_filename = f"{playlist_name}.zip"
                zip_path = pathlib.Path(self.download_directory) / zip_filename
                if zip_path.exists():
                    self.update_signal.emit(f'{zip_filename} already exists. Skipping...')
                    return
                
                downloaded_files = []
                total_songs = len(queries)
                for index, (song_name, artist_name) in enumerate(queries, start=1):
                    filename = f"{artist_name} - {song_name}.mp3"
                    query = f"{song_name} {artist_name}"
                    output_path = playlist_dir / filename
                    
                    if output_path.exists():
                        self.update_signal.emit(f'{filename} already exists. Skipping...')
                        continue
                    
                    self.update_signal.emit(f'Downloading {index}/{total_songs} song: {filename}')
                    self.download_song(query, output_path)
                    self.addMetadata(output_path, song_name, artist_name)
                    downloaded_files.append(output_path)
                
                self.create_zip(downloaded_files, zip_path, playlist_dir)
                self.update_signal.emit(f'Playlist download and zip completed successfully: {zip_filename}')
            else:
                # Handle single song
                song_name, artist_name = queries
                filename = f"{artist_name} - {song_name}.mp3" if song_name and artist_name else f"{self.url}.mp3"
                query = f"{song_name} {artist_name}" if song_name and artist_name else self.url
                output_path = pathlib.Path(self.download_directory) / filename
                
                if output_path.exists():
                    self.update_signal.emit(f'{filename} already exists. Skipping...')
                    return
                
                self.update_signal.emit(f'Downloading song: {filename}')
                self.download_song(query, output_path)
                self.addMetadata(output_path, song_name, artist_name)
                self.update_signal.emit('Download and metadata update completed successfully!')
        except Exception as e:
            self.update_signal.emit(f'Error: {e}')
    
    def get_queries(self, url):
        """Extract song name and artist from Spotify URL or handle YouTube URL/song name."""
        try:
            if 'open.spotify.com/track/' in url:
                track_id = url.split('/')[-1].split('?')[0]
                track = sp.track(track_id)
                song_name = track["name"].replace("/", "-")
                artist_name = track["artists"][0]["name"].replace("/", "-")
                return (song_name, artist_name), None
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
            else:
                # Handle YouTube URL or song name
                return (url, None), None
        except Exception as e:
            self.update_signal.emit(f'Error fetching song details: {e}')
        return None, None

    def download_song(self, query, output_path):
        is_youtube = "youtube.com" in self.url or "youtu.be" in self.url
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': str(output_path).replace('.mp3',''),
        }
        if is_youtube:
            ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': str(self.download_directory) + '/%(title)s.%(ext)s',
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(self.url if is_youtube else f"ytsearch:{query}", download=True)
            if 'entries' in info:
                info = info['entries'][0]
            final_filename = ydl.prepare_filename(info).replace(".webm", ".mp3").replace(".m4a", ".mp3")
            final_path = pathlib.Path(final_filename)
            if final_path.exists():
                if not is_youtube:
                    self.addMetadata(final_path, query.split(' ')[0], query.split(' ')[1] if len(query.split(' ')) > 1 else None)

    def create_zip(self, files, zip_path, temp_dir):
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for file in files:
                zipf.write(file, arcname=file.name)
                file.unlink()  # Remove the original file after adding to zip
        shutil.rmtree(temp_dir)  # Remove the temporary directory after zipping

    def addMetadata(self, file_path, song_name, artist_name=None):
        try:
            audio = MP3(file_path, ID3=ID3)
            try:
                audio.add_tags()
            except:
                pass  # Tags already exist
            
            audio.tags.add(TIT2(encoding=3, text=song_name))
            if artist_name:
                audio.tags.add(TPE1(encoding=3, text=artist_name))
            
            # Download album art
            image_url = self.get_album_art_url(song_name, artist_name)
            if image_url:
                response = requests.get(image_url)
                if response.status_code == 200:
                    audio.tags.add(
                        APIC(
                            encoding=3,  # 3 is for utf-8
                            mime='image/jpeg',  # image/jpeg or image/png
                            type=3,  # 3 is for the cover image
                            desc='Cover',
                            data=response.content
                        )
                    )
            
            audio.save()
            self.update_signal.emit(f'Metadata added to: {song_name}' + (f' by {artist_name}' if artist_name else ''))
        except Exception as e:
            self.update_signal.emit(f'Failed to add metadata: {e}')

    def get_album_art_url(self, song_name, artist_name):
        """Fetch album art URL from Spotify."""
        try:
            if artist_name:
                results = sp.search(q=f"track:{song_name} artist:{artist_name}", type='track', limit=1)
            else:
                results = sp.search(q=song_name, type='track', limit=1)
            
            if results['tracks']['items']:
                album = results['tracks']['items'][0]['album']
                return album['images'][0]['url'] if album['images'] else None
        except Exception as e:
            self.update_signal.emit(f'Failed to fetch album art: {e}')
        return None

class MusicDownloaderApp(QWidget):
    def __init__(self):
        super().__init__()
        self.download_directory = str(DEFAULT_DOWNLOAD_DIR)
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Offlinefy - Spotify & YouTube Downloader')
        self.setGeometry(100, 100, 500, 450)
        self.setWindowIcon(QIcon("offlinefy.png")) 
        
        self.setStyleSheet("""
            QWidget {
                background-color: #121212;
                color: #ffffff;
                font-family: Arial;
            }
            QLabel {
                font-size: 14px;
            }
            QLineEdit {
                background-color: #282828;
                border: 2px solid #1DB954;
                border-radius: 5px;
                padding: 5px;
                color: white;
            }
            QPushButton {
                background-color: #1DB954;
                color: black;
                font-weight: bold;
                border-radius: 10px;
                padding: 8px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #14a044;
            }
            QTextEdit {
                background-color: #282828;
                border: 2px solid #ff0000;
                border-radius: 5px;
                padding: 5px;
                color: white;
            }
        """)
        
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
