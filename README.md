I made this program with the goal of making a karaoke player with the smallest attack surface possible, only using packages available on the termux and debian repositories.

How it works:
1. Configuration Management
Upon execution, the script initializes a karaoke_config.json file if it does not already exist.
This configuration controls:
 -Reserved screen space for lyrics and the size of the "buffer zone".
 -Performance toggles, such as whether to save processed cache files or run in a text-only mode.
2. Subtitle Parsing
The load_srt function processes standard SRT files by splitting the content into blocks using regex. It extracts:
-Timestamps, which are converted from HH:MM:SS,mmm format into total milliseconds.
-Text content, which is indexed and sorted by start time for fast lookup during playback.
3. Video Pre-processing & Caching
To ensure smooth playback in the terminal, the script optimizes the video before display:
FFmpeg Integration: The script uses ffprobe to determine video duration and ffmpeg to scale the video to terminal-compatible dimensions.
Format Conversion: It converts the video stream into a raw grayscale pixel format (-pix_fmt gray) at 25 frames per second.
Caching: This raw data is saved to a temporary binary file (.<video_basename>_<width>x<height>.cache) to avoid re-processing the video on subsequent runs.The script deletes this cache after playback unless configured otherwise.
4. Rendering Engine
The playback loop synchronizes three distinct elements:
Audio: A subprocess of mpv handles audio playback in the background to ensure no latency between the terminal output and the sound.
ASCII Video: The script reads the cached raw bytes, mapping pixel intensity (0–255) to a string of ASCII characters (e.g.,  .'^...$@`), and prints these character grids to the terminal.
Dynamic Layout: The rendering window uses shutil.get_terminal_size() to adjust the aspect ratio of the video and the number of lyric lines in real-time, ensuring the UI fits the current terminal window.
5. Synchronization
The script uses the system clock (time.time()) to track elapsed time since the start of audio playback. It calculates which specific lyric block to highlight by comparing this elapsed time against the start/end timestamps of the parsed SRT data.


Usage:
python <video_path> <srt_path>. You have to use a video file if the video mode is enabled.
