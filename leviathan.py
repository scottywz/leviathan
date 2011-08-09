#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Leviathan Music Manager
# A command-line utility to manage your music collection.
# 
# Copyright (C) 2010-2011 Scott Zeid
# http://me.srwz.us/leviathan
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
# 
# Except as contained in this notice, the name(s) of the above copyright holders
# shall not be used in advertising or otherwise to promote the sale, use or
# other dealings in this Software without prior written authorization.

import collections
import ConfigParser as configparser
import os
import re
import shutil
import sqlite3
import stat
import string
import subprocess
import sys
import traceback
import UserDict

import mutagen
import yaml

from mutagen.easyid3 import EasyID3

Format = collections.namedtuple("Format", ["ffmpeg_codec"])

# DB version changelog:
# 2 - added length field to songs table
# 1.1 - leviathan_meta "key" field made UNIQUE
# 1 - initial version
DB_VERSION = "2"
EXTENSIONS = dict(
 aac  = Format("libfaac"),
 flac = Format("flac"),
 m4a  = Format("libfaac"),
 mp3  = Format("libmp3lame"),
 ogg  = Format("libvorbis"),
 wav  = Format("pcm_s16le"),
 wma  = Format("wmav2")
)


class Albums(object):
 queries = {
  "all_albums_and_artists": """SELECT album, artist FROM songs
                               GROUP BY album, artist
                               ORDER BY sort_album, sort_artist""",
  "album_and_artist_from_both": """SELECT album, artist FROM songs WHERE
                                    album = :album AND artist = :artist
                                   ORDER BY sort_album, sort_artist""",
  "albums_and_artist_from_artist": """SELECT album, artist FROM songs WHERE
                                       artist = :artist
                                      GROUP BY album, artist
                                      ORDER BY sort_album, sort_artist""",
  "song_ids_from_album_and_artist": """SELECT id FROM songs WHERE
                                        album = :album AND artist = :artist
                                       ORDER BY
                                        sort_title, sort_artist, sort_album"""
 }
 Album = collections.namedtuple("Album", "name artist library songs")
 
 def __init__(self, library):
  self.library = library
 
 def __len__(self):
  return len(self.library.query(self.queries["all_albums_and_artists"]))
 
 def __call__(self, artist=None, album=None):
  if album:
   if not artist:
    raise TypeError("artist cannot be None when album is not None")
   return self[(artist, album)]
  elif artist:
   return self[artist]
  return self
 
 def __contains__(self, item):
  if isinstance(item, basestring):
   q = self.queries["albums_and_artist_from_artist"]
   r = self.library.query(q, artist=item)
  elif isinstance(item, (list, tuple)):
   q = self.queries["album_and_artist_from_both"]
   r = self.library.query(q, artist=item[1], album=item[0])
  else:
   raise TypeError("item must be a string, list, or tuple")
  return bool(len(r))
 
 def __getitem__(self, item):
  if isinstance(item, basestring):
   q = self.queries["albums_and_artist_from_artist"]
   r = self.library.query(q, artist=item)
   if not len(r):
    raise IndexError("no aritst named '%s'" % item)
   return [self[i] for i in r if i]
  elif isinstance(item, (int, long)):
   return self[self.names[item]]
  elif isinstance(item, (list, tuple)):
   q = self.queries["song_ids_from_album_and_artist"]
   r = self.library.query(q, artist=item[1], album=item[0])
   if not len(r):
    raise IndexError("no album named '%s' by artist '%s'" % tuple(item))
   songs = tuple([Song(self.library, i[0]) for i in r if i])
   return self.Album(name=item[0], artist=item[1], library=self.library,
                     songs=songs)
  elif isinstance(item, slice):
   return [self[i] for i in self.names[item]]
  else:
   raise TypeError("item must be a string, integer, list, slice, or tuple")
 
 def __iter__(self):
  for i in self.names:
   yield self[i]
 
 @property
 def names(self):
  q = self.queries["all_albums_and_artists"]
  return [i for i in self.library.query(q) if i]


class Artists(object):
 queries = {
  "all_artists": """SELECT artist FROM songs
                    GROUP BY artist ORDER BY sort_artist""",
  "artist_from_artist": """SELECT artist FROM songs WHERE artist = :artist
                           GROUP BY artist ORDER BY sort_artist""",
  "song_ids_from_artist": """SELECT id FROM songs WHERE artist = :artist
                             ORDER BY sort_title, sort_artist, sort_album"""
 }
 Artist = collections.namedtuple("Artist", "name library songs")
 class Artist(Artist):
  @property
  def albums(self):
   return self.library.albums[self.name]
 
 def __init__(self, library):
  self.library = library
 
 def __len__(self):
  return len(self.library.query(self.queries["all_artists"]))
 
 def __contains__(self, artist_name):
  r = self.library.query(self.queries["artist_from_artist"], artist=artist)
  return bool(len(r))
 
 def __getitem__(self, item):
  if isinstance(item, basestring):
   r = self.library.query(self.queries["song_ids_from_artist"], artist=item)
   if not len(r):
    raise IndexError("no artist named '%s'" % item)
   songs = tuple([Song(self.library, i[0]) for i in r if i])
   return self.Artist(name=item, library=self.library, songs=songs)
  elif isinstance(item, (int, long)):
   return self[self.names[item]]
  elif isinstance(item, slice):
   return [self[i] for i in self.names[item]]
  else:
   raise TypeError("item must be a string, integer, or slice")
 
 def __iter__(self):
  for i in self.names:
   yield self[i]
 
 @property
 def names(self):
  return [i[0] for i in self.library.query(self.queries["all_artists"]) if i]


class Playlist(UserDict.DictMixin, object):
 queries = {
  "add": """INSERT INTO playlists (name) VALUES (:name)""",
  "entry_add": """INSERT INTO playlist_entries (song, playlist)
                  VALUES (:song, :playlist)""",
  "entry_delete": """DELETE FROM playlist_entries
                     WHERE song = :song AND playlist = :playlist""",
  "entry_id": """SELECT id FROM playlist_entries
                 WHERE song = :song and playlist = :playlist""",
  "delete_playlist_from_id": """DELETE FROM playlists WHERE id = :id""",
  "delete_playlist_entries_from_id": """DELETE FROM playlist_entries
                                        WHERE playlist = :id""",
  "id_from_id": """SELECT id FROM playlists WHERE id = (:id)""",
  "id_from_name": """SELECT id FROM playlists WHERE name = (:name)""",
  "name_from_id": """SELECT name FROM playlists WHERE id = (:id)""",
  "name_from_name": """SELECT name FROM playlists WHERE name = (:name)""",
  "playlist_from_id": """SELECT id, name FROM playlists WHERE id = (:id)""",
  "playlist_from_name": """SELECT id, name FROM playlists
                           WHERE name = (:name)""",
  "songs_from_id": """SELECT
                       songs.id,relpath,title,sort_title,artist,sort_artist,
                       album,sort_album,length
                      FROM songs INNER JOIN playlist_entries ON
                       songs.id = playlist_entries.song AND
                       playlist_entries.playlist = :id_
                      ORDER BY sort_title, sort_artist, sort_album""",
  "song_paths_from_id": """SELECT relpath FROM songs
                           INNER JOIN playlist_entries ON
                            songs.id = playlist_entries.song AND
                            playlist_entries.playlist = :id_
                           ORDER BY sort_title, sort_artist, sort_album""",
  "rename_from_id": """UPDATE playlists SET name = :name WHERE id = :id"""
 }
 
 def __init__(self, library, name_or_id):
  """Returns a Playlist object with the given info.
  
  This class is instantiated by Playlists; do not instantiate it directly
  unless you know what you're doing.
  
  """
  
  if not isinstance(library, Library):
   raise TypeError("library must be a Library")
  if not isinstance(name_or_id, (basestring, int, long)):
   raise TypeError("name_or_id must be a string or integer")
  self.library = library
  if isinstance(name_or_id, basestring):
   name = name_or_id
   id_ = None
  elif isinstance(name_or_id, (int, long)):
   id_ = name_or_id
   try:
    name = library.query(self.queries["name_from_id"], id=name_or_id)[0][0]
   except IndexError:
    raise IndexError("There is no playlist with the id %d" % id_)
  self.__data = {"id": id_, "name": to_unicode(name)}
  if not self.__data["id"]:
   self.__data["id"] = self.__get_id()
  if name and not library.check_path(self.path, library.playlists_path, False):
   raise ValueError("The playlist's file must be within the playlist root.")
 
 def __getitem__(self, key):
  return self.__data[key]
 def keys(self):
  return self.__data.keys()
 
 @property
 def id(self): return self["id"]
 @property
 def name(self): return self["name"]
 @property
 def path(self):
  return self.library.playlist_formats.default.path(self.name)
 @property
 def relpath(self):
  return self.library.playlist_formats.default.relpath(self.name)
 
 @property
 def paths(self):
  paths = {}
  for f in self.library.playlist_formats.values():
   paths[f.dirname] = f.path(self.name)
  return paths
 
 @property
 def relpaths(self):
  paths = {}
  for f in self.library.playlist_formats.values():
   paths[f.dirname] = f.relpath(self.name)
  return paths
 
 @property
 def exists(self):
  q = self.queries["id_from_name"]
  return bool(len(self.library.query(q, name=self.name)))
 
 @property
 def songs(self):
  if not self.exists:
   raise Exception("the playlist '%s' is not in the database" % self.name)
  q = self.queries["songs_from_id"]
  return self.library.songs._parse_songs(self.library.query(q, id_=self.id))
 
 @property
 def song_paths(self):
  return [os.path.join(self.library.music_path, i) for i in self.song_relpaths]
 
 @property
 def song_paths_mp3(self):
  return [os.path.join(self.library.music_path, i.rsplit(".", 1)[0] + ".mp3")
          for i in self.song_relpaths]
 
 @property
 def song_relpaths(self):
  if not self.exists:
   raise Exception("the playlist '%s' is not in the database" % self.name)
  q = self.queries["song_paths_from_id"]
  return [i[0] for i in self.library.query(q, id_=self.id)]
 
 @property
 def song_relpaths_mp3(self):
  return [i.rsplit(".", 1)[0] + ".mp3" for i in self.song_relpaths]
 
 def add_song(self, song):
  if not self.has_song(song):
   self.library.query(self.queries["entry_add"], song=song.id,
                      playlist=self.id)
   self.save()
 
 def __get_id(self):
  q = self.queries["id_from_name"]
  try:
   return self.library.query(q, name=self.name)[0][0]
  except IndexError:
   return None

 def has_song(self, song):
  if not self.exists:
   raise ValueError("the playlist %s does not exist" % self.name)
  if not song.exists:
   raise ValueError("the song %s does not exist" % song.relpath)
  q = self.queries["entry_id"]
  return bool(len(self.library.query(q, song=song.id, playlist=self.id)))
 
 def _load(self):
  if not os.path.exists(self.path):
   if self.exists: self.save()
   return
  songs = PlaylistFormat(self.library).load(self.path).songs
  conn, c = self.library._setup_db()
  for song in songs:
   song = self.library.songs.add(song.relpath)
   c.execute(self.queries["entry_id"], dict(song=song.id, playlist=self.id))
   if not len(c.fetchall()):
    c.execute(self.queries["entry_add"], dict(song=song.id, playlist=self.id))
   conn.commit()
  conn.commit()
  c.close()
  self.save()
 
 def remove(self):
  if not self.exists:
   raise Exception("the playlist '%s' is not in the database" % self.name)
  name = self.name
  self.library.query(self.queries["delete_playlist_from_id"], id=self.id)
  self.library.query(self.queries["delete_playlist_entries_from_id"],id=self.id)
  for path in self.paths.values():
   if os.path.isfile(os.path.realpath(path)): os.unlink(path)
 
 def remove_song(self, song):
  if self.has_song(song):
   self.library.query(self.queries["entry_delete"], song=song.id,
                      playlist=self.id)
   self.save()
 
 def rename(self, new_name):
  if not self.exists:
   raise Exception("the playlist '%s' is not in the database" % self.name)
  if new_name and \
     not self.library.check_path(self.relpath, self.library.playlists_path, 0):
   raise ValueError("The playlist's file must be within the playlist root.")
  old_name = self.name
  old_paths = self.paths
  self.library.query(self.queries["rename_from_id"], name=new_name, id=self.id)
  self.__data["name"] = new_name
  new_paths = self.paths
  for dirname in self.library.playlist_formats:
   shutil.move(old_paths[dirname], new_paths[dirname])
 
 def save(self):
  """Writes this playlist to disk."""
  for f in self.library.playlist_formats.values():
   plsf = f.format(self)
   if f.mp3_only:
    path_attr = "path_mp3" if f.absolute_paths else "relpath_mp3"
   else:
    path_attr = "path" if f.absolute_paths else "relpath"
   plsf.save(f.path(self.name), title_fmt=f.title_format, path_attr=path_attr)
   if f.substitutions:
    with open(f.path(self.name), "rb") as fp:
     data = fp.read().decode("utf8")
    for search, replace, is_regex in f.substitutions:
     if is_regex:
      data = search.sub(replace, data)
     else:
      data = data.replace(search, replace)
    with open(f.path(self.name), "wb") as fp:
     fp.write(data.encode("utf8"))


class Playlists(object):
 """Represents the playlists in a Leviathan database.
  
  Playlists can be manipulated using the methods in this class or by using the
  playlist's database ID or name as a mapping key.
  
  This class is instantiated by Library; you should not instantiate it directly
  unless you know what you're doing.
  
  """
 queries = {
  "all_ids": """SELECT id FROM playlists ORDER BY name""",
  "all_ids_quick": """SELECT id FROM playlists""",
  "all_ids_sort_id": """SELECT id FROM playlists ORDER BY id""",
  "all_playlists": """SELECT id, name FROM playlists ORDER BY name"""
 }
 
 def __init__(self, library):
  self.library = library
 
 def __len__(self):
  return len(self.library.query(self.queries["all_ids_quick"]))
 
 def __contains__(self, pls):
  if isinstance(pls, Playlist):
   pls = pls.name
  if isinstance(pls, basestring):
   r = self.library.query(Playlist.queries["id_from_name"], name=pls)
  elif isinstance(pls, (int, long)):
   r = self.library.query(Playlist.queries["id_from_id"], id=pls)
  else:
   raise TypeError("pls must be a Playlist, string, or integer")
  return bool(len(r))
 
 def __delitem__(self):
  self[pls].remove()
 
 def __getitem__(self, item):
  if not isinstance(item, (basestring, int, long, slice, Playlist)):
   raise TypeError("item must be a string, integer, slice, or Playlist")
  if isinstance(item, slice):
   r = []
   for i in xrange(*item.indices((self.greatest_id() or 0) + 1)):
    try:
     r.append(Playlist(self.library, i))
    except:
     pass
   return r
  if isinstance(item, Playlist): item = playlist.name
  return Playlist(self.library, item)
 
 def __iter__(self):
  ids = [i[0] for i in self.library.query(self.queries["all_ids"]) if i]
  for i in ids:
   yield Playlist(self.library, i)
 
 def _parse(self, result):
  # Makes a list of Playlist objects from a SQL query result (output of
  # sqlite3.Cursor.fetchall)
  return [Playlist(self.library, *i) for i in result]
 
 def _update_playlists(self, playlists):
  for pls in playlists:
   pls.save()
 
 def add(self, name):
  if name in self:
   return self[name]
  self.library.query(Playlist.queries["add"], name=name)
  pls = Playlist(self.library, name)
  pls._load()
  return pls
 
 def all(self):
  q = self.queries["all_playlists"]
  return self._parse(self.library.query(q))
 
 def greatest_id(self):
  ids = [i[0] for i in self.library.query(self.queries["all_ids_sort_id"])
         if i]
  try:
   return ids[-1]
  except IndexError:
   return None
 
 def scan(self):
  for i in os.listdir(self.library.playlists_path):
   name = custom_splitext(i, self.library.playlist_formats.default.ext)[0]
   if name not in self.library.db_ignore_playlists:
    path = os.path.join(self.library.playlists_path, i)
    self.add(name)
 
 def save(self):
  """Saves all playlists to disk."""
  for pls in self:
   if pls.name not in self.library.db_ignore_playlists:
    pls.save()


class PlaylistFormat(object):
 extensions = []
 name = None
 
 def __init__(self, library_or_playlist):
  if isinstance(library_or_playlist, Library):
   self.library = library_or_playlist
   self.songs = []
  elif isinstance(library_or_playlist, Playlist):
   self.library = library_or_playlist.library
   self.songs = library_or_playlist.songs
  else:
   raise TypeError("library_or_playlist must be a Library or Playlist")
 @classmethod
 def detect(self, filename):
  ext = "." + filename.rsplit(".", 1)[1].lower()
  if ext in M3UPlaylist.extensions:
   with open(filename, "rb") as f:
    if f.next() == "#EXTM3U":
     return ExtendedM3UPlaylist
    return M3UPlaylist
  if ext in PLSPlaylist.extensions:
   return PLSPlaylist
  return None
 def format_title_string(self, song, fmt):
  d = collections.defaultdict(lambda: "", song)
  if not d["title"]:
   d["title"] = os.path.basename(song.relpath.rsplit(".", 1)[0])[0]
  title = string.Template(fmt).substitute(d)
  return title
 def load(self, filename):
  # Subclasses should not inherit this method's behavior
  if type(self) != PlaylistFormat:
   raise NotImplementedError()
  fmt = self.detect(filename)
  if not fmt:
   raise ValueError(to_unicode(filename) + " is not in a supported format")
  ret = fmt(self.library)
  ret.load(filename)
  return ret
 def save(self, filename=None, title_fmt="$title", path_attr="path"):
  raise NotImplementedError()

class M3UPlaylist(PlaylistFormat):
 extensions = (".m3u", ".m3u8")
 name = "m3u"
 
 def load(self, filename):
  with open(filename, "rb") as f:
   data = [i for i in f.read().decode("utf8").splitlines()
           if i and not i.startswith("#")]
  self.songs = []
  for p in data:
   if p in self.library.songs:
    self.songs.append(self.library.songs[p])
   elif self.library.check_path(p, self.library.music_path, False):
    p = self.library.relpath(p, self.library.music_path)
    if p in self.library.songs:
     self.songs.append(self.library.songs[p])
 
 def save(self, filename=None, title_fmt="unused", path_attr="path"):
  out = "\n".join([getattr(i, path_attr) for i in self.songs])
  if filename:
   with open(filename, "wb") as f:
    f.write(out.encode("utf8"))
  else:
   return out

class ExtendedM3UPlaylist(M3UPlaylist):
 name = "extm3u"
 
 def save(self, filename=None, title_fmt="$title", path_attr="path"):
  out = ["#EXTM3U", ""]
  for i in self.songs:
   title = self.format_title_string(i, title_fmt)
   length = int(round(i.length)) if i.length != None else -1
   path = getattr(i, path_attr)
   out += ["#EXTINF:%d,%s" % (length, title), path, ""]
  out = "\n".join(out)
  if filename:
   with open(filename, "wb") as f:
    f.write(out.encode("utf8"))
  else:
   return out

class PLSPlaylist(PlaylistFormat):
 extensions = (".pls",)
 name = "pls"
 
 def load(self, filename):
  cp = configparser.SafeConfigParser()
  with open(filename, "rb") as f:
   cp.readfp(f)
  self.songs = []
  length = int(cp.get("playlist", "NumberOfEntries"))
  for i in range(1, length + 1):
   p = cp.get("playlist", "File" + str(i))
   if p in self.library.songs:
    self.songs.append(self.library.songs[p])
   elif self.library.check_path(p, self.library.music_path, False):
    p = self.library.relpath(p, self.library.music_path)
    if p in self.library.songs:
     self.songs.append(self.library.songs[p])
 
 def save(self, filename=None, title_fmt="$title", path_attr="path"):
  out = ["[playlist]", ""]
  n = 1
  for i in self.songs:
   title = self.format_title_string(i, title_fmt)
   length = int(round(i.length)) if i.length != None else -1
   out += ["File%d=%s" % (n, getattr(i, path_attr)), "Title%d=%s" % (n, title),
           "Length%d=%d" % (n, length), ""]
   n = int(n) + 1
  out += ["NumberOfEntries="+str(int(n)-1), "", "Version=2", ""]
  out = "\n".join(out)
  if filename:
   with open(filename, "wb") as f:
    f.write(out.encode("utf8"))
  else:
   return out

playlist_file_formats = dict(
 m3u=M3UPlaylist,
 extm3u=ExtendedM3UPlaylist,
 pls=PLSPlaylist
)


class Song(UserDict.DictMixin, object):
 queries = {
  "add": """INSERT INTO songs
             (relpath,title,sort_title,artist,sort_artist,album,sort_album,
              length)
            VALUES
             (:relpath,:title,:sort_title,:artist,:sort_artist,:album,
              :sort_album,:length)""",
  "delete_playlist_entries_from_id": """DELETE FROM playlist_entries
                                        WHERE song = :id""",
  "delete_song_from_id": """DELETE FROM songs WHERE id = :id""",
  "id_from_id": """SELECT id FROM songs WHERE id = (:id)""",
  "id_from_relpath": """SELECT id FROM songs WHERE relpath = (:relpath)""",
  "playlists_from_id": """SELECT name FROM playlists
                          INNER JOIN playlist_entries ON
                           playlist_entries.playlist = playlists.id AND
                           playlist_entries.song = :id
                          ORDER BY name""",
  "song_from_id": """SELECT
                      id,relpath,title,sort_title,artist,sort_artist,album,
                      sort_album,length
                     FROM songs WHERE id = (:id)""",
  "song_from_relpath": """SELECT \
                           id,relpath,title,sort_title,artist,sort_artist,
                           album,sort_album,length
                          FROM songs WHERE relpath = (:relpath)""",
  "update_from_id": """UPDATE songs SET
                        relpath=:relpath,title=:title,sort_title=:sort_title,
                        artist=:artist,sort_artist=:sort_artist,album=:album,
                        sort_album=:sort_album,length=:length
                       WHERE id = :id""",
  "update_from_relpath": """UPDATE songs SET
                             title=:title,sort_title=:sort_title,
                             artist=:artist,sort_artist=:sort_artist,
                             album=:album,sort_album=:sort_album,length=:length
                            WHERE relpath = :relpath""",
  "update_relpath_from_id": """UPDATE songs SET relpath=:relpath
                               WHERE id = :id"""
 }
 
 def __init__(self, library, *info):
  """Returns a Song object with the given info.
  
  This class is instantiated by Songs; do not instantiate it directly unless
  you know what you're doing.
  
  """
  if not isinstance(library, Library):
   raise TypeError("library must be a Library")
  if len(info) not in (0, 1, 9):
   raise TypeError("__init__() takes 1, 2, or 10 arguments")
  if len(info) == 1:
   search = to_unicode(info[0])
   if isinstance(search, basestring):
    info = library.query(self.queries["song_from_relpath"], relpath=search)
   elif isinstance(search, (int, long)):
    info = library.query(self.queries["song_from_id"], id=search)
   else:
    raise TypeError("when 2 arguments are given, the second must be a string,"
                    " integer, or long")
   try:
    info = info[0]
   except IndexError:
    if not isinstance(search, basestring):
     raise
    if search and not library.check_path(search, library.music_path, False):
     raise ValueError("The song file must be within the library root.")
    info = [None] + library._get_song_info(search)
    if not info:
     raise ValueError("'%s' is not a valid music file", search)
  self.library = library
  self.__data = {
   "relpath": to_unicode(info[1]),
   "title": to_unicode(info[2]),
   "sort_title": to_unicode(info[3]),
   "artist": to_unicode(info[4]),
   "sort_artist": to_unicode(info[5]),
   "album": to_unicode(info[6]),
   "sort_album": to_unicode(info[7]),
   "length": to_unicode(info[8])
  }
  try:
   self.__data["id"] = int(info[0])
  except TypeError:
   self.__data["id"] = self.__get_id()
 
 def __getitem__(self, key):
  return self.__data[key]
 
 def keys(self):
  return self.__data.keys()
 
 def _update_playlists(self, playlists=None):
  if playlists == None: playlists = self.playlists
  self.library.playlists._update_playlists(playlists)
 
 @property
 def path(self): return os.path.join(self.library.music_path, self.relpath)
 @property
 def path_mp3(self): return self.path.rsplit(".", 1)[0] + ".mp3"
 @property
 def relpath(self): return self["relpath"]
 @relpath.setter
 def relpath(self, new_relpath):
  self.__data["relpath"] = new_relpath
  self.library.query(self.queries["update_relpath_from_id"],
                     relpath=new_relpath, id=self.id)
 @property
 def relpath_mp3(self): return self.relpath.rsplit(".", 1)[0] + ".mp3"
 @property
 def id(self): return self["id"]
 @property
 def title(self): return self["title"]
 @property
 def sort_title(self): return self["sort_title"]
 @property
 def artist(self): return self["artist"]
 @property
 def sort_artist(self): return self["sort_artist"]
 @property
 def album(self): return self["album"]
 @property
 def sort_album(self): return self["sort_album"]
 @property
 def length(self): return self["length"]
 
 @property
 def exists(self):
  q = self.queries["id_from_relpath"]
  return bool(len(self.library.query(q, relpath=self.relpath)))
 
 @property
 def playlists(self):
  if not self.exists:
   raise Exception("the song at '%s' is not in the database" % self.relpath)
  q = self.queries["playlists_from_id"]
  return self.library.playlists._parse(self.library.query(q, id=self.id))
 
 @property
 def tuple(self):
  return (self["id"], (self["title"], self["sort_title"], self["artist"],
                       self["sort_artist"], self["album"], self["sort_album"],
                       self["length"]))
 
 def __get_id(self):
  q = self.queries["id_from_relpath"]
  try:
   return self.library.query(q, relpath=self.relpath)[0][0]
  except IndexError:
   return None
 
 def load_metadata(self):
  info = self.library._get_song_info(self.relpath)
  self.__data.update({
   "relpath": to_unicode(info[0]),
   "title": to_unicode(info[1]),
   "sort_title": to_unicode(info[2]),
   "artist": to_unicode(info[3]),
   "sort_artist": to_unicode(info[4]),
   "album": to_unicode(info[5]),
   "sort_album": to_unicode(info[6])
  })
 
 def remove(self):
  if not self.exists:
   raise Exception("the song at '%s' is not in the database" % self.relpath)
  playlists = self.playlists
  self.library.query(self.queries["delete_song_from_id"], id=self.id)
  self.library.query(self.queries["delete_playlist_entries_from_id"],
                       id=self.id)
  self._update_playlists(playlists)
 
 def update(self):
  if not self.exists:
   raise IndexError("the song at '%s' is not in the database" % self.relpath)
  if self.relpath and \
     not self.library.check_path(self.relpath, self.library.music_path, False):
   raise ValueError("The song file must be within the library root.")
  self.load_metadata()
  self.library.query(self.queries["update_from_relpath"], **self)
  self._update_playlists()


class Songs(object):
 """Represents the songs in a Leviathan database as a dictionary-like object.

This class is instantiated by Library; you should not instantiate it directly
unless you know what you're doing.

"""
 queries = {
  "all_ids": """SELECT id FROM songs ORDER BY sort_title""",
  "all_ids_quick": """SELECT id FROM songs""",
  "all_ids_sort_id": """SELECT id FROM songs ORDER BY id""",
  "all_songs": """SELECT
                   id,relpath,title,sort_title,artist,sort_artist,album,
                   sort_album,length
                  FROM songs ORDER BY sort_title""",
  "id_from_*": """SELECT id FROM songs WHERE %s = :value""",
  "id_from_*_like": """SELECT id FROM songs WHERE %s LIKE :value""",
  "id_from_*_sorted_by_*": """SELECT id FROM songs WHERE %s = :value
                              ORDER BY %s""",
  "id_from_*_sorted_by_*_like": """SELECT id FROM songs WHERE %s LIKE :value
                                   ORDER BY %s"""
 }
 
 def __init__(self, library):
  self.library = library
 
 def __len__(self):
  return len(self.library.query(self.queries["all_ids_quick"]))
 
 def __contains__(self, song):
  if isinstance(song, Song):
   song = song.relpath
  if isinstance(song, basestring):
   song = to_unicode(song)
   r = self.library.query(Song.queries["id_from_relpath"], relpath=song)
  elif isinstance(song, (int, long)):
   r = self.library.query(Song.queries["id_from_id"], id=song)
  else:
   raise TypeError("song must be a Song, string, or integer")
  return bool(len(r))
 
 def __delitem__(self, song):
  self[song].remove()
 
 def __getitem__(self, item):
  if not isinstance(item, (basestring, int, long, slice, Song)):
   raise TypeError("item must be a string, integer, slice, or Song")
  if isinstance(item, slice):
   r = []
   for i in xrange(*item.indices((self.greatest_id() or 0) + 1)):
    try:
     r.append(Song(self.library, i))
    except:
     pass
   return r
  if isinstance(item, Song): item = item.relpath
  return Song(self.library, item)
 
 def __iter__(self):
  ids = [i[0] for i in self.library.query(self.queries["all_ids"]) if i]
  for i in ids:
   try:
    r = self.library.query(Song.queries["song_from_id"], id=i)[0]
   except IndexError:
    continue
   yield Song(self.library, *r)
 
 def _parse_songs(self, result):
  # Makes a list of Song objects from a SQL query result (output of
  # sqlite3.Cursor.fetchall)
  return [Song(self.library, *i) for i in result]
 
 def add(self, relpath):
  if relpath in self:
   song = self[relpath]
   song.update()
   return song
  song = Song(self.library, relpath)
  self.library.query(Song.queries["add"], **song)
  song._Song__data["id"] = song._Song__get_id()
  return song
 
 def all(self):
  return self._parse_songs(self.library.query(self.queries["all_songs"]))
 
 def greatest_id(self):
  ids = [i[0] for i in self.library.query(self.queries["all_ids_sort_id"])
         if i]
  try:
   return ids[-1]
  except IndexError:
   return None
 
 def scan(self):
  for root, dirs, files in os.walk(self.library.music_path, followlinks=True):
   for i in files:
    path = os.path.join(root, i)
    if mutagen.File(path, easy=True):
     self.add(self.library.relpath(path, self.library.music_path))
 
 def search(self, key, value, exact=True, sort="sort_title"):
  qname = "id_from_*"
  if sort:
   if isinstance(sort, basestring):
    sort = [sort]
   if isinstance(sort, (list, tuple)):
    sort = ",".join([re.sub(r"[^a-z_,]", "", i) for i in sort if i.strip()])
   else:
    raise ValueError("sort must be a string, list, or tuple")
   qname += "_sorted_by_*"
  if not exact:
   qname += "_like"
   value = "%" + value.replace("_", "%_") + "%"
  print repr(key), repr(sort)
  q = self.queries[qname] % ((key, sort) if sort else key)
  return [self[i[0]] for i in self.library.query(q, value=value) if i]
 
 def to_mp3(self):
  library = self.library.music_path
  nomp3 = []
  extension_whitelist = [i for i in EXTENSIONS.keys() if i != "mp3"]
  for i in self:
   if i.relpath.rsplit(".", 1)[1] in extension_whitelist and \
      not os.path.exists(i.relpath.rsplit(".", 1)[0] + ".mp3"):
    nomp3.append(i.relpath)
  if len(nomp3) > 0:
   nomp3.sort()
   for in_file in nomp3:
    in_file = os.path.join(self.library.music_path, in_file)
    out_file = in_file.rsplit(".", 1)[0] + ".mp3"
    convert_to_mp3(in_file, out_file, self.library.ffmpeg, self.library.lame,
                   self.library.constant_bitrate, self.library.vbr_quality)


class Library(object):
 queries = {
  "all_meta_keys_and_values": """SELECT key, value FROM leviathan_meta
                                 ORDER BY key""",
  "add_meta": """INSERT INTO leviathan_meta (key, value)
                 VALUES (:key, :value)""",
  "meta_value_from_key": """SELECT value FROM leviathan_meta WHERE
                             key = :key""",
  "update_meta": """UPDATE leviathan_meta SET value = :value WHERE
                     key = :key"""
 }
 
 def __init__(self, config):
  if isinstance(config, basestring):
   self.config_file = os.path.expanduser(config)
   with open(self.config_file, "rb") as f:
    config = yaml.load(f)
  elif isinstance(config, file):
   self.config_file = config.name
   config = yaml.load(config)
  elif isinstance(config, dict):
   self.config_file = None
  else:
   raise ValueError("config must be a string, file object, or dict, not a(n) "
                     + type(config).__name__)
  # Library settings
  self.music_path = os.path.normpath(to_unicode(config["music_path"]))
  self.database_path = os.path.normpath(to_unicode(config["database_path"]))
  self.albumart_filename = to_unicode(config["albumart_filename"])
  # Check database version
  if os.path.exists(os.path.realpath(self.database_path)):
   if int(self.get_meta("db_version") or 0) < int(DB_VERSION):
    raise Exception("the database schema version is old; please delete and"
                    " recreate the database")
  # Playlist settings
  self.playlist_formats = PlaylistFormatSettings()
  playlist_formats = config["playlist_formats"]
  self.default_playlist_config = None
  for k in playlist_formats:
   v = playlist_formats[k]
   k = os.path.normpath(to_unicode(k))
   fmt = to_unicode(v.get("format", u"m3u"))
   if fmt not in playlist_file_formats:
    raise ValueError("the playlist format %s is not a supported format" % fmt)
   fmt = playlist_file_formats[fmt]
   ext = fmt.extensions[0]
   default = v.get("default", False)
   if default:
    if self.playlist_formats.default:
     default = False
    else:
     self.playlist_formats.default = k
   substitutions = v.get("substitutions", []) or []
   substitutions = [[to_unicode(j) for j in i] for i in substitutions]
   for i in substitutions:
    if len(i) < 2:
     continue
    if len(i) > 2:
     if bool(i[2]):
      i[0] = re.compile(i[0], re.MULTILINE|re.UNICODE)
     else:
      i[2] = False
    else:
     i += [False]
   v = PlaylistFormatSettings.Entry(
        dirname=k,
        ext=ext,
        default=default,
        format=fmt,
        title_format=to_unicode(v.get("title_format", u"$title")),
        mp3_only=v.get("mp3_only", False),
        absolute_paths=v.get("absolute_paths", True),
        substitutions=substitutions
       )
   self.playlist_formats[k] = v
  if not self.playlist_formats.default:
   raise ValueError("a default playlist path must be specified in the config"
                    " file")
  self.playlists_path = self.playlist_formats.default.dirname
  self.db_ignore_playlists = [to_unicode(i)
                              for i in config["db_ignore_playlists"] if i]
  # MP3 encoding settings
  self.ffmpeg = to_unicode(config["ffmpeg"])
  self.lame = to_unicode(config["lame"])
  self.constant_bitrate = config["constant_bitrate"]
  if self.constant_bitrate != None:
   self.constant_bitrate = int(config["constant_bitrate"].lower().rstrip("k"))
  self.vbr_quality = config["vbr_quality"]
  if self.vbr_quality != None:
   self.vbr_quality = int(self.vbr_quality)
  # Sorting tag settings
  self.sort_tag_settings = {
   "title":  dict(whitelist=[], blacklist=[]),
   "artist": dict(whitelist=[], blacklist=[]),
   "album":  dict(whitelist=[], blacklist=[])
  }
  sort_tags = config.get("sort_tags", {})
  for tag in sort_tags:
   if tag in self.sort_tag_settings:
    whitelist = sort_tags[tag].get("whitelist", [])
    if isinstance(whitelist, (int, long)):
     whitelist = bool(whitelist)
    if isinstance(whitelist, (bool, list, tuple)):
     if isinstance(whitelist, (list, tuple)):
      whitelist = [i for i in whitelist
                   if i and self.check_path(i, self.music_path, False)]
     self.sort_tag_settings[tag]["whitelist"] = whitelist
    blacklist = sort_tags[tag].get("blacklist", [])
    if isinstance(blacklist, (list, tuple)):
     blacklist = [i for i in blacklist
                  if i and self.check_path(i, self.music_path, False)]
     self.sort_tag_settings[tag]["blacklist"] = blacklist
  # Initialize song lists
  self.albums = Albums(self)
  self.artists = Artists(self)
  self.songs = Songs(self)
  self.playlists = Playlists(self)
 def _get_song_info(self, relpath):
  title, ext = os.path.splitext(os.path.basename(relpath))
  title = [title]
  artist = album = [""]
  fmt = get_format(ext)
  ret = None
  if fmt:
   cwd = os.getcwdu()
   os.chdir(self.music_path)
   if not os.path.isfile(os.path.realpath(relpath)):
    os.chdir(cwd)
    raise ValueError("The specified song does not exist or is not a regular"
                     " file or a link to one.")
   try:
    mg = mutagen.File(relpath, easy=True)
    if mg:
     title = to_unicode(mg.get("title", title)[0]
                        if mg.get("title", title)[0] != "" else title[0])
     sort_title = self._get_sort_value(mg, relpath, "title", title)
     for tag in ("artist", "performer", "albumartist"):
      if tag in mg:
       artist = to_unicode(mg.get(tag, [""])[0])
       sort_artist = self._get_sort_value(mg, relpath, tag, artist)
       break
     album = to_unicode(mg.get("album", [""])[0])
     sort_album = self._get_sort_value(mg, relpath, "album", album)
     try:
      length = mg.info.length
     except AttributeError:
      length = None
    ret = [to_unicode(relpath), title, sort_title, artist, sort_artist, album,
           sort_album, length]
   finally:
    os.chdir(cwd)
  return ret
 
 def _get_sort_value(self, mg, relpath, tag, default_value):
  def my_dirname(path):
   if os.path.isdir(os.path.realpath(os.path.join(self.music_path, path))):
    return path
   return os.path.dirname(path)
  if tag not in ("title", "artist", "performer", "albumartist", "album"):
   raise ValueError("tag must be one of title, artist, performer, albumartist,"
                    " or album")
  key = "artist" if tag in ("artist", "performer", "albumartist") else tag
  settings = self.sort_tag_settings[key]
  if (settings["whitelist"] == True or relpath in settings["whitelist"] or
      my_dirname(relpath) in settings["whitelist"]):
   if (relpath not in settings["blacklist"] and
       my_dirname(relpath) not in settings["blacklist"]):
    if tag + "sort" in mg:
     return to_unicode(mg[tag + "sort"][0]).lower()
  return sort_value(default_value)
 
 def _setup_db(self):
  new = False if os.path.exists(os.path.realpath(self.database_path)) else True
  conn = sqlite3.connect(self.database_path)
  c = conn.cursor()
  if new:
   schema = """\
CREATE TABLE "leviathan_meta" (
 "id"          integer NOT NULL PRIMARY KEY,
 "key"         text    NOT NULL UNIQUE,
 "value"       text    NOT NULL
);

CREATE TABLE "songs" (
 "id"          integer NOT NULL PRIMARY KEY,
 "relpath"     text    NOT NULL UNIQUE,
 "title"       text    NOT NULL,
 "sort_title"  text    NOT NULL,
 "artist"      text    NOT NULL,
 "sort_artist" text    NOT NULL,
 "album"       text    NOT NULL,
 "sort_album"  text    NOT NULL,
 "length"      numeric
);

CREATE TABLE "playlists" (
 "id"          integer NOT NULL PRIMARY KEY,
 "name"        text    NOT NULL UNIQUE
);

CREATE TABLE "playlist_entries" (
 "id"          integer NOT NULL PRIMARY KEY,
 "song"        integer NOT NULL,
 "playlist"    integer NOT NULL
);

CREATE INDEX "playlist_entries_song"     ON "playlist_entries" ("song");
CREATE INDEX "playlist_entries_playlist" ON "playlist_entries" ("playlist");
"""
   c.executescript(schema)
   c.execute(self.queries["add_meta"], dict(key="db_version",value=DB_VERSION))
   conn.commit()
  return conn, c
 
 def scan(self):
  self.songs.scan()
  self.playlists.scan()
 
 def check_path(self, child, parent, raise_error=False):
  valid = os.path.realpath(child).startswith(os.path.realpath(parent))
  if not valid:
   child = os.path.join(parent, child)
   valid = os.path.realpath(child).startswith(os.path.realpath(parent))
   if not valid:
    if raise_error:
     raise ValueError("The path %s is not within %s" % (child, parent))
  return valid
 
 def get_meta(self, key):
  r = self.query(self.queries["meta_value_from_key"], key=key)
  if r and r[0]:
   return r[0][0]
 
 def move(self, src, dst):
  src = self.relpath(to_unicode(src), self.music_path)
  dst = self.relpath(to_unicode(dst), self.music_path)
  cwd = os.getcwdu()
  os.chdir(self.music_path)
  if os.path.isdir(os.path.realpath(src)):
   if not os.path.exists(dst):
    os.mkdir(dst, 0755)
   if not os.path.isdir(os.path.realpath(dst)):
    raise ValueError("If src is a directory, dst must also be a directory or a"
                     " symlink to one")
   mvdir(src, dst, callback=self.update_song_path)
  else:
   if os.path.isdir(os.path.realpath(dst)):
    dst = os.path.join(dst, os.path.basename(src))
   shutil.move(src, dst)
   self.songs[src].relpath = dst
  os.chdir(cwd)
  src = os.path.join(self.music_path, src)
  dst = os.path.join(self.music_path, dst)
  for pls in self.playlists:
   for path in pls.paths.values():
    with open(path, "rb") as f:
     s = to_unicode(f.read())
    s = s.replace(src, dst)
    with open(path, "wb") as f:
     f.write(s.encode("utf8"))
 
 def query(self, query, **kwargs):
  conn, c = self._setup_db()
  c.execute(query, kwargs)
  r = c.fetchall()
  if conn.total_changes:
   conn.commit()
  c.close()
  return r
 
 def relpath(self, child, parent, raise_error=True):
  self.check_path(child, parent, raise_error)
  return os.path.relpath(os.path.realpath(child), os.path.realpath(parent))
 
 def sanitize(self, directory="", quiet=False, debug=False, level=0):
  if directory == "":
   directory = self.music_path
  albumart_filename = self.albumart_filename
  directory_rel = self.relpath(directory, self.music_path, False)
  class status:
   def __init__(self):
    self.permissions = True
    self.albumart = True
  success = status()
  try:
   ls = os.listdir(directory)
   ls.sort()
  except EnvironmentError:
   if not quiet:
    print "could not access", directory_rel
   success.permissions = False
   return False
  else:
   for i in ls:
    path = os.path.realpath(os.path.join(directory, i))
    path_rel = os.path.relpath(path, self.music_path)
    if os.path.isfile(path):
     try:
      os.chmod(path, stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IROTH)
     except EnvironmentError:
      if not quiet:
       print "could not set permissions on", path_rel
      success.permissions = False
    elif os.path.isdir(path):
     try:
      os.chmod(path, stat.S_IRWXU|stat.S_IRGRP|stat.S_IXGRP|stat.S_IROTH
                     |stat.S_IXOTH)
     except EnvironmentError:
      if not quiet:
       print "could not set permissions on", path_rel
      success.permissions = False
     self.sanitize(path, quiet, debug, level=level + 1)
   if level == 2:
    if albumart_filename not in ls:
     apic_status = None
     for i in ls:
      path = os.path.realpath(os.path.join(directory, i))
      path_rel = os.path.relpath(path, self.music_path)
      if os.path.isfile(path):
       apic_status = apic_extract(path, os.path.join(directory,
                                                     albumart_filename))
      if apic_status == True:
       if debug:
        print "made", os.path.join(directory_rel, albumart_filename)
       break
     if apic_status != True:
      if not quiet:
       print "could not find album art in", directory_rel
      success.albumart = False
  if level == 0:
   return success
 
 def __set_meta(self, key):
  qname = "update_meta" if self.get_meta(key) != None else "add_meta"
  self.query(self.queries[qname], key=key, value=value)
 
 def to_mp3(self):
  self.songs.to_mp3()
  self.playlists.save()

# End of Library class

class PlaylistFormatSettings(dict):
 Entry = collections.namedtuple("PlaylistFormatSettingsEntry",
          "dirname ext default format title_format mp3_only absolute_paths"
          " substitutions")
 class Entry(Entry):
  def path(self, name):
   return os.path.join(self.dirname, name + self.ext)
  def relpath(self, name):
   return name + self.ext
 @property
 def default(self):
  return self[self._default] if hasattr(self, "_default") else None
 @default.setter
 def default(self, path):
  if hasattr(self, "_default"):
   raise AttributeError("default is already set")
  self._default = path

def apic_extract(mp3, jpg=None):
 try:
  tags = mutagen.mp3.Open(mp3)
 except:
  return False
 data = ""
 for i in tags:
  if i.startswith("APIC"):
   data = tags[i].data
   break
 if not data:
  return None
 if jpg != None:
  out = open(jpg, "w")
  out.write(data)
  out.close()
  return True
 return data

def convert_to_mp3(in_file, out_file, ffmpeg_path, lame_path,
                   constant_bitrate=None, vbr_quality=None):
 ffmpeg_cmd = [ffmpeg_path, "-i", in_file, "-vn", "-acodec", "pcm_s16le",
               "-f", "wav", "-"]
 lame_cmd   = [lame_path, "-m", "s", "--noreplaygain"]
 if vbr_quality != None: lame_cmd += ["-V", str(vbr_quality)]
 elif constant_bitrate: lame_cmd += ["-b", str(constant_bitrate)]
 lame_cmd += ["-", out_file]
 ffmpeg_sp = subprocess.Popen(ffmpeg_cmd, shell=False, stdout=subprocess.PIPE)
 lame_sp = subprocess.Popen(lame_cmd, shell=False, stdin=ffmpeg_sp.stdout)
 finished = False
 while not finished:
  if ffmpeg_sp.poll() not in (0, None):
   lame_sp.terminate()
   raise Exception("FFmpeg exited with code " + str(ffmpeg_sp.returncode))
  if lame_sp.poll() not in (0, None):
   ffmpeg_sp.terminate()
   raise Exception("LAME exited with code " + str(lame_sp.returncode))
  if ffmpeg_sp.poll() == 0 and lame_sp.poll() == 0:
   finished = True
 in_file_ext = in_file.rsplit(".", 1)[1].lower()
 if in_file_ext in EXTENSIONS:
  in_tags  = mutagen.File(in_file, easy=True)
  out_tags = mutagen.File(out_file, easy=True)
  if None not in (in_tags, out_tags):
   for i in in_tags:
    if i in EasyID3.valid_keys:
     out_tags[i] = in_tags[i]
   try:
    out_tags.save()
   except ValueError:
    raise Exception("an unknown error occurred while converting %s" % in_file)

def custom_splitext(path, match=None):
 split = os.path.splitext(path)
 if match == None or split[1] == match:
  return split
 else:
  return (path, "")

def get_format(ext):
 ext = ext.lower().lstrip(".")
 if ext in EXTENSIONS:
  return EXTENSIONS[ext]
 return None

def main(argv):
 commands = ["sanitize", "to-mp3", "scan", "song", "playlist", "pls", "move",
             "mv", "help", "-h", "--help"]
 usage = """Usage: %s command [arguments]

Commands:        Arguments:
scan
 Adds all songs in the library and all playlists to the database.
move|mv          src dst
 Moves a song in the filesystem and updates the database and playlists to match.
playlist|pls     add|del|delete|ls|save playlist-name
 Creates, deletes, lists, or saves a playlist.
playlist|pls     ren|rename old-name new-name
 Renames a playlist.
playlist|pls     ls
 Lists all playlist names.
playlist|pls     save
 Updates all playlist files on the disk.
playlist|pls     add|remove|rm song-path playlist-name [playlist-name]...
 Adds or removes a song from one or more playlists.
playlist|pls     move|mv song-path old-playlist-name new-playlist-name
 Moves a song from one playlist to another playlist.
sanitize
 Fixes permissions and makes sure all albums with artwork have an albumart.jpg.
song             add|update|remove|rm song-path
 Adds, updates, or removes a song in the database (DOES NOT affect the file).
song             find|path[s]|search [database-field [title]] search-term
 Searches for the given text in the list of songs and prints all matching paths.
to-mp3
 Makes sure MP3 versions of all songs and playlists exist.
help|-h|--help
 Shows this usage information and exits.\
""" % argv[0]
 
 if len(argv) < 2:
  print usage
  return 2
 
 # Config file flag
 if argv[1] == "-c":
  if len(argv) < 3:
   print "Please specify a configuration file or omit -c."
   return 2
  conf_file = argv.pop(2)
  argv.pop(1)
 elif argv[1].startswith("--config-file="):
  conf_file = argv.pop(1).split("=", 1)[1]
  if conf_file == "":
   print "Please specify a configuration file or omit --config-file."
   return 2
 else:
  conf_file = os.path.expanduser("~/.leviathan.yaml")
 
 cmd = argv[1]
 
 if cmd not in commands:
  print "invalid command:", cmd
  return 2
 
 # Help flag/command
 if cmd in ("help", "-h", "--help"):
  print usage
  return 0
 
 try:
  library = Library(conf_file)
 except EnvironmentError as exc:
  print "error:", exc
  return 1
 
 # Scan command
 if cmd == "scan":
  if (len(argv) not in (2, 3)) or \
     (len(argv) == 3 and argv[2] not in ("songs", "playlists", "pls", "all")):
   print "Usage: %s scan [songs|playlists|pls|all]" % argv[0]
   return 2
  if len(argv) == 3 and argv[2] == "songs":
   library.songs.scan()
  elif len(argv) == 3 and argv[2] in ("playlists", "pls"):
   library.playlists.scan()
  else:
   library.scan()
 # Move command
 elif cmd in ("move", "mv"):
  if len(argv) < 4:
   print "Usage: %s move|mv src dst" % sys.argv[0], cmd
   return 2
  try:
   library.move(argv[2], argv[3])
  except UnicodeError:
   traceback.print_exc()
  except (EnvironmentError, ValueError) as exc:
   print exc
 # Playlist command set
 elif cmd in ("playlist", "pls"):
  if (len(argv)  < 3) or \
     (len(argv) == 3 and argv[2] not in ("ls", "save")) or \
     (len(argv) == 4 and argv[2] not in ("add","del","delete","ls","save")) or \
     (len(argv) != 5 and argv[2] in ("ren", "rename")) or \
     (len(argv) != 6 and argv[2] in ("move", "mv")) or \
     (len(argv)  > 4 and argv[2] not in ("add","move","mv","ren","rename",
                                         "remove","rm")):
   print "Usage: %s playlist|pls add|del|delete|ls|save playlist-name" % argv[0]
   print "   or: %s playlist|pls ren|rename old-name new-name" % argv[0]
   print "   or: %s playlist|pls ls|save" % argv[0]
   print "   or: %s playlist|pls add|remove|rm song-path playlist-name [playlist-name]..." % argv[0]
   print "   or: %s playlist|pls move|mv song-path old-playlist-name new-playlist-name" % argv[0]
   return 2
  elif len(argv) == 4 or argv[2] in ("rename", "ren"):
   name = fix_cli_playlist_name(library, argv[3])
   # Playlist - Add
   if argv[2] == "add":
    library.playlists.add(name)
   else:
    pls = library.playlists[name]
   # Playlist - Delete
   if argv[2] in ("del", "delete"):
    r = yes_no_prompt("Are you sure you want to delete the playlist %s?" % name)
    if not r:
     return 1
    pls.remove()
   # Playlist - List one playlist
   elif argv[2] == "ls":
    entries = pls.songs
    for i in entries:
     print i.title.encode("utf8"),
     if i.artist or i.album:
      print "(%s)"%", ".join([j for j in (i.artist,i.album) if j]).encode("utf8")
   # Playlist - Rename
   if argv[2] in ("ren", "rename"):
    new_name = fix_cli_playlist_name(library, argv[4])
    pls.rename(new_name)
   # Playlist - Save
   elif argv[2] == "save":
    pls.save()
  # Playlist - List all playlist names
  elif argv[2] == "ls":
   print ", ".join([i.name for i in library.playlists]).encode("utf8")
  # Playlist - Save all playlists
  elif argv[2] == "save":
   library.playlists.save()
  # Multiple playlists - requires a song path to be specified
  else:
   playlist_names = [fix_cli_playlist_name(library, i) for i in argv[4:]]
   song = library.songs.add(library.relpath(argv[3], library.music_path))
   # Playlist - Remove song confirmation
   if argv[2] in ("remove", "rm"):
    r = yes_no_prompt("Are you sure you want to remove %s from the"
                      " playlist(s)?" % argv[3])
    if not r:
     return 1
   # Playlist - Add or remove song
   if argv[2] in ("add", "remove", "rm"):
    for name in playlist_names:
     if name not in library.playlists:
      print "warning: ignoring playlist %s because it does not exist." % name
      continue
     pls = library.playlists[name]
     # Playlist - Add song
     if argv[2] == "add":
      pls.add_song(song)
     # Playlist - Remove song
     if argv[2] in ("remove", "rm"):
      pls.remove_song(song)
   # Playlist = Move song
   if argv[2] in ("move", "mv"):
    old_name = fix_cli_playlist_name(library, argv[4])
    new_name = fix_cli_playlist_name(library, argv[5])
    if old_name not in library.playlists:
     print "error: the playlist %s does not exist." % old_name
    if new_name not in library.playlists:
     print "error: the playlist %s does not exist." % new_name
    library.playlists[old_name].remove_song(song)
    library.playlists[new_name].add_song(song)
 # Sanitize file permissions and album art
 elif cmd == "sanitize":
  quiet = ("-q" in argv or "--quiet" in argv)
  debug = ("-d" in argv or "--debug" in argv)
  success = library.sanitize(quiet=quiet, debug=debug)
  if success.albumart == False and not quiet:
   print "* not all album directories have album art *"
  if success.permissions == False:
   print "* not all files and directories could be sanitized *"
 # Song command set
 elif cmd == "song":
  if (len(argv)  < 4) or \
     (len(argv) == 4 and argv[2] not in ("add","update","remove","rm","find",
                                         "path","paths","search")) or \
     (len(argv) == 5 and argv[2] not in ("find","path","paths","search")):
   print "Usage: %s song add|update|remove|rm song-path" % argv[0]
   print "   or: %s song find|path[s]|search [database-field [title]] search-term" % argv[0]
   return 2
  # Song - Add/Update
  if argv[2] in ("add", "update"):
   library.songs.add(library.relpath(argv[3], library.music_path))
  # Song - Remove song
  if argv[2] in ("remove", "rm"):
   song = library.songs[library.relpath(argv[3], library.music_path)]
   r = yes_no_prompt("Are you sure you want to remove the song %s from the"
                     " database?" % song.relpath)
   if not r:
    return 1
   song.remove()
  # Song - Search
  if argv[2] in ("find", "path", "paths", "search"):
   if len(argv) == 5:
    field = argv[3]
    term = argv[4]
    if term == "":
     print "Please specify a search term."
     return 2
   else:
    field = "title"
    term = argv[3]
    if term == "":
     print "Please specify the name of a song."
     return 2
   for i in library.songs.search(field, term, exact=False, sort="relpath"):
    print i.relpath
   return 0
 # to-mp3 command
 elif cmd == "to-mp3":
  library.to_mp3()
 return 0

def fix_cli_playlist_name(library, name):
 if "/" in name:
  name = os.path.relpath(name, library.playlists_path)
 name = custom_splitext(name, ".m3u")[0]
 return name

def mvdir(src, dst, callback=None, _first_level=True):
 if not os.path.exists(dst):
  os.mkdir(dst, 0755)
 if not os.path.isdir(os.path.realpath(src)):
  raise ValueError("%s is not a directory" % src)
 if not os.path.isdir(os.path.realpath(dst)):
  raise ValueError("%s is not a directory" % dst)
 for i in os.listdir(src):
  src_p, dst_p = os.path.join(src, i), os.path.join(dst, i)
  if os.path.isdir(os.path.realpath(src_p)):
   mvdir(src_p, dst_p, callback, False)
  else:
   shutil.move(src_p, dst_p)
  if callable(callback):
   callback(src_p, dst_p)
 os.rmdir(src)
 if _first_level and callback != None and not callable(callback):
  raise TypeError("callback is not callable")

def setattrs(d, _cls = None):
 setattrs_class = _cls
 if _cls == None:
  class setattrs_class: pass
 for i in d:
  if isinstance(d[i], dict):
   setattr(setattrs_class, i, setattrs(d[i]))
  else:
   setattr(setattrs_class, i, d[i])
 if _cls == None:
  return setattrs_class

def sort_value(s):
 s = to_unicode(strip_latin_diacritics(s)).lower()
 if s.startswith("the "):
  s = s.replace("the ", "", 1) + ", the"
 elif s.startswith("an "):
  s = s.replace("an ", "", 1) + ", an"
 elif s.startswith("a "):
  s = s.replace("a ", "", 1) + ", a"
 return s

# replace Latin letters with diacritical marks with the same letters without
# diacritics, preserving case
def strip_latin_diacritics(string):
 ret = string
 latin_diacritics = {
  "A": u"ÁÀĂẮẰẴẲÂẤẦẪẨǍÅǺÄǞÃȦǠĄĀẢȀȂẠẶẬḀȺǼǢ",
  "B": u"ḂḄḆɃƁƂ",
  "C": u"ĆĈČĊÇḈȻƇ",
  "D": u"ĎḊḐḌḒḎĐƉƊƋ",
  "E": u"ÉÈĔÊẾỀỄỂĚËẼĖȨḜĘĒḖḔẺȄȆẸỆḘḚɆ",
  "F": u"ḞƑ",
  "G": u"ǴĞĜǦĠĢḠǤƓ",
  "H": u"ĤȞḦḢḨḤḪH̱ĦⱧ",
  "I": u"ÍÌĬÎǏÏḮĨİĮĪỈȈȊỊḬIƗᵻ",
  "J": u"ĴJ̌Ɉ",
  "K": u"ḰǨĶḲḴꝄꝂꝀƘⱩ",
  "L": u"ĹĽĻḶḸḼḺŁŁĿȽⱠⱢꝈꝆ",
  "M": u"ḾṀṂ",
  "N": u"ŃǸŇÑṄŅṆṊṈƝȠN",
  "O": u"ÓÒŎÔỐỒỖỔǑÖȪŐÕṌṎȬȮȰØǾǪǬŌṒṐỎȌȎƠỚỜỠỞỢỌỘƟꝊꝌ",
  "P": u"ṔṖⱣꝐƤꝒꝔP",
  "Q": u"ꝘɊ",
  "R": u"ŔŘṘŖȐȒṚṜṞɌꞂⱤ",
  "S": u"ŚṤŜŠṦṠŞṢṨȘSꞄ",
  "SS": u"ẞ",
  "T": u"ŤTṪŢṬȚṰṮŦȾƬƮ",
  "U": u"ÚÙŬÛǓŮÜǗǛǙǕŰŨṸŲŪṺỦȔȖƯỨỪỮỬỰỤṲṶṴɄᵾ",
  "V": u"ṼṾƲ",
  "W": u"ẂẀŴW̊ẄẆẈꝠ",
  "X": u"ẌẊ",
  "Y": u"ÝỲŶY̊ŸỸẎȲỶỴʏɎƳ",
  "Z": u"ŹẐŽŻẒẔƵȤⱫǮꝢ",
  "a": u"áàăắằẵẳâấầẫẩǎåǻäǟãȧǡąāảȁȃạặậḁⱥᶏǽǣᶐ",
  "b": u"ḃḅḇƀᵬᶀɓƃ",
  "c": u"ćĉčċçḉȼƈɕ",
  "d": u"ďḋḑḍḓḏđᵭᶁɖɗᶑƌȡ",
  "e": u"éèĕêếềễểěëẽėȩḝęēḗḕẻȅȇẹệḙḛɇᶒᶕɚᶓᶔɝ",
  "f": u"ḟᵮᶂƒ",
  "g": u"ǵğĝǧġģḡǥᶃɠ",
  "h": u"ĥȟḧḣḩḥḫẖħⱨ",
  "i": u"íìĭîǐïḯĩiįīỉȉȋịḭıɨᶖ",
  "j": u"ĵǰȷɉʝɟʄ",
  "k": u"ḱǩķḳḵꝅꝃꝁᶄƙⱪ",
  "l": u"ĺľļḷḹḽḻłł̣ŀƚⱡɫꝉꝇɬᶅɭȴ",
  "m": u"ḿṁṃᵯᶆɱ",
  "n": u"ńǹňñṅņṇṋṉᵰɲƞᶇɳȵn̈",
  "o": u"óòŏôốồỗổǒöȫőõṍṏȭȯȱøǿǫǭōṓṑỏȍȏơớờỡởợọộɵꝋꝍ",
  "p": u"ṕṗᵽꝑᶈƥꝓꝕp̃",
  "q": u"ʠꝙɋ",
  "r": u"ŕřṙŗȑȓṛṝṟɍᵲᶉɼꞃɽɾᵳ",
  "s": u"śṥŝšṧṡẛşṣṩșᵴᶊʂȿs̩ꞅᶋᶘ",
  "ss": u"ß",
  "t": u"ťẗṫţṭțṱṯŧⱦᵵƫƭʈȶ",
  "u": u"úùŭûǔůüǘǜǚǖűũṹųūṻủȕȗưứừữửựụṳṷṵʉᶙᵿ",
  "v": u"ṽṿᶌʋⱴ",
  "w": u"ẃẁŵẘẅẇẉꝡ",
  "x": u"ẍẋᶍ",
  "y": u"ýỳŷẙÿỹẏȳỷỵɏƴ",
  "z": u"źẑžżẓẕƶᵶᶎȥʐʑɀⱬǯᶚƺꝣ"
 }
 for letter in latin_diacritics:
  for i in latin_diacritics[letter]:
   ret = ret.replace(i, letter)
 return ret

def test(conf_file=None):
 if not conf_file:
  conf_file = os.path.expanduser("~/.leviathan.yaml")
 library = Library(conf_file)
 return library

def to_unicode(s, encoding="utf8"):
 if isinstance(s, (str, buffer)):
  return unicode(s, encoding)
 return s

def yes_no_prompt(prompt="Are you sure?"):
 r = raw_input("%s (yes/[no]) " % prompt)
 while r not in ("yes", "no", ""):
  r = raw_input('Please type "yes" or "no": ')
 return True if r == "yes" else False

if __name__ == "__main__":
 try:
  sys.exit(main(sys.argv))
 except KeyboardInterrupt:
  pass
 except UnicodeError:
  traceback.print_exc()
 #except (TypeError, ValueError) as exc:
 # print "error:", exc
 # sys.exit(2)
