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
        self.progress_bar = tqdm(total=100, desc="Converting", unit="%")
        
    def update(self, time):
        progress = (time / self.duration) * 100
        self.progress_bar.n = progress
        self.progress_bar.refresh()
    
    def close(self):
        self.progress_bar.close()

class MKVHandler(FileSystemEventHandler):
    def __init__(self, root_dir):
        self.root_dir = Path(root_dir)
        self.setup_logging()
        self.scan_existing_files()
        
    def setup_logging(self):
        log_file = self.root_dir / 'mkv_converter.log'
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
    
    def get_video_duration(self, file_path):
        """Get video duration using ffprobe"""
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            str(file_path)
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            data = json.loads(result.stdout)
            return float(data['format']['duration'])
        except:
            return None

    def get_video_info(self, file_path):
        """Get video information for status display"""
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_streams',
            '-show_format',
            str(file_path)
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            data = json.loads(result.stdout)
            
            # Get video stream info
            video_stream = next((s for s in data['streams'] if s['codec_type'] == 'video'), None)
            
            if video_stream and 'format' in data:
                size_mb = round(float(data['format']['size']) / (1024*1024), 2)
                return {
                    'resolution': f"{video_stream.get('width', '?')}x{video_stream.get('height', '?')}",
                    'duration': float(data['format']['duration']),
                    'size': size_mb
                }
        except:
            pass
        return None

    def scan_existing_files(self):
        """Scan for existing MKV files on startup"""
        mkv_files = list(self.root_dir.rglob('*.mkv'))
        if mkv_files:
            logging.info(f"Found {len(mkv_files)} existing MKV files")
            print(f"\nFound {len(mkv_files)} MKV files to convert")
            for mkv_path in mkv_files:
                if 'converted' not in str(mkv_path):
                    self.convert_mkv_to_mp4(str(mkv_path))
        else:
            print("\nNo existing MKV files found. Watching for new files...")

    def on_created(self, event):
        if event.is_directory:
            return
        if event.src_path.lower().endswith('.mkv'):
            self.convert_mkv_to_mp4(event.src_path)
    
    def get_output_path(self, input_path):
        input_path = Path(input_path)
        relative_path = input_path.relative_to(self.root_dir)
        output_path = self.root_dir / relative_path.parent / f"{input_path.stem}.mp4"
        return output_path
    
    def verify_conversion(self, output_path):
        if not output_path.exists():
            return False
        if output_path.stat().st_size == 0:
            output_path.unlink()
            return False
        return True
    
    def convert_mkv_to_mp4(self, mkv_path):
        try:
            input_path = Path(mkv_path)
            output_path = self.get_output_path(input_path)
            temp_output_path = output_path.with_suffix('.temp.mp4')
            
            # Get video information
            video_info = self.get_video_info(input_path)
            if video_info:
                print(f"\nProcessing: {input_path.relative_to(self.root_dir)}")
                print(f"Resolution: {video_info['resolution']}")
                print(f"Size: {video_info['size']} MB")
                print(f"Duration: {time.strftime('%H:%M:%S', time.gmtime(video_info['duration']))}")
            
            # Create output directory if it doesn't exist
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            logging.info(f"Starting conversion of {input_path.name}")
            
            # Create progress tracking
            progress = FFmpegProgress(video_info['duration'] if video_info else 0)
            
            # Using ffmpeg with progress monitoring
            cmd = [
                'ffmpeg',
                '-i', str(input_path),
                '-c:v', 'copy',
                '-c:a', 'aac',
                '-strict', 'experimental',
                '-y',
                '-progress', 'pipe:1',
                str(temp_output_path)
            ]
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # Monitor conversion progress
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                
                # Extract time progress
                time_match = re.search(r'out_time_ms=(\d+)', line)
                if time_match:
                    current_time = int(time_match.group(1)) / 1000000  # Convert microseconds to seconds
                    progress.update(current_time)
            
            progress.close()
            
            if process.returncode == 0 and self.verify_conversion(temp_output_path):
                # Move temp file to final location
                shutil.move(str(temp_output_path), str(output_path))
                logging.info(f"Successfully converted {input_path.name}")
                print(f"✓ Completed: {output_path.relative_to(self.root_dir)}")
                
                # Remove original MKV file
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

def main():
    parser = argparse.ArgumentParser(description='Convert MKV files to MP4 format recursively')
    parser.add_argument('path', help='Root path to watch for MKV files')
    args = parser.parse_args()
    
    watch_path = Path(args.path).resolve()
    
    if not watch_path.exists():
        print(f"Error: Directory {watch_path} does not exist")
        return
    
    if not watch_path.is_dir():
        print(f"Error: {watch_path} is not a directory")
        return
    
    event_handler = MKVHandler(str(watch_path))
    observer = Observer()
    observer.schedule(event_handler, str(watch_path), recursive=True)
    observer.start()
    
    print(f"\nWatching {watch_path} and all subdirectories for MKV files...")
    print("Press Ctrl+C to stop")
    
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