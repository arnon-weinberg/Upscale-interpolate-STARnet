# Module for working with FFmpeg command-line.

import sys, os
import shlex, shutil, subprocess
import re, glob

# Convert HH:MM:SS.ms timestamp format to SS.ms time in seconds format:
def ts2s(ts):
  ts = [float(x) for x in ts.split(':')]
  while(len(ts)>1):
    ts[1] += ts[0]*60
    ts.pop(0)
  return ts[0]

# Extract frames from video, and optionally generate concat file of frames:
# See: http://www.research-lab.ca/2022/05/using-ffmpeg-to-replace-video-frames/
def ffmpeg_extract_frames(opt, input_dir):
  if not opt.debug: print(f"Extracting frames from '{opt.input}' ...", end='')
  else: print(f"Extracting frames from '{opt.input}' using FFmpeg")

  command = 'ffmpeg'
  if   opt.debug == 0: command += ' -loglevel fatal'
  elif opt.debug == 1: command += ' -loglevel warning'
  if opt.resume: command += ' -n' # This doesn't work
  command += ' -i '+shlex.quote(opt.input)

  select = '' # scene select
  prefix = '' # output filename prefix
  if opt.scene:
    if opt.scene['st'] is not None:
      select = f"gte(t,{ts2s(opt.scene['st'])})"
    else:
      select = f"gte(n,{opt.scene['sf']})"

    if   opt.scene['et'] is not None:
      select += f"*lt(t,{ts2s(opt.scene['et'])})"
    elif opt.scene['ef'] is not None:
      select += f"*lt(n,{opt.scene['ef']})'"
    elif opt.scene['tf'] is not None:
      select += f"*lt(selected_n,{opt.scene['tf']})"
    elif opt.scene['tt'] is not None:
      select += f"*lt(t,{ts2s(opt.scene['st']) + ts2s(opt.scene['tt'])})"
    if select: command += f" -vf \"select='{select}'"         \
                        + (',showinfo' if opt.output else '') \
                        + '" -vsync passthrough' # Change to -fps_mode

    if opt.scene['st'] is not None:
      prefix = f"{opt.scene['st']}+"
    else:
      command += f" -start_number {opt.scene['sf']}"

  command += ' '+shlex.quote(os.path.join(input_dir,prefix+'%06d.png'))+' 2>&1'
  if opt.debug > 1: print('command =', command)
  if not opt.resume and os.path.exists(input_dir):
    for f in glob.glob(os.path.join(input_dir,'*.png')): os.remove(f)
  if not os.path.exists(input_dir): os.makedirs(input_dir)

  # If output is a file, then generate concat file of frames:
  if opt.output and                                                    \
     ( not opt.resume or # Don't overwrite existing concat file
       not os.path.exists(os.path.join(input_dir,'concat.txt')) ):
    command = re.sub(r'^ffmpeg( -loglevel \w+)? ',
                     r'ffmpeg -loglevel +level ', command)
    # Preserve command output colour:
    command = f"script -qec {shlex.quote(command)} /dev/null"          \
            +" | sed -E 'N;s/(\\r?\\n|\\r(.))(\\x1B\[0m)?/\\3\\r\\n\\2/g;P;D;'"
    # Convert showinfo to concat.txt file using showinfo2concat.py:
    command += f""" | tee >({shlex.quote(os.path.join(os.path.dirname(
                               sys.argv[0]),'showinfo2concat.py'))}""" \
             + f" --prefix={shlex.quote(prefix)} -"                    \
             + f" >{shlex.quote(os.path.join(input_dir,'concat.txt'))})"
    # Handle loglevel manually:
    color = '(\033\[[0-9;]+m)*'
    command += f" | egrep -v '^{color}\[Parsed_showinfo_'"
    if opt.debug < 1: command += f" | egrep -v '^{color}\[(error|warning)\] '"
    if opt.debug < 2: command += f" | egrep -v '^{color}\[(info)\] '"
    command += f" | sed -E 's/^({color})\[\w+\] /\\1/'"
  os.system ( command )
  if not opt.debug: print(' done.')

# Replace frames in video
# See: http://www.research-lab.ca/2022/05/using-ffmpeg-to-replace-video-frames/
def ffmpeg_replace_frames(opt, input_dir, output_dir):
  if not opt.debug: print(f"Replacing frames in '{opt.input}' ...", end='')
  else: print(f"Replacing frames in '{opt.input}' using FFmpeg")

  command = 'ffmpeg'
  command += ' -i '+shlex.quote(opt.input)

  # Overlay frames using concat file:
  concat = os.path.join(output_dir,'concat.txt')
  if not os.path.exists(concat): # Don't overwrite existing concat file
    shutil.copy2(os.path.join(input_dir,'concat.txt'),concat)
  command += ' -f concat -safe 0 -i '+shlex.quote(concat)
  with open(concat) as F:
    F.readline() # Discard first line
    TB = re.search(r'^# TB: ([\d./]+)',F.readline()).group(1)
    TB = re.sub(r'^([^/]+)$',r'\1/1',TB) # TB = Timebase
    TS = re.sub(r'^([^/]+)/([^/]+)$',r'\2/\1',TB)
    TS = re.sub(r'/1$',r'',TS)           # TS = Timescale (inverse of TB)
    PTS = re.search(r'^file .+; PTS: (\d+);',F.readline()).group(1)
    command += f" -filter_complex \"[1]settb={TB},"    \
             +  f"setpts={PTS}+PTS*25*{TB}[o];[0:v:0]"
    if opt.zoom: command += f"scale=iw*{opt.zoom}:-1:flags=bicubic[v];[v]"
    command +=  f"[o]overlay=eof_action=pass\" -vsync passthrough -r {TS}"

  # Preserve unmodified streams and metadata:
  command += ' -map 0'
  dryrun = subprocess.run (
        command + ' -t 1 -y '
      + shlex.quote(os.path.join(output_dir,
                                 'dryrun.'+os.path.basename(opt.output)))
      + " | sed -E 'N;s/(\\r?\\n|\\r(.))(\\x1B\[0m)?/\\3\\r\\n\\2/g;P;D;'",
      shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    ).stdout.decode()
  dryrun = re.sub(r'^.+\nStream mapping:\n((?:\s+[^\n]+\n)+)\S.+$',r'\1',
                  dryrun, flags=re.DOTALL)
  command += ' -c copy -c:v:0 '                      \
           + re.sub(r'^.+ -> Stream #0:0 \(([^)]+)\)\n.+$',r'\1',
                    dryrun, flags=re.DOTALL)
  for ( n ) in re.findall(r'^\s+Stream #0:(\d+) ', dryrun, re.MULTILINE):
    command += f" -map_metadata:s:{n} 0:s:{n}"

  if   opt.debug == 0: command += ' -loglevel fatal -hide_banner'
  elif opt.debug == 1: command += ' -loglevel warning -hide_banner'
  if opt.resume: command += ' -n'
  command += ' '+shlex.quote(opt.output)

  if opt.debug > 1: print('command =', command)
  os.system ( command )

  if not opt.debug: print(' done.')
