import time
import os
from datetime import datetime
from typing import Optional, List
from spotipy import Spotify
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
import os

class Song:
    """Stores relevant data for a song retrieved from spotify's API.

    :param song: Dictionary containing playlist data from spotify's API.
    """
    added_at: datetime
    id: str
    name: str

    def __init__(self, song: dict) -> None:
        self.added_at = datetime.strptime(
            song['added_at'], "%Y-%m-%dT%H:%M:%SZ")
        self.id = song['track']['id']
        self.name = song['track']['name']

class Playlist:
    """Stores relevant data and methods for a playlist retrieved from spotify's API.

    :param sp: Spotipy client object.
    :param playlist: Dictionary containing playlist data from Spotipy.
    """
    songs: Optional[List[Song]]
    id: str
    name: str
    sp: Spotify

    def __init__(self, sp: Spotify, playlist: dict) -> None:
        if playlist is None:
            raise ValueError("No playlist data provided")
        self.sp = sp
        self.name = playlist.get('name', 'Unknown Playlist')
        self.id = playlist.get('id', '')
        self.songs = None

    def add_song(self, song: Song):
        """Adds a song to the playlist."""

        if not self.songs:
            if not self.__fetch_songs():
                print('error when loading songs in playlist')
                return
        if not self.__song_in(song):
            print(song.name, 'added to', self.name)
            self.sp.playlist_add_items(self.id, [song.id])
        else:
            print(song.name, 'already in', self.name)

    def __song_in(self, song: Song) -> bool:
        """Checks if a song is already in the playlist.

        :param song: The song to check for.
        :return: True for song in playlist, False otherwise.
        """

        return any(x.id == song.id for x in self.songs)

    def __fetch_songs(self) -> bool:
        """Retrieves and stores the playlist's songs using spotify's api.

        :return: True for success, False otherwise.
        """

        try:
            results = self.sp.playlist_items(
                playlist_id=self.id, additional_types=('track',))
        except Exception as e:
            print(repr(e))
            return False
        if 'items' not in results:
            return False
        self.songs = [Song(x) for x in results['items']]
        return True


class MonthlyPlaylists:
    """Fetches and checks playlists against newly saved songs then adds new songs to a monthly playlist.

    :param client_id: Client ID for Spotify API.
    :param client_secret: Client Secret for Spotify API.
    :param redirect_uri: Any valid URI matching the redirect URI in Spotify Developer application (optional).
    :param date: Date to detect newly saved songs after (optional).
    :param name_format: Strftime format string to name monthly playlists (optional).
    :param headless: Allows authenticating Spotify on a headless machine (optional).
    """
    user_id: str
    saved_songs: Optional[List[Song]]
    playlists: Optional[List[Playlist]]
    last_checked: datetime
    name_format: str

    def __init__(self, client_id: str, client_secret: str,
                 redirect_uri: str = '',
                 date: datetime = None, name_format: str = '%b \'%y', headless: bool = False) -> None:
        self.sp = spotipy.Spotify(
            auth_manager=SpotifyOAuth(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                scope="user-library-read playlist-modify-private playlist-modify-public playlist-read-private",
                cache_path=None,
                open_browser=False
            )
        )
        self.user_id = self.sp.current_user()['id']
        self.saved_songs = None
        self.playlists = None
        self.last_checked = datetime.today().replace(day=1) if date is None else date
        self.name_format = name_format

    def update_monthly_playlists(self):
        """Performs every step for maintaining monthly playlists."""

        if not self.__fetch_saved_songs():
            print('error when loading saved songs')
        new_songs = self.__fetch_new_saved_songs()
        if not new_songs:
            print('No new songs')
            return
        if not self.__fetch_playlists():
            print('error when loading playlists')
            return
        if not self.__add_songs_to_playlist(new_songs):
            print('error during playlist creation/detection')
            return
        self.last_checked = new_songs[0].added_at

    def __fetch_saved_songs(self, offset: int = 0) -> bool:
        """Fetches and stores currently saved songs using spotify's api.
        :param offset: Load songs from offset onwards and append to current saved_songs.
        :return: True for success, False otherwise.
        """

        try:
            results = self.sp.current_user_saved_tracks(
                limit=50, offset=offset)
        except Exception as e:
            print(repr(e))
            return False
        if 'items' not in results:
            return False
        songs = [Song(x) for x in results['items']]
        if offset > 0:
            self.saved_songs.extend(songs)
        else:
            self.saved_songs = songs
        if self.saved_songs[-1].added_at > self.last_checked:
            self.__fetch_saved_songs(offset=offset+50)
        return True

    def __fetch_playlists(self) -> bool:
        """Fetches and stores current playlists using Spotify's API.
        :return: True for success, False otherwise.
        """
        try:
            results = self.sp.current_user_playlists()
            if 'items' not in results or not results['items']:
                print('No playlists found or empty playlist data')
                return False

            self.playlists = [Playlist(self.sp, x) for x in results['items'] if x]
            return True
        except Exception as e:
            print(f"An error occurred while fetching playlists: {repr(e)}")
            return False


    def __fetch_new_saved_songs(self):
        """Returns list of songs that were added after the last_date checked."""

        return [song for song in self.saved_songs if song.added_at > self.last_checked]

    def __add_songs_to_playlist(self, songs: List[Song]) -> bool:
        """Adds songs to a playlist named from the current month and year, creates the playlist if it does not exist."""
        if not songs:
            return False

        name = songs[0].added_at.strftime(self.name_format)
        existing_playlist = self.__find_playlist(name)
        
        if existing_playlist is None:
            return False  # Asegura que no procede si no hay playlist válida

        for song in songs:
            existing_playlist.add_song(song)
            
        return True


    def __find_playlist(self, name: str) -> Optional[Playlist]:
        """Returns a playlist matching the given name or creates one if it does not exist."""
        playlist = next((x for x in self.playlists if x.name == name), None)
        
        if playlist is None:
            print(f"Creating new playlist: {name}")
            try:
                data = self.sp.user_playlist_create(user=self.user_id, name=name)
                new_playlist = Playlist(self.sp, data)
                self.playlists.append(new_playlist)
                return new_playlist
            except Exception as e:
                print(f"Failed to create playlist: {repr(e)}")
                return None

        return playlist


load_dotenv()

spotify = MonthlyPlaylists(
    client_id=os.getenv('CLIENT_ID'),
    client_secret=os.getenv('CLIENT_SECRET'),
    redirect_uri=os.getenv('REDIRECT_URI')
)
# The class updates its date threshold to whichever song it added last.
# Therefore, calling update_monthly_playlists() multiple times will make minimal api calls

spotify.update_monthly_playlists()