"""Export the actual Playwright capture as an MP4 loop and a downloadable GIF."""
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
source = Path((root / 'data/recordings/latest-path.txt').read_text().strip())
media = root / 'apps/web/public/media'
subprocess.run(['ffmpeg', '-y', '-ss', '0.65', '-i', str(source), '-an', '-c:v', 'libx264', '-preset', 'fast', '-crf', '23', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(media / 'tiza-demo.mp4')], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
subprocess.run(['ffmpeg', '-y', '-ss', '0.65', '-i', str(source), '-filter_complex', 'fps=10,scale=800:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle', '-loop', '0', str(media / 'tiza-demo.gif')], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
for name in ['tiza-demo.mp4', 'tiza-demo.gif']:
    print(name, (media/name).stat().st_size)
