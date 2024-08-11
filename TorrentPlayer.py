import curses
import os
import shutil
import subprocess
import tempfile
import glob
import time
import requests
import json
import shlex

# Define the base directory for saving torrents
HOME_DIR = os.path.expanduser("~")
TORRENTS_DIR = os.path.join(HOME_DIR, "torrents")

# Ensure the directory exists
if not os.path.exists(TORRENTS_DIR):
    os.makedirs(TORRENTS_DIR)

def truncate_string(s, width):
    """Truncate a string to fit within a specified width, adding ellipsis if necessary."""
    return s[:width-3] + '...' if len(s) > width else s

def truncate_filename(filename, max_length=15):
    """Truncate filenames to a maximum length while keeping the extension."""
    if len(filename) > max_length:
        name, ext = os.path.splitext(filename)
        truncated_name = name[:max_length - len(ext) - 3]
        return truncated_name + '...' + ext
    return filename

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
        if y >= height - 2:  # Skip drawing if we're at the bottom of the screen
            break
        name = truncate_string(torrent['name'], width)
        if idx == selected_row_idx:
            stdscr.attron(curses.color_pair(1))
            stdscr.addstr(y, x, name)
            stdscr.attroff(curses.color_pair(1))
        else:
            stdscr.addstr(y, x, name)

    # Draw status and help bar only if there's enough space
    if height > 2:
        stdscr.addstr(height - 2, 0, status_message[:width - 1])
    if height > 1:
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

# Function to list files in the torrent mount directory
def list_files(directory):
    try:
        files = sorted([os.path.join(directory, f) for f in os.listdir(directory)])
        return files
    except OSError as e:
        return [f"Error listing directory: {e}"]

# Function to play a video file
def play_video(stdscr, video_file):
    stdscr.clear()
    stdscr.addstr(0, 0, f"Attempting to play: {video_file}")
    stdscr.refresh()
    time.sleep(1)

    resolved_path = os.path.abspath(video_file)
    stdscr.addstr(1, 0, f"Resolved path: {resolved_path}")
    stdscr.refresh()
    time.sleep(2)

    if not os.path.exists(resolved_path):
        stdscr.addstr(2, 0, f"File not found: {resolved_path}")
        stdscr.refresh()
        time.sleep(2)
        return

    # Check file permissions
    if not os.access(resolved_path, os.R_OK):
        stdscr.addstr(2, 0, f"No read permission for file: {resolved_path}")
        stdscr.refresh()
        time.sleep(2)
        return

    # Display file size
    file_size = os.path.getsize(resolved_path)
    stdscr.addstr(2, 0, f"File size: {file_size} bytes")
    stdscr.refresh()
    time.sleep(1)

    # Try different players
    players = ["/usr/bin/mpv", "/usr/bin/mplayer", "/usr/bin/vlc"]
    for player in players:
        if os.path.exists(player):
            stdscr.addstr(3, 0, f"Playing video with {player}...")
            stdscr.refresh()
            time.sleep(1)
            try:
                quoted_path = shlex.quote(resolved_path)
                command = f"{player} {quoted_path}"
                stdscr.addstr(4, 0, f"Command: {command}")
                stdscr.refresh()
                time.sleep(1)
                result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                stdscr.addstr(5, 0, "Playback completed")
                stdscr.refresh()
                time.sleep(1)
                return
            except subprocess.CalledProcessError as e:
                stdscr.addstr(5, 0, f"Error while running {player}: {e}")
                stdscr.addstr(6, 0, f"STDOUT: {e.stdout}")
                stdscr.addstr(7, 0, f"STDERR: {e.stderr}")
                stdscr.refresh()
                time.sleep(3)

    stdscr.addstr(5, 0, "No suitable media player found.")
    stdscr.refresh()
    time.sleep(2)
# Function to play the torrent

def play_torrent(stdscr, torrent_name):
    torrent_file = os.path.join(TORRENTS_DIR, f"{torrent_name}.torrent")
    if not os.path.exists(torrent_file):
        stdscr.addstr(curses.LINES - 2, 0, f"Torrent file {torrent_name}.torrent not found.")
        stdscr.refresh()
        time.sleep(2)
        return

    mountpoint = tempfile.mkdtemp(prefix="btplay-")
    stdscr.addstr(curses.LINES - 2, 0, f"Created mountpoint: {mountpoint}")
    stdscr.refresh()
    time.sleep(1)

    try:
        mount_command = ["btfs", torrent_file, mountpoint]
        stdscr.addstr(curses.LINES - 2, 0, f"Mounting with command: {' '.join(mount_command)}")
        stdscr.refresh()
        time.sleep(1)

        try:
            subprocess.run(mount_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        except subprocess.CalledProcessError as e:
            stdscr.addstr(curses.LINES - 2, 0, f"Error mounting: {e}")
            stdscr.addstr(curses.LINES - 1, 0, f"STDOUT: {e.stdout}, STDERR: {e.stderr}")
            stdscr.refresh()
            time.sleep(3)
            return

        if not os.path.ismount(mountpoint):
            stdscr.addstr(curses.LINES - 2, 0, "BTFS mount failed")
            stdscr.refresh()
            time.sleep(2)
            return

        stdscr.addstr(curses.LINES - 2, 0, "Mount successful")
        stdscr.refresh()
        time.sleep(1)

        current_dir = mountpoint
        while True:
            files = list_files(current_dir)

            stdscr.clear()
            stdscr.addstr(0, 0, f"Current directory: {current_dir}")
            stdscr.addstr(1, 0, "Files in directory:")
            for idx, file in enumerate(files):
                if idx >= curses.LINES - 4:  # Leave space for status messages
                    break
                stdscr.addstr(idx + 2, 0, f"{idx}: {file}")

            stdscr.addstr(curses.LINES - 2, 0, "Press any key to continue, 'q' to quit")
            stdscr.refresh()

            key = stdscr.getch()
            if key == ord('q'):
                return

            directories = [f for f in files if os.path.isdir(f)]
            video_files = [f for f in files if f.lower().endswith(('.mp4', '.avi', '.mkv'))]
            all_items = directories + video_files

            if not all_items:
                stdscr.addstr(curses.LINES - 2, 0, f"No playable files or directories found in {current_dir}")
                stdscr.refresh()
                time.sleep(2)
                if current_dir != mountpoint:
                    current_dir = os.path.dirname(current_dir)
                    continue
                else:
                    return

            selected_index = 0
            while True:
                stdscr.clear()
                height, width = stdscr.getmaxyx()
                for idx, item in enumerate(all_items):
                    if idx == selected_index:
                        stdscr.attron(curses.color_pair(1))
                    is_dir = os.path.isdir(item)
                    item_name = os.path.basename(item)
                    truncated_item = truncate_filename(item_name, max_length=width - 4)
                    display_name = f"[D] {truncated_item}" if is_dir else truncated_item
                    stdscr.addstr(idx, 0, display_name)
                    if idx == selected_index:
                        stdscr.attroff(curses.color_pair(1))

                stdscr.addstr(height - 1, 0, "Use arrow keys to navigate, ENTER to select, BACKSPACE to go up, 'q' to quit.")
                stdscr.refresh()

                key = stdscr.getch()
                if key == curses.KEY_DOWN:
                    selected_index = (selected_index + 1) % len(all_items)
                elif key == curses.KEY_UP:
                    selected_index = (selected_index - 1) % len(all_items)
                elif key == ord('\n'):
                    selected_item = all_items[selected_index]
                    if os.path.isdir(selected_item):
                        current_dir = selected_item
                        break  # Break to refresh the file list with the new directory
                    else:
                        play_video(stdscr, selected_item)
                        return
                elif key == ord('\b') or key == 127:  # BACKSPACE or DEL key
                    if current_dir != mountpoint:
                        current_dir = os.path.dirname(current_dir)
                        break  # Break to refresh the file list with the parent directory
                elif key == ord('q'):
                    return

    finally:
        # Attempt to unmount and delete the temporary directory
        try:
            unmount_command = ["fusermount", "-u", mountpoint]
            stdscr.addstr(curses.LINES - 2, 0, f"Unmounting with command: {' '.join(unmount_command)}")
            stdscr.refresh()
            time.sleep(1)
            subprocess.run(unmount_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        except subprocess.CalledProcessError as e:
            stdscr.addstr(curses.LINES - 2, 0, f"Error unmounting: {e}")
            stdscr.addstr(curses.LINES - 1, 0, f"STDOUT: {e.stdout}, STDERR: {e.stderr}")
            stdscr.refresh()
            time.sleep(3)
        try:
            shutil.rmtree(mountpoint)
            stdscr.addstr(curses.LINES - 2, 0, f"Removed directory: {mountpoint}")
            stdscr.refresh()
            time.sleep(1)
        except Exception as e:
            stdscr.addstr(curses.LINES - 2, 0, f"Error removing directory: {e}")
            stdscr.refresh()
            time.sleep(2)

# Function to list torrents
def list_torrents(stdscr):
    torrent_files = glob.glob(os.path.join(TORRENTS_DIR, '*.torrent'))
    if not torrent_files:
        stdscr.addstr(0, 0, "No .torrent files found.")
        stdscr.refresh()
        time.sleep(2)
        return

    selected_index = 0
    while True:
        stdscr.clear()
        height, width = stdscr.getmaxyx()
        for idx, file in enumerate(torrent_files):
            if idx == selected_index:
                stdscr.attron(curses.color_pair(1))
            truncated_file = truncate_filename(os.path.basename(file), max_length=width)
            stdscr.addstr(idx, 0, truncated_file)
            if idx == selected_index:
                stdscr.attroff(curses.color_pair(1))
        stdscr.addstr(height - 1, 0, "Use arrow keys to navigate, ENTER to select and play.")
        stdscr.refresh()

        key = stdscr.getch()
        if key == curses.KEY_DOWN:
            selected_index = (selected_index + 1) % len(torrent_files)
        elif key == curses.KEY_UP:
            selected_index = (selected_index - 1) % len(torrent_files)
        elif key == ord('\n'):
            torrent_file = torrent_files[selected_index]
            return os.path.basename(torrent_file).replace('.torrent', '')
        elif key == ord('q'):
            return None

# Main function to handle user interaction
def main(stdscr):
    curses.curs_set(0)
    curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE)

    while True:
        stdscr.clear()
        stdscr.addstr(0, 0, "1. List available torrents")
        stdscr.addstr(1, 0, "2. Search torrents")
        stdscr.addstr(2, 0, "q. Quit")
        stdscr.refresh()

        key = stdscr.getch()
        if key == ord('1'):
            # List available torrents
            torrent_name = list_torrents(stdscr)
            if torrent_name:
                play_torrent(stdscr, torrent_name)
        elif key == ord('2'):
            # Search for torrents
            query = draw_search_prompt(stdscr)
            torrents, next_page = search_torrents(query)
            if torrents is None:
                stdscr.addstr(curses.LINES - 2, 0, "Failed to fetch torrents.")
                stdscr.refresh()
                time.sleep(2)
                continue

            selected_row_idx = 0
            while True:
                draw_menu(stdscr, torrents, selected_row_idx)
                key = stdscr.getch()

                if key == curses.KEY_DOWN:
                    selected_row_idx = (selected_row_idx + 1) % len(torrents)
                elif key == curses.KEY_UP:
                    selected_row_idx = (selected_row_idx - 1) % len(torrents)
                elif key == ord('\n'):
                    torrent = torrents[selected_row_idx]
                    # Play the selected torrent
                    play_torrent(stdscr, torrent['name'])
                    break
                elif key == ord('q'):
                    return
                elif key == ord('s'):
                    # Save the selected torrent
                    torrent = torrents[selected_row_idx]
                    save_torrent_info(torrent)
                    stdscr.addstr(curses.LINES - 2, 0, f"Saved torrent info to {torrent['name']}.json")
                    stdscr.refresh()
                    time.sleep(2)
                elif key == ord('d'):
                    # Download metadata
                    torrent = torrents[selected_row_idx]
                    download_metadata(torrent['infohash'], torrent['name'], stdscr)
                    break
                elif key == curses.KEY_RIGHT and next_page:
                    torrents, next_page = search_torrents(query, after=next_page)
                    if torrents is None:
                        stdscr.addstr(curses.LINES - 2, 0, "Failed to fetch next page.")
                        stdscr.refresh()
                        time.sleep(2)
                    else:
                        selected_row_idx = 0
                elif key == curses.KEY_LEFT:
                    # No previous page handling for this example
                    stdscr.addstr(curses.LINES - 2, 0, "Previous page handling not implemented.")
                    stdscr.refresh()
                    time.sleep(2)
        elif key == ord('q'):
            return

if __name__ == "__main__":
    curses.wrapper(main)
