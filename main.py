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

VIDEO_EXTENSIONS = ['.mkv', '.m4v', '.mp4', '.avi', ".webm"]
SEASON_REGEX = re.compile(r"season (\d+)", re.I)
TITLE_WITH_YEAR_REGEX = re.compile(r"(.+) \((\d{4})\)")
EPISODE_REGEXES = [
    re.compile(r"s(?P<season>\d+)e(?P<episode>\d+)"),
    re.compile(r"(?P<season>\d+)x(?P<episode>\d+)"),
    re.compile(r"\s+(?P<episode>\d+)\s+")
]
EPISODE_FORMAT_STRING = "s{season:02}e{episode:02} - {title}{extension}"

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


def find_matching_shows(guessed_show_name: str, year) -> list[ShowInfo]:
    search = tmdb.Search()
    shows = []
    response = search.tv(query=guessed_show_name, first_air_date_year=year)
    for show in response["results"]:
        show_info = ShowInfo(id=show["id"], name=show["name"], year=None)
        try:
            year = date.fromisoformat(show["first_air_date"]).year
            show_info.year = year
        except ValueError:
            pass
        shows.append(show_info)
    return shows

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
    print(f"[RENAME] {file.name} -> {new_name}")
    file.rename(file.parent / new_name)

def process_episode(file: Path, show_info: ShowInfo, season: Optional[int]):
    
    # Try to find an episode number in the filename
    for pattern in EPISODE_REGEXES:
        result = pattern.search(file.name)
        if result:
            try:
                rename_episode(file, show_info, result.group("season"), result.group("episode"))
            except IndexError:
                rename_episode(file, show_info, season, result.group("episode"))
            return
    
    print(f"[ERROR] Unable to parse episode number from {file.name}")

def process_season(file: Path, show_title: str, show_year: str, season: Optional[int]):
    shows = find_matching_shows(show_title, show_year)
    if len(shows) == 1:
        process_episode(file, shows[0], season)
    elif len(shows) < 1:
        print(f"[ERROR] No shows matched \"{show_title}\"")
    else:
        terminal_menu = TerminalMenu([show.name for show in shows])
        selected_index = terminal_menu.show()
        if selected_index is not None:
            process_episode(file, shows[selected_index], season)

def process_file(file: Path):
    print(f"Processing {str(file)}")

    # Try to figure out which show this file belongs to
    
    # First, see if we're lucky and the file is in a "<show name> (<year>)/Season <season number>/<file>" hierarchy
    result = SEASON_REGEX.match(file.parent.name)
    if result:
        season = int(result.group(1))
        season_dir = file.parent
        result = TITLE_WITH_YEAR_REGEX.match(season_dir.parent.name)
        if result:
            title = result.group(1)
            year = result.group(2)
            process_season(file, title, year, season)
        else:
            title = season_dir.parent.name
            process_season(file, title, None, season)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--show-id", type=str)
    args = parser.parse_args()

    for file in args.files:
        if file.is_dir():
            for nested_file in file.iterdir():
                if nested_file.suffix in VIDEO_EXTENSIONS:
                    process_file(nested_file)
        elif file.is_file():
            if file.suffix in VIDEO_EXTENSIONS:
                process_file(file)


if __name__ == "__main__":
    main()
