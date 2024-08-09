import curses
import os
import requests
import json
import subprocess
import time

# Define the base directory for saving torrents
HOME_DIR = os.path.expanduser("~")
TORRENTS_DIR = os.path.join(HOME_DIR, "torrents")

# Ensure the directory exists
if not os.path.exists(TORRENTS_DIR):
    os.makedirs(TORRENTS_DIR)

# Function to fetch torrents
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
        response.raise_for_status()  # Check for HTTP errors
        data = response.json()  # Parse JSON response

        torrents = data.get('torrents', [])
        next_page = data.get('next', None)

        return torrents, next_page
    except requests.exceptions.RequestException as e:
        return None, None

# Function to draw the search prompt
def draw_search_prompt(stdscr):
    curses.echo()
    stdscr.clear()
    stdscr.addstr(0, 0, "Enter search query: ")
    stdscr.refresh()
    query = stdscr.getstr(1, 0, 60).decode('utf-8')
    curses.noecho()
    return query

# Function to draw the results menu
def draw_menu(stdscr, torrents, selected_row_idx, status_message=""):
    stdscr.clear()
    height, width = stdscr.getmaxyx()

    # Draw the torrents list
    for idx, torrent in enumerate(torrents):
        x = 0
        y = idx + 1
        if idx == selected_row_idx:
            stdscr.attron(curses.color_pair(1))
            stdscr.addstr(y, x, f"{torrent['name'][:width-1]}")
            stdscr.attroff(curses.color_pair(1))
        else:
            stdscr.addstr(y, x, f"{torrent['name'][:width-1]}")

    # Draw status and help bar
    stdscr.addstr(height - 2, 0, status_message[:width - 1])
    stdscr.addstr(height - 1, 0, "Arrow Up/Down: Navigate | Right: Next Page | Left: Previous Page | 's': Save | 'd': Download Metadata | 'q': Quit")
    stdscr.refresh()

# Function to fetch tracker list
def fetch_trackers():
    trackers_url = "https://raw.githubusercontent.com/ngosang/trackerslist/master/trackers_all.txt"
    try:
        response = requests.get(trackers_url)
        response.raise_for_status()
        trackers = response.text.splitlines()
        return trackers
    except requests.exceptions.RequestException as e:
        return []

# Function to save selected torrent info to a file
def save_torrent_info(torrent):
    filename = f"{torrent['name']}.json"
    file_path = os.path.join(TORRENTS_DIR, filename)
    with open(file_path, 'w') as f:
        json.dump(torrent, f, indent=4)
    return file_path

# Function to rename the downloaded torrent file
def rename_torrent_file(old_name, new_name):
    old_path = os.path.join(TORRENTS_DIR, old_name)
    new_path = os.path.join(TORRENTS_DIR, new_name)
    if os.path.exists(old_path):
        os.rename(old_path, new_path)
        return new_path
    return None

# Function to download metadata using aria2c
def download_metadata(infohash, name, stdscr):
    trackers = fetch_trackers()
    if not trackers:
        stdscr.addstr(curses.LINES - 2, 0, "Failed to fetch trackers.")
        stdscr.refresh()
        time.sleep(2)
        return

    magnet_link = f"magnet:?xt=urn:btih:{infohash}&dn={name}"
    tracker_params = "&".join(f"tr={tracker}" for tracker in trackers if tracker)
    torrent_filename = f"{infohash}.torrent"  # Temporary name based on infohash

    # Prepare the command
    command = [
        "aria2c",
        "--bt-metadata-only=true",
        "--bt-save-metadata=true",
        "--dir=" + TORRENTS_DIR,  # Directory where torrent file will be saved
        "--out=" + torrent_filename,  # Name of the saved torrent file
        f"{magnet_link}&{tracker_params}"
    ]

    # Execute the command and update status
    try:
        # Display progress
        stdscr.addstr(curses.LINES - 2, 0, f"Downloading metadata for {name}...")
        stdscr.refresh()
        result = subprocess.run(command, check=True, text=True, capture_output=True)
        # Rename the file after download
        rename_torrent_file(torrent_filename, f"{name}.torrent")
        stdscr.addstr(curses.LINES - 2, 0, f"Download complete: {name}.torrent")
        stdscr.refresh()
        time.sleep(2)
    except subprocess.CalledProcessError as e:
        stdscr.addstr(curses.LINES - 2, 0, f"Error while running aria2c: {e}")
        stdscr.refresh()
        time.sleep(2)

# Main function to run the UI
def main(stdscr):
    curses.curs_set(0)
    curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE)

    # Step 1: Get the search query
    query = draw_search_prompt(stdscr)

    # Step 2: Fetch the results
    number_of_results = 25
    torrents, next_page = search_torrents(query, number_of_results)
    selected_row_idx = 0
    current_page = 1

    while True:
        draw_menu(stdscr, torrents, selected_row_idx)
        key = stdscr.getch()

        if key == curses.KEY_UP and selected_row_idx > 0:
            selected_row_idx -= 1
        elif key == curses.KEY_DOWN and selected_row_idx < len(torrents) - 1:
            selected_row_idx += 1
        elif key == curses.KEY_RIGHT and next_page:
            torrents, next_page = search_torrents(query, number_of_results, after=next_page)
            selected_row_idx = 0
            current_page += 1
        elif key == curses.KEY_LEFT and current_page > 1:
            previous_page = torrents[0]['rowid'] - number_of_results
            torrents, next_page = search_torrents(query, number_of_results, after=previous_page)
            selected_row_idx = 0
            current_page -= 1
        elif key == ord('s'):
            file_path = save_torrent_info(torrents[selected_row_idx])
            stdscr.addstr(curses.LINES - 2, 0, f"Saved to {file_path}")
            stdscr.refresh()
            stdscr.getch()
        elif key == ord('d'):
            torrent = torrents[selected_row_idx]
            download_metadata(torrent['infohash'], torrent['name'], stdscr)
        elif key == ord('q'):
            break

if __name__ == "__main__":
    curses.wrapper(main)
