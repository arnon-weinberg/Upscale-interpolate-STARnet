#!/usr/bin/env python
# See https://www.research-lab.ca/2022/05/using-ffmpeg-to-replace-video-frames/
#
# >showinfo2concat.py --help

import argparse
import sys
import re

parser = argparse.ArgumentParser ( description = 'Convert showinfo log to concat file with durations' )

parser.add_argument ( 'input', nargs='?', help='showinfo log file or -' )
parser.add_argument ( '--prefix', default='', help='image file name prefix' )
parser.add_argument ( '--start0', dest='start0', action='store_true',
                      help='start at PTS=0 instead of first frame' )

opt = parser.parse_args()

# Read showinfo log file:
F = sys.stdin
if opt.input and opt.input != '-':
  F = open(opt.input)

tb = ''
frames = []
# showinfo log entries + optional loglevel and terminal color escape codes:
showinfo = r'(?:\033\[[0-9;]+m)*'
showinfo = r'^'+showinfo+r'\[Parsed_showinfo_.+\]'+showinfo
for l in F.readlines():
  g = re.search(showinfo+r' config in time_base: ([\d\/]+), ',l)
  if g: tb = g.group(1)
  g = re.search(showinfo+r' n:\s*(?P<n>\d+) pts:\s*(?P<pts>\d+)'
                        +r' pts_time:\s*(?P<pts_time>[\d\.]+) ',l)
  if g: frames.append(g.groupdict())

# Output concat file:
print('ffconcat version 1.0')
f = frames.pop(0)
f['n'] = int(f['n'])
pts = int(f['pts'])
print(f"# TB: {tb}")
if opt.start0:
  print(f"file './{opt.prefix}{f['n']+1:06}.png'")
  print(f"duration {pts/25:.6g} # {pts}/25")
print(f"file './{opt.prefix}{f['n']+1:06}.png'"
     +f" # n: {f['n']}; PTS: {f['pts']}; Timestamp (s): {f['pts_time']}")
for f in frames:
  f['n'] = int(f['n'])
  f['pts'] = int(f['pts'])
  print(f"duration {(f['pts']-pts)/25:.6g} # {(f['pts']-pts)}/25")
  print(f"file './{opt.prefix}{f['n']+1:06}.png'"
       +f" # n: {f['n']}; PTS: {f['pts']}; Timestamp (s): {f['pts_time']}")
  pts = f['pts']

F.close()
