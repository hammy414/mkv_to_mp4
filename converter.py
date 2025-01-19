import os
import time
import argparse
from pathlib import Path
import subprocess
import logging
import shutil
import json
import re
from datetime import datetime
from tqdm import tqdm
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class FFmpegProgress:
    def __init__(self, duration):
        self.duration = duration
        self.progress_bar = tqdm(
            total=100,
            desc="Converting",
            bar_format='{desc}: {percentage:3.1f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]'
        )
        
    def update(self, current_time):
        progress = (current_time / self.duration) * 100
        self.progress_bar.n = progress
        self.progress_bar.refresh()
        
    def close(self):
        self.progress_bar.close()

class MKVHandler(FileSystemEventHandler):
    def __init__(self, root_dir, target_resolution=None, encoding_preset='medium', 
                 crf=23, profile='high', tune=None, maxrate=None, bufsize=None):
        self.root_dir = Path(root_dir)
        self.target_resolution = target_resolution
        self.encoding_preset = encoding_preset
        self.crf = crf
        self.profile = profile
        self.tune = tune
        self.maxrate = maxrate
        self.bufsize = bufsize or (maxrate * 2 if maxrate else None)  # Default buffer size is 2x maxrate
        self.setup_logging()
        self.scan_existing_files()

    def setup_logging(self):
        """Configure logging settings for the MKV handler"""
        log_dir = self.root_dir / 'logs'
        log_dir.mkdir(exist_ok=True)
        
        log_file = log_dir / f'mkv_converter_{datetime.now().strftime("%Y%m%d")}.log'
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        logging.info(f"Starting MKV converter with root directory: {self.root_dir}")

    def scan_existing_files(self):
        """Scan for existing MKV files in the root directory"""
        logging.info(f"Scanning for existing MKV files in {self.root_dir}")
        for mkv_file in self.root_dir.rglob('*.mkv'):
            logging.info(f"Found existing MKV file: {mkv_file}")
            self.convert_mkv_to_mp4(str(mkv_file))

    def get_output_path(self, input_path):
        """Generate the output path for the converted file"""
        return input_path.with_suffix('.mp4')

    def get_video_info(self, input_path):
        """Get video information using ffprobe"""
        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                str(input_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                return None
                
            probe_data = json.loads(result.stdout)
            
            # Find video stream
            video_stream = next((s for s in probe_data['streams'] if s['codec_type'] == 'video'), None)
            if not video_stream:
                return None
                
            return {
                'width': int(video_stream['width']),
                'height': int(video_stream['height']),
                'resolution': f"{video_stream['width']}x{video_stream['height']}",
                'duration': float(probe_data['format']['duration']),
                'size': round(float(probe_data['format']['size']) / (1024*1024), 2)  # Convert to MB
            }
        except Exception as e:
            logging.error(f"Error getting video info: {str(e)}")
            return None

    def parse_resolution(self, resolution_str):
        """Parse resolution string to width and height"""
        if not resolution_str:
            return None
            
        if 'p' in resolution_str.lower():
            height = int(resolution_str.lower().replace('p', ''))
            width = int(height * 16 / 9)  # Assume 16:9 aspect ratio
            return (width, height)
        elif 'x' in resolution_str.lower():
            width, height = map(int, resolution_str.lower().split('x'))
            return (width, height)
        return None

    def verify_conversion(self, output_path):
        """Verify that the converted file exists and has non-zero size"""
        if not output_path.exists():
            return False
        return output_path.stat().st_size > 0

    def get_recommended_bitrate(self, width, height, fps=30):
        """Calculate recommended bitrate based on resolution"""
        pixels = width * height * fps
        # Bitrates for different resolutions (in Mbps)
        if height <= 480:  # DVD quality
            return "1.5M"
        elif height <= 720:  # HD
            return "2.5M"
        elif height <= 1080:  # Full HD
            return "4M"
        else:  # 4K and above
            return "8M"

    def convert_mkv_to_mp4(self, mkv_path):
        try:
            input_path = Path(mkv_path)
            output_path = self.get_output_path(input_path)
            temp_output_path = output_path.with_suffix('.temp.mp4')
            
            video_info = self.get_video_info(input_path)
            if not video_info:
                logging.error(f"Could not get video info for {input_path}")
                return

            target_dims = self.parse_resolution(self.target_resolution)
            needs_downscale = False
            if target_dims:
                target_width, target_height = target_dims
                current_height = video_info['height']
                if current_height > target_height:
                    needs_downscale = True

            # Calculate recommended bitrate if not specified
            if not self.maxrate:
                if needs_downscale:
                    self.maxrate = self.get_recommended_bitrate(target_width, target_height)
                else:
                    self.maxrate = self.get_recommended_bitrate(video_info['width'], video_info['height'])
                self.bufsize = f"{int(float(self.maxrate[:-1]) * 2)}M"

            print(f"\nProcessing: {input_path.relative_to(self.root_dir)}")
            print(f"Current Resolution: {video_info['resolution']}")
            if needs_downscale:
                print(f"Target Resolution: {target_width}x{target_height}")
            print(f"Size: {video_info['size']} MB")
            print(f"Duration: {time.strftime('%H:%M:%S', time.gmtime(video_info['duration']))}")
            print(f"Encoding Settings:")
            print(f"- Preset: {self.encoding_preset}")
            print(f"- CRF: {self.crf}")
            print(f"- Profile: {self.profile}")
            print(f"- Max Bitrate: {self.maxrate}")
            print(f"- Buffer Size: {self.bufsize}")
            if self.tune:
                print(f"- Tune: {self.tune}")
            
            cmd = [
                'ffmpeg',
                '-i', str(input_path),
                '-c:a', 'aac',
                '-b:a', '128k',  # Audio bitrate
                '-strict', 'experimental',
            ]
            
            # Video encoding settings
            if needs_downscale or self.maxrate:
                cmd.extend([
                    '-c:v', 'libx264',
                    '-preset', self.encoding_preset,
                    '-crf', str(self.crf),
                    '-profile:v', self.profile,
                    '-maxrate', self.maxrate,
                    '-bufsize', self.bufsize,
                    '-movflags', '+faststart',  # Enable fast start for streaming
                ])
                
                if self.tune:
                    cmd.extend(['-tune', self.tune])
                
                if needs_downscale:
                    cmd.extend(['-vf', f'scale={target_width}:{target_height}'])
            else:
                cmd.extend(['-c:v', 'copy'])
            
            cmd.extend([
                '-y',
                '-progress', 'pipe:1',
                str(temp_output_path)
            ])
            
            progress = FFmpegProgress(video_info['duration'])
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                time_match = re.search(r'out_time_ms=(\d+)', line)
                if time_match:
                    current_time = int(time_match.group(1)) / 1000000
                    progress.update(current_time)
            
            progress.close()
            
            if process.returncode == 0 and self.verify_conversion(temp_output_path):
                shutil.move(str(temp_output_path), str(output_path))
                logging.info(f"Successfully converted {input_path.name}")
                
                # Get final file size
                final_size = round(output_path.stat().st_size / (1024*1024), 2)
                original_size = video_info['size']
                size_reduction = round(((original_size - final_size) / original_size) * 100, 1)
                
                print(f"✓ Completed: {output_path.relative_to(self.root_dir)}")
                print(f"Original Size: {original_size} MB")
                print(f"Final Size: {final_size} MB")
                print(f"Size Reduction: {size_reduction}%")
                
                input_path.unlink()
                logging.info(f"Removed original file: {input_path.name}")
            else:
                logging.error(f"Error converting {input_path.name}")
                if temp_output_path.exists():
                    temp_output_path.unlink()
                
        except Exception as e:
            logging.error(f"Error processing {mkv_path}: {str(e)}")
            if 'temp_output_path' in locals() and temp_output_path.exists():
                temp_output_path.unlink()
            if 'progress' in locals():
                progress.close()

    def on_created(self, event):
        """Handle file creation events"""
        if event.is_directory:
            return
        if event.src_path.lower().endswith('.mkv'):
            logging.info(f"New MKV file detected: {event.src_path}")
            self.convert_mkv_to_mp4(event.src_path)

def main():
    parser = argparse.ArgumentParser(description='Convert MKV files to MP4 format recursively')
    parser.add_argument('path', help='Root path to watch for MKV files')
    parser.add_argument('--resolution', '-r', help='Target resolution (e.g., 720p, 1080p, or WxH)', default=None)
    parser.add_argument('--preset', '-p', 
                      choices=['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 
                              'medium', 'slow', 'slower', 'veryslow'],
                      default='medium',
                      help='Encoding preset (affects speed vs compression)')
    parser.add_argument('--crf', '-q',
                      type=int,
                      choices=range(0, 52),
                      default=23,
                      help='Constant Rate Factor (0-51, lower is better quality)')
    parser.add_argument('--profile',
                      choices=['baseline', 'main', 'high'],
                      default='high',
                      help='H.264 profile')
    parser.add_argument('--tune',
                      choices=['film', 'animation', 'grain', 'fastdecode', 'zerolatency'],
                      help='Content-specific tuning')
    parser.add_argument('--maxrate',
                      help='Maximum bitrate (e.g., 4M for 4Mbps)')
    parser.add_argument('--bufsize',
                      help='Buffer size (defaults to 2x maxrate)')
    
    args = parser.parse_args()
    
    watch_path = Path(args.path).resolve()
    
    if not watch_path.exists():
        print(f"Error: Directory {watch_path} does not exist")
        return
    
    if not watch_path.is_dir():
        print(f"Error: {watch_path} is not a directory")
        return
    
    event_handler = MKVHandler(
        str(watch_path),
        args.resolution,
        args.preset,
        args.crf,
        args.profile,
        args.tune,
        args.maxrate,
        args.bufsize
    )
    
    observer = Observer()
    observer.schedule(event_handler, str(watch_path), recursive=True)
    observer.start()
    
    print(f"\nWatching {watch_path} and all subdirectories for MKV files...")
    print("\nStreaming Optimization Settings:")
    if args.resolution:
        print(f"- Target resolution: {args.resolution}")
    print(f"- Preset: {args.preset}")
    print(f"- CRF: {args.crf}")
    print(f"- Profile: {args.profile}")
    if args.maxrate:
        print(f"- Max Bitrate: {args.maxrate}")
        print(f"- Buffer Size: {args.bufsize or f'(auto: {int(float(args.maxrate[:-1]) * 2)}M)'}")
    print("\nPress Ctrl+C to stop")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        logging.info("Stopping converter")
        print("\nConverter stopped")
    
    observer.join()

if __name__ == "__main__":
    main()