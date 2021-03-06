#!/bin/bash

# Leviathan Music Manager
# A command-line utility to manage your music collection.
# 
# Copyright (C) 2010-2011, 2020 S. Zeid
# https://code.s.zeid.me/leviathan
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


# Test suite

set -e

cd "$(dirname "$0")"
SCRIPT_DIR=`pwd`
TEST_ROOT="$SCRIPT_DIR/test-library"
LIBRARY_DIR="$TEST_ROOT/Library"

function leviathan {
 python3 "$SCRIPT_DIR/leviathan.py" -c "$TEST_ROOT/leviathan.yml" "$@"
 return $?
}

function make_files {
 set +x
 (
  cat <<EOF
# Library settings
music_path:        $LIBRARY_DIR
database_path:     $TEST_ROOT/Library.sqlite3
albumart_filename: albumart.jpg
# Playlist formats
playlist_formats:
 $TEST_ROOT/Playlists:
  default:        True
  format:         m3u
  title_format:   \$title
  mp3_only:       False
  absolute_paths: True
  substitutions:
 $TEST_ROOT/Playlists - MP3 Only:
  default:        False
  format:         extm3u
  title_format:   \$title
  mp3_only:       True
  absolute_paths: True
  substitutions:
   - ["^(.)", "#\\\\1"]
 $TEST_ROOT/Playlists - WiiMC:
  default:        False
  format:         pls
  title_format:   \$title - \$artist
  mp3_only:       True
  absolute_paths: True
  substitutions:
   - [$LIBRARY_DIR, Library]
# List of playlists to ignore
db_ignore_playlists:
 - Ignore Me Please
 - Ignore Me Too
# MP3 encoding settings
ffmpeg:            ffmpeg
lame:              lame
constant_bitrate:  256k
vbr_quality:       0
# Sort tag settings
sort_tags:
 title:
  whitelist:
   - Kevin Keller Ensemble/In Absentia
  blacklist:
   -
 artist:
  whitelist:
   -
  blacklist:
   -
 album:
  whitelist:
   -
  blacklist:
   -
EOF
 ) > "$TEST_ROOT/leviathan.yml"
 (
  cat <<EOF
# Herp
$LIBRARY_DIR/Ludovico Einaudi/Divenire/10 - Ascolta.mp3
$LIBRARY_DIR/Antje Duvekot/The Near Demise of the High Wire Dancer/3 - Long Way.flac
$LIBRARY_DIR/Polyphony - Stephen Layton/Not no faceless Angel/8 - O sacrum convivium.flac
$LIBRARY_DIR/Ludovico Einaudi/Le Onde/06 - Tracce.mp3
$LIBRARY_DIR/Ludovico Einaudi/La Scala_ Concert 03 03 03/2 - 1 - Fuori dalla notte.mp3
# Derp
$LIBRARY_DIR/Ludovico Einaudi/La Scala_ Concert 03 03 03/2 - 2 - Al di là del vetro.mp3
$LIBRARY_DIR/Ludovico Einaudi/Nightbook/02 - Lady Labyrinth.mp3
$LIBRARY_DIR/Ludovico Einaudi/The Royal Albert Hall Concert/08 - The Tower.mp3
EOF
 ) > "$TEST_ROOT/Playlists/Herp Derp.m3u"
 (
  cat <<EOF
$LIBRARY_DIR/Ludovico Einaudi/Una Mattina/12 - Nuvole bianche.mp3
EOF
 ) > "$TEST_ROOT/Playlists/Ignore Me Please.m3u"
 (
  cat <<EOF
$LIBRARY_DIR/derp.mp3
EOF
 ) > "$TEST_ROOT/Playlists/Ignore Me Too.m3u"
 set -x
}

function try {
 set +xe
 "$@"
 CODE=$?
 echo $CODE
 if [ $CODE -ne 0 ]; then
  exit
 fi
 set -xe
 return 0
}

function tryn {
 set +xe
 "$@"
 CODE=$?
 echo $CODE
 if [ $CODE -eq 0 ]; then
  exit
 fi
 set -xe
 return 0
}

set -x

[ -e "$TEST_ROOT" ] && rm -r "$TEST_ROOT" || true

mkdir -p \
 "$LIBRARY_DIR" \
 "$TEST_ROOT/Playlists" \
 "$TEST_ROOT/Playlists - MP3 Only" \
 "$TEST_ROOT/Playlists - WiiMC"

mkdir -p \
 "$LIBRARY_DIR/Antje Duvekot/Snapshots" \
 "$LIBRARY_DIR/Antje Duvekot/The Near Demise of the High Wire Dancer" \
 "$LIBRARY_DIR/Kevin Keller Ensemble" \
 "$LIBRARY_DIR/Le Vent du Nord/Tromper Le Temps" \
 "$LIBRARY_DIR/Ludovico Einaudi/Divenire" \
 "$LIBRARY_DIR/Ludovico Einaudi/La Scala_ Concert 03 03 03" \
 "$LIBRARY_DIR/Ludovico Einaudi/Le Onde" \
 "$LIBRARY_DIR/Ludovico Einaudi/Nightbook" \
 "$LIBRARY_DIR/Ludovico Einaudi/The Royal Albert Hall Concert" \
 "$LIBRARY_DIR/Ludovico Einaudi/Una Mattina" \
 "$TEST_ROOT/Winifred Horan/Just One Wish"

cp    ~/"Music/Library/Antje Duvekot/Snapshots/17. Soma.mp3" "$LIBRARY_DIR/Antje Duvekot/Snapshots/"
cp    ~/"Music/Library/Antje Duvekot/The Near Demise of the High Wire Dancer/3 - Long Way.flac" "$LIBRARY_DIR/Antje Duvekot/The Near Demise of the High Wire Dancer/"
cp    ~/"Music/Library/Antje Duvekot/The Near Demise of the High Wire Dancer/7 - Scream.flac" "$LIBRARY_DIR/Antje Duvekot/The Near Demise of the High Wire Dancer/"
cp -r ~/"Music/Library/Kevin Keller Ensemble/In Absentia/" "$LIBRARY_DIR/Kevin Keller Ensemble/"
cp    ~/"Music/Library/Le Vent du Nord/Tromper Le Temps/08 - Le cœur de ma mère.mp3" "$LIBRARY_DIR/Le Vent du Nord/Tromper Le Temps/"
cp    ~/"Music/Library/Ludovico Einaudi/Divenire/03 - Monday.mp3" "$LIBRARY_DIR/Ludovico Einaudi/Divenire/"
cp    ~/"Music/Library/Ludovico Einaudi/Divenire/10 - Ascolta.mp3" "$LIBRARY_DIR/Ludovico Einaudi/Divenire/"
cp    ~/"Music/Library/Ludovico Einaudi/La Scala_ Concert 03 03 03/2 - 1 - Fuori dalla notte.mp3" "$LIBRARY_DIR/Ludovico Einaudi/La Scala_ Concert 03 03 03/"
cp    ~/"Music/Library/Ludovico Einaudi/La Scala_ Concert 03 03 03/2 - 2 - Al di là del vetro.mp3" "$LIBRARY_DIR/Ludovico Einaudi/La Scala_ Concert 03 03 03/"
cp    ~/"Music/Library/Ludovico Einaudi/Le Onde/06 - Tracce.mp3" "$LIBRARY_DIR/Ludovico Einaudi/Le Onde/"
cp    ~/"Music/Library/Ludovico Einaudi/Nightbook/02 - Lady Labyrinth.mp3" "$LIBRARY_DIR/Ludovico Einaudi/Nightbook/"
cp    ~/"Music/Library/Ludovico Einaudi/Nightbook/06 - Eros.mp3" "$LIBRARY_DIR/Ludovico Einaudi/Nightbook/"
cp    ~/"Music/Library/Ludovico Einaudi/The Royal Albert Hall Concert/04 - In Principio.mp3" "$LIBRARY_DIR/Ludovico Einaudi/The Royal Albert Hall Concert/"
cp    ~/"Music/Library/Ludovico Einaudi/The Royal Albert Hall Concert/05 - Indaco.mp3" "$LIBRARY_DIR/Ludovico Einaudi/The Royal Albert Hall Concert/"
cp    ~/"Music/Library/Ludovico Einaudi/The Royal Albert Hall Concert/08 - The Tower.mp3" "$LIBRARY_DIR/Ludovico Einaudi/The Royal Albert Hall Concert/"
cp    ~/"Music/Library/Ludovico Einaudi/Una Mattina/12 - Nuvole bianche.mp3" "$LIBRARY_DIR/Ludovico Einaudi/Una Mattina/"
cp -r ~/"Music/Library/Polyphony - Stephen Layton" "$LIBRARY_DIR/"  # include cover art and PDF booklet
cp    ~/"Music/Library/Karan Casey/Songlines/03. Ballad Of Accounting.mp3" "$TEST_ROOT/"
cp    ~/"Music/Library/Winifred Horan/Just One Wish/09. Giants Fall.mp3" "$TEST_ROOT/Winifred Horan/Just One Wish/"
cp    ~/"Music/Library/Winifred Horan/Just One Wish/11. Albatross.mp3" "$TEST_ROOT/Winifred Horan/Just One Wish/"
rm -f "$LIBRARY_DIR/Polyphony - Stephen Layton/Not no faceless Angel/8 - O sacrum convivium.mp3" &>/dev/null
make_files

try leviathan scan songs
try leviathan scan playlists
try leviathan scan pls
rm "$TEST_ROOT/Library.sqlite3"

try leviathan scan
try grep "Lady Labyrinth.mp3" "$TEST_ROOT/Playlists/Herp Derp.m3u" 
try grep "Lady Labyrinth.mp3" "$TEST_ROOT/Playlists - MP3 Only/Herp Derp.m3u" 
try grep "Lady Labyrinth.mp3" "$TEST_ROOT/Playlists - WiiMC/Herp Derp.pls"

try leviathan pls add "Test 1"
try leviathan pls add "$LIBRARY_DIR/Antje Duvekot/The Near Demise of the High Wire Dancer/3 - Long Way.flac" "Test 1"
try leviathan pls add "$LIBRARY_DIR/Antje Duvekot/The Near Demise of the High Wire Dancer/7 - Scream.flac" "Test 1"
try leviathan pls add "$LIBRARY_DIR/Ludovico Einaudi/Le Onde/06 - Tracce.mp3" "Test 1"
try leviathan pls add "$LIBRARY_DIR/Ludovico Einaudi/Nightbook/06 - Eros.mp3" "Test 1"
try leviathan pls add "$LIBRARY_DIR/Ludovico Einaudi/The Royal Albert Hall Concert/04 - In Principio.mp3" "Test 1"
try leviathan pls add "$LIBRARY_DIR/Polyphony - Stephen Layton/Not no faceless Angel/8 - O sacrum convivium.flac" "Test 1"
try leviathan pls ls "Test 1"
try leviathan pls ls "Test 1" | try grep "Tracce"
try leviathan song find artist "Antje Duvekot" | try grep "Antje Duvekot"
try leviathan song path title "Tracce" | try grep "Tracce"
try leviathan song paths sort_title "in principio" | try grep "In Principio"
try leviathan song search album "Not no faceless Angel" | try grep "Not no faceless Angel"

tryn leviathan pls add "$TEST_ROOT/03. Ballad Of Accounting.mp3" "Test 1"

try leviathan pls add "Test 2"
try leviathan pls add "$LIBRARY_DIR/Antje Duvekot/Snapshots/17. Soma.mp3" "Test 2"
try leviathan pls add "$LIBRARY_DIR/Ludovico Einaudi/The Royal Albert Hall Concert/05 - Indaco.mp3" "Test 2"
try leviathan pls add "Test 3"
try leviathan pls ls
try leviathan pls ls | grep "Test 1, Test 2, Test 3"
try leviathan pls move "$LIBRARY_DIR/Ludovico Einaudi/The Royal Albert Hall Concert/05 - Indaco.mp3" "Test 2" "Test 3"
try leviathan pls mv "$LIBRARY_DIR/Ludovico Einaudi/The Royal Albert Hall Concert/05 - Indaco.mp3" "Test 3" "Test 2"
try leviathan pls rename "Test 2" "Test_2"
try leviathan pls ren "Test_2" "Test-2"
echo "yes" | try leviathan pls remove "$LIBRARY_DIR/Ludovico Einaudi/The Royal Albert Hall Concert/05 - Indaco.mp3" "Test-2"
echo "yes" | try leviathan pls rm "$LIBRARY_DIR/Antje Duvekot/Snapshots/17. Soma.mp3" "Test-2"
echo "yes" | try leviathan pls delete "Test-2"
try leviathan pls add "Test 3"
try leviathan pls add "$LIBRARY_DIR/Antje Duvekot/Snapshots/17. Soma.mp3" "Test 3"
echo "yes" | try leviathan pls del "Test 3"

try leviathan pls add "Test 4"
try leviathan pls add "$LIBRARY_DIR/Kevin Keller Ensemble/In Absentia/01 - I. Stillness.mp3" "Test 4"
try leviathan pls add "$LIBRARY_DIR/Kevin Keller Ensemble/In Absentia/02 - II. Anticipation.mp3" "Test 4"
try leviathan pls add "$LIBRARY_DIR/Kevin Keller Ensemble/In Absentia/03 - III. Reflection.mp3" "Test 4"
try leviathan pls add "$LIBRARY_DIR/Kevin Keller Ensemble/In Absentia/04 - IV. Exhilaration.mp3" "Test 4"
try leviathan pls add "$LIBRARY_DIR/Kevin Keller Ensemble/In Absentia/05 - V. Hope.mp3" "Test 4"
try leviathan pls add "$LIBRARY_DIR/Kevin Keller Ensemble/In Absentia/06 - VI. Struggle.mp3" "Test 4"
try leviathan pls add "$LIBRARY_DIR/Kevin Keller Ensemble/In Absentia/07 - VII. Absence.mp3" "Test 4"
try leviathan pls add "$LIBRARY_DIR/Kevin Keller Ensemble/In Absentia/08 - VIII. Acceptance.mp3" "Test 4"
try leviathan pls add "$LIBRARY_DIR/Kevin Keller Ensemble/In Absentia/09 - IX. Peace.mp3" "Test 4"

try leviathan song add "$LIBRARY_DIR/Ludovico Einaudi/Divenire/03 - Monday.mp3"

# Test Unicode playlist names, Unicode normalization,
# and œ -> oe in strip_latin_diacritics.  BTW, LVDN kicks monkey ass.
try leviathan pls add "Test 5 - Français"
try leviathan pls add "$LIBRARY_DIR/Le Vent du Nord/Tromper Le Temps/08 - Le cœur de ma mère.mp3" "Test 5 - Français"
try test "`sqlite3 "$TEST_ROOT/Library.sqlite3" "SELECT sort_title FROM songs WHERE title = 'Le cœur de ma mère'"`" = "le coeur de ma mere"

mv "$TEST_ROOT/Winifred Horan" "$LIBRARY_DIR/"
try leviathan song add "$LIBRARY_DIR/Winifred Horan/Just One Wish/09. Giants Fall.mp3"
try leviathan song update "$LIBRARY_DIR/Winifred Horan/Just One Wish/11. Albatross.mp3"
try leviathan pls add "$LIBRARY_DIR/Winifred Horan/Just One Wish/09. Giants Fall.mp3" "Test 1"
try leviathan pls ls "Test 1" | try grep "$LIBRARY_DIR/Winifred Horan/Just One Wish/09. Giants Fall.mp3"
try leviathan move "$LIBRARY_DIR/Winifred Horan/Just One Wish/09. Giants Fall.mp3" "$LIBRARY_DIR/hello.mp3"
try ls "$LIBRARY_DIR/hello.mp3"
try leviathan mv "$LIBRARY_DIR/hello.mp3" "$LIBRARY_DIR/Winifred Horan/Just One Wish/09. Giants Fall.mp3"
echo "yes" | try leviathan song remove "$LIBRARY_DIR/Winifred Horan/Just One Wish/09. Giants Fall.mp3"
echo "yes" | try leviathan song rm "$LIBRARY_DIR/Winifred Horan/Just One Wish/11. Albatross.mp3"
try leviathan pls ls "Test 1" | tryn grep "Winifred Horan"

try leviathan to-mp3
try ls "$LIBRARY_DIR/Polyphony - Stephen Layton/Not no faceless Angel/8 - O sacrum convivium.mp3"
try grep "O sacrum convivium.mp3" "$TEST_ROOT/Playlists - MP3 Only/Test 1.m3u" 
try grep "O sacrum convivium.mp3" "$TEST_ROOT/Playlists - WiiMC/Test 1.pls"

try leviathan sanitize
try leviathan to-mp3
