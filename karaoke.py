import os
import sys
import time
import re
import subprocess
import shutil
import json
from datetime import datetime

class Style:
    CLEAR = "\033[H\033[J"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[96m"
    GRAY = "\033[90m"
    RESET = "\033[0m"

def load_config(config_file="karaoke_config.json"):
    default_config = {
        "reserved_for_lyrics": 45,
        "lyrics_lines_needed": 15,
        "size_buffer_zone": 3,
        "save_render_files": False,
        "lyrics_only_mode": False
    }

    if not os.path.exists(config_file):
        with open(config_file, 'w') as f:
            json.dump(default_config, f, indent=4)
        return default_config

    try:
        with open(config_file, 'r') as f:
            user_config = json.load(f)
            # Merge with defaults in case of missing keys
            return {**default_config, **user_config}
    except Exception:
        print("Warning: Could not read config file. Using defaults.")
        return default_config

def parse_srt_time(time_str):
    time_str = time_str.replace(',', '.')
    t = datetime.strptime(time_str.strip(), "%H:%M:%S.%f")
    return (
        t.hour * 3600000 +
        t.minute * 60000 +
        t.second * 1000 +
        t.microsecond // 1000
    )

def load_srt(srt_path):
    if not os.path.exists(srt_path):
        print(f"Error: Subtitle file '{srt_path}' not found.")
        sys.exit(1)

    with open(srt_path, 'r', encoding='utf-8') as f:
        content = f.read().strip()

    blocks = re.split(r'\n\s*\n', content)
    lyrics = []
    
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) >= 3:
            times = lines[1].split('-->')
            if len(times) == 2:
                start = parse_srt_time(times[0])
                end = parse_srt_time(times[1])
                text = " ".join(lines[2:])
                lyrics.append({'start': start, 'end': end, 'text': text})
                
    return sorted(lyrics, key=lambda x: x['start'])

def get_lyrics_window(lyrics, current_time, lines_needed=12):
    current_idx = -1
    for i, lyric in enumerate(lyrics):
        if lyric['start'] <= current_time <= lyric['end']:
            current_idx = i
            break
            
    if current_idx == -1:
        for i, lyric in enumerate(lyrics):
            if lyric['start'] > current_time:
                current_idx = i - 0.5
                break
        else:
            current_idx = len(lyrics) - 1

    window_lines = []
    lines_above = 4
    lines_below = max(2, lines_needed - lines_above - 1)
    
    target_idx = int(current_idx + 0.5) if isinstance(current_idx, float) else current_idx
    start_window = max(0, target_idx - lines_above)
    end_window = min(len(lyrics), target_idx + lines_below + 1)
    
    if target_idx < lines_above:
        for _ in range(lines_above - target_idx):
            window_lines.append("")

    for idx in range(start_window, end_window):
        lyric_text = lyrics[idx]['text']
        if idx == current_idx:
            window_lines.append(f"{Style.BOLD}{Style.CYAN}🎤 {lyric_text}{Style.RESET}")
        elif isinstance(current_idx, float) and idx == int(current_idx + 0.5):
            window_lines.append(f"{Style.BOLD}{Style.GRAY}⏳ [Intro/Bridge] next: {lyric_text}{Style.RESET}")
        else:
            window_lines.append(f"{Style.DIM}{Style.GRAY}{lyric_text}{Style.RESET}")
            
    while len(window_lines) < lines_needed:
        window_lines.append("")
        
    return window_lines

def get_video_duration(video_path):
    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        return float(result.stdout.strip())
    except Exception:
        return 0.0

def pre_process_video(video_path, width, height, temp_file):
    duration = get_video_duration(video_path)

    ffmpeg_cmd = [
        'ffmpeg', '-y',
        '-i', video_path,
        '-vf', f'scale={width}:{height}:flags=lanczos,unsharp=5:5:1.0:5:5:0.0',
        '-r', '25', # Force 25 fps to match your playback loop
        '-f', 'rawvideo',
        '-pix_fmt', 'gray',
        '-'
    ]

    if duration > 0:
        ffmpeg_cmd.insert(1, '-progress')
        ffmpeg_cmd.insert(2, 'pipe:2')

    player = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    print(f"\n{Style.BOLD}{Style.CYAN}⚙️ PRE-PROCESSING COMPACT VIDEO...{Style.RESET}")

    with open(temp_file, 'wb') as out_f:
        while player.poll() is None:
            chunk = player.stdout.read(4096)
            if chunk:
                out_f.write(chunk)

            if duration > 0:
                try:
                    os.set_blocking(player.stderr.fileno(), False)
                    err_lines = player.stderr.read(1024).decode('utf-8', errors='ignore')
                    if "out_time_us" in err_lines:
                        time_match = re.findall(r'out_time_us=(\d+)', err_lines)
                        if time_match:
                            current_us = float(time_match[-1])
                            progress = min(1.0, (current_us / 1000000.0) / duration)
                            bar_len = 30
                            filled = int(bar_len * progress)
                            bar = "█" * filled + "░" * (bar_len - filled)
                            sys.stdout.write(f"\r[{bar}] {int(progress * 100)}% Optimized")
                            sys.stdout.flush()
                except Exception:
                    pass
            time.sleep(0.005)

    remaining_data = player.stdout.read()
    if remaining_data:
        with open(temp_file, 'ab') as out_f:
            out_f.write(remaining_data)

    player.wait()
    sys.stdout.write(Style.CLEAR)
    sys.stdout.flush()

def play_optimized_karaoke(video_path, srt_path, config):
    lyrics = load_srt(srt_path)
    columns, rows = shutil.get_terminal_size()

    # Load settings from config
    reserved_for_lyrics = config["reserved_for_lyrics"]
    lyrics_lines_needed = config["lyrics_lines_needed"]
    buffer_zone = config["size_buffer_zone"]
    save_render = config["save_render_files"]
    lyrics_only = config["lyrics_only_mode"]

    # 1. DYNAMIC VIDEO SIZE
    video_width = max(40, columns - reserved_for_lyrics)
    video_height = int(video_width / 3.2)

    if video_height > (rows - 4):
        video_height = rows - 4
        video_width = int(video_height * 3.2)

    video_width = max(1, video_width - buffer_zone)
    video_height = max(1, video_height - buffer_zone)

    # 2. FLUID LYRIC HEIGHT
    layout_height = max(lyrics_lines_needed, rows - 4)

    frames = []
    total_frames = 0
    frame_delay = 1.0 / 25.0

    if not lyrics_only:
        # Create a unique cache file name based on the video and calculated resolution
        video_basename = os.path.splitext(os.path.basename(video_path))[0]
        cache_file = f".{video_basename}_{video_width}x{video_height}.cache"

        if not os.path.exists(cache_file) or os.path.getsize(cache_file) == 0:
            pre_process_video(video_path, video_width, video_height, cache_file)
        else:
            print(f"\n{Style.BOLD}{Style.CYAN}📁 LOADING CACHED RENDER: {cache_file}{Style.RESET}")
            time.sleep(1)

        ascii_chars = " .'`^\",:;Il!i><~+_-?][}{1)(|/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"
        frame_size = video_width * video_height

        with open(cache_file, 'rb') as f:
            while True:
                frame_bytes = f.read(frame_size)
                if not frame_bytes or len(frame_bytes) < frame_size:
                    break

                frame_lines = []
                for r in range(video_height):
                    row_bytes = frame_bytes[r * video_width : (r + 1) * video_width]
                    row_str = "".join([ascii_chars[pixel * len(ascii_chars) // 256] for pixel in row_bytes])
                    frame_lines.append(row_str)
                frames.append(frame_lines)

        if not save_render and os.path.exists(cache_file):
            os.remove(cache_file)

        total_frames = len(frames)
        if total_frames == 0:
            print("Error: Structural video buffer extraction failed.")
            return

    # Start audio playback
    mpv_cmd = ['mpv', '--no-video', '--quiet', '--really-quiet', video_path]
    try:
        audio_player = subprocess.Popen(mpv_cmd)
    except FileNotFoundError:
        print("Error: 'mpv' required for audio playback.")
        sys.exit(1)

    start_sys_time = time.time()
    sys.stdout.write(Style.CLEAR)

    try:
        while audio_player.poll() is None:
            elapsed_time = time.time() - start_sys_time
            current_ms = int(elapsed_time * 1000)

            karaoke_window = get_lyrics_window(lyrics, current_ms, lines_needed=layout_height)

            sys.stdout.write("\033[H")
            if lyrics_only:
                print(f"{Style.BOLD}{Style.CYAN} 🎤 LYRICS ONLY MODE {Style.RESET}" + "─" * (columns - 23))
            else:
                print(f"{Style.BOLD}{Style.CYAN} 🎬 COMPACT TERMINAL KARAOKE {Style.RESET}" + "─" * (columns - 30))

            for r in range(layout_height):
                if lyrics_only:
                    video_line = ""
                    divider = ""
                else:
                    if r < video_height and total_frames > 0:
                        frame_idx = min(int(elapsed_time / frame_delay), total_frames - 1)
                        video_line = frames[frame_idx][r]
                    else:
                        video_line = " " * video_width
                    divider = f" {Style.GRAY}┃{Style.RESET} "

                lyric_line = karaoke_window[r] if r < len(karaoke_window) else ""

                sys.stdout.write(f"\033[K")
                print(f"{Style.GRAY}{video_line}{Style.RESET}{divider}{lyric_line}")

            sys.stdout.flush()
            time.sleep(0.01)

    except KeyboardInterrupt:
        pass
    finally:
        audio_player.terminate()
        audio_player.wait()
        sys.stdout.write(Style.RESET)
        print(f"\nPlayback stopped.")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 ascii_karaoke.py <path_to_video> <path_to_srt>")
        sys.exit(1)

    current_config = load_config()
    play_optimized_karaoke(sys.argv[1], sys.argv[2], current_config)
