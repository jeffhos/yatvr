import tmdbsimple as tmdb
from datetime import date
from dataclasses import dataclass
from typing import Optional
import argparse
from pprint import pp
from pathlib import Path
import re
from simple_term_menu import TerminalMenu
import os
from dotenv import load_dotenv

VIDEO_EXTENSIONS = ['.mkv', '.m4v', '.mp4', '.avi', ".webm"]
FILE_REGEXES = [
    re.compile(r"(?P<show_name>[^/]+)\s*\((?P<year>\d{4})\)/Season (?P<season>\d+)/", re.I),
    re.compile(r"(?P<show_name>[^/]+)/Season (?P<season>\d+)/", re.I),
    re.compile(r"s(?P<season>\d+)\s*e(?P<episode>\d+)", re.I),
    re.compile(r"(?P<season>\d+)x(?P<episode>\d+)", re.I)
]
EPISODE_FORMAT_STRING = "s{season:02}e{episode:02} - {title}{extension}"
CHARACTER_REPLACEMENTS = {
    "/": " - "
}

load_dotenv()
tmdb.API_KEY = os.getenv("TVDB_API_KEY")

@dataclass
class ShowInfo:
    id: int
    name: str
    year: Optional[int]

@dataclass 
class SeasonInfo:
    id: int
    number: int

@dataclass 
class EpisodeInfo:
    pass

class NoMatchingShowException(Exception):
    pass

matched_shows_cache: dict[tuple[str, Optional[str]], ShowInfo] = {}

def find_matching_shows(guessed_show_name: str, year: Optional[str]) -> list[ShowInfo]:
    if (guessed_show_name, year) in matched_shows_cache:
        return matched_shows_cache[(guessed_show_name, year)]
    
    search = tmdb.Search()
    shows = []
    response = search.tv(query=guessed_show_name, first_air_date_year=year)
    for show in response["results"]:
        show_info = ShowInfo(id=show["id"], name=show["name"], year=None)
        try:
            show_info.year = date.fromisoformat(show["first_air_date"]).year
        except ValueError:
            pass
        shows.append(show_info)

    if len(shows) == 1:
        matched_shows_cache[(guessed_show_name, year)] = shows[0]
        return shows[0]
    elif len(shows) < 1:
        raise NoMatchingShowException(f"[ERROR] No shows matched \"{guessed_show_name}\"")
    else:
        terminal_menu = TerminalMenu([show.name for show in shows])
        selected_index = terminal_menu.show()
        if selected_index is not None:
            matched_shows_cache[(guessed_show_name, year)] = shows[selected_index]
            return shows[selected_index]
        raise NoMatchingShowException(f"[ERROR] No show chosen")

def get_episodes(show_info: ShowInfo) -> list[EpisodeInfo]:
    show = tmdb.TV(show_info.id)
    for season_info in show.info()["seasons"]:
        season = tmdb.TV_Seasons(show_info.id, season_info["season_number"])
        pp(season.info())

def rename_episode(file: Path, show_info: ShowInfo, season: Optional[int], episode: int):
    if season is None:
        print(f"[ERROR] Unable to parse season from {file.name}")
        return

    # Look up the episode info in TVDB
    episode_info = tmdb.TV_Episodes(show_info.id, season, episode)
    substitution_values = {
        "episode": episode,
        "season": season,
        "title": episode_info.info()["name"],
        "extension": file.suffix
    }
    new_name = EPISODE_FORMAT_STRING.format_map(substitution_values)
    for character, replacement in CHARACTER_REPLACEMENTS.items():
        new_name.replace(character, replacement)
    if file.name != new_name:
        print(f"[RENAME] {file.name} -> {new_name}")
        file.rename(file.parent / new_name)
    else:
        print(f"[INFO] File {file.name} already has correct name, skipping")

def rename_video(file: Path, show_name: str, year: Optional[str], season: int, episode: int):
    show = find_matching_shows(show_name, year)

    rename_episode(file, show, season, episode)

def process_video(file: Path):
    print(f"Processing {str(file)}")

    # Run through all the regexes, trying to get enough information
    show_name = None
    year = None
    season = None
    episode = None
    for regex in FILE_REGEXES:
        result = regex.search(str(file))
        if result:
            if 'show_name' in result.groupdict() and show_name is None:
                show_name = result.group('show_name')
            if 'year' in result.groupdict() and year is None:
                year = result.group('year')
            if 'season' in result.groupdict() and season is None:
                season = int(result.group('season'))
            if 'episode' in result.groupdict() and episode is None:
                episode = int(result.group('episode'))
        
        if show_name is not None and season is not None and episode is not None:
            rename_video(file, show_name, year, season, episode)
            return
        
    print(f"Error parsing episode info from {str(file)}")

def process_file(file: Path):
    if file.is_dir():
        for nested_file in file.iterdir():
            process_file(nested_file)
    elif file.is_file():
        if file.suffix in VIDEO_EXTENSIONS:
            process_video(file)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--show-id", type=str)
    args = parser.parse_args()

    for file in args.files:
        process_file(file)


if __name__ == "__main__":
    main()
