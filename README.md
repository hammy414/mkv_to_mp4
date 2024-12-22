# MKV to MP4 Converter

A Python-based utility that automatically watches directories for MKV files and converts them to MP4 format using FFmpeg. Written by Josh Sternfeld for educational purposes.

## Features

- Automatic directory watching for new MKV files
- Recursive scanning of subdirectories
- Real-time progress bar during conversion
- Maintains original video quality (uses copy codec for video)
- Converts audio to AAC format
- Detailed logging
- Handles existing MKV files on startup
- Displays video information (resolution, size, duration)
- Automatically removes original MKV files after successful conversion

## Prerequisites

- Python 3.6 or higher
- FFmpeg installed and accessible in system PATH
- Required Python packages:
  ```
  tqdm
  watchdog
  ```

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/mkv_to_mp4.git
   cd mkv_to_mp4
   ```

2. Create and activate a virtual environment (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install required packages:
   ```bash
   pip install -r requirements.txt
   ```

4. Ensure FFmpeg is installed:
   - **Windows**: Download from [FFmpeg website](https://ffmpeg.org/download.html) and add to PATH
   - **macOS**: Install via Homebrew: `brew install ffmpeg`
   - **Linux**: Install via package manager: `sudo apt install ffmpeg` (Ubuntu/Debian)

## Usage

Run the script with a directory path as an argument:

```bash
python mkv_converter.py /path/to/watch/directory
```

The script will:
1. Scan for existing MKV files in the specified directory and its subdirectories
2. Convert any found MKV files to MP4
3. Continue watching for new MKV files and convert them automatically
4. Create a log file (mkv_converter.log) in the watch directory

### Progress Information

During conversion, you'll see:
- File being processed
- Video resolution
- File size
- Duration
- Real-time conversion progress
- Completion status

To stop the converter, press Ctrl+C.

## Technical Details

- Video codec is copied directly (no re-encoding)
- Audio is converted to AAC format
- Temporary files are used during conversion to prevent incomplete files
- Conversion verification ensures output file integrity
- Failed conversions are logged and temporary files are cleaned up

## Logging

The script creates a log file (mkv_converter.log) in the watch directory, containing:
- Conversion start/completion times
- Errors and exceptions
- File operations

## License

This project is open source and available under the MIT License. Feel free to use, modify, and distribute as needed.

## Disclaimer

This tool was created for educational purposes. Please ensure you have the right to modify any video files you process with this tool. The author is not responsible for any misuse of this software.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Author

Josh Sternfeld

## Acknowledgments

- FFmpeg for video processing capabilities
- Python watchdog library for file system monitoring
- tqdm for progress bar functionality

## Support

For issues, questions, or contributions, please open an issue on the GitHub repository.