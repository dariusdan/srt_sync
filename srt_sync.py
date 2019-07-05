#! python3
# srt_sync.py

'''
TO DO:

- Raise exceptions for invalid slice arguments
	- Raise exception if index parameter is out of range
	- Raise exception if start index >= end index
- Fix negative offset (related to optional arguments)
- Match the last line of the file(?)
- Merge / Split / Delete methods
- Check overlaps / negative duration / short display time / long lines
'''

# imports ======================================================================

from collections import namedtuple
import argparse
import logging
import os
import re
import sys


# logging definitions ==========================================================

logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')
#logging.disable(logging.DEBUG)


# constants ====================================================================

Constants = namedtuple('Constants', ['SRT_PATTERN', 'TIMESTAMP_PATTERN'])
constants = Constants(

	# SRT_PATTERN --------------------------------------------------------------
	r'''								# https://regex101.com/r/eSrmb9/6
	(\d+)[\r]?[\n]						# index
	(\d\d):(\d\d):(\d\d),(\d\d\d)		# starting hour, mins, secs, msecs
	[ ]-->[ ]							# timestamp division
	(\d\d):(\d\d):(\d\d),(\d\d\d)		# ending hour, mins, secs, msecs
	(									# optional positional coordinates
		[ ]{1,2}
		X1:(\d{3})[ ]					# X1 coordinate
		X2:(\d{3})[ ]					# X2 coordinate
		Y1:(\d{3})[ ]					# Y1 coordinate
		Y2:(\d{3})						# Y2 coordinate
	)?
	[\r]?[\n]
	(((.+)[\r]?[\n])+)					# content
	''', 

	# TIMESTAMP_PATTERN --------------------------------------------------------
	r'''								# https://regex101.com/r/pexG8G/2
	^([+-])?							# offset sign
	(
		(([0-5]?\d):)?					# hours
		(([0-5]?\d):)					# minutes
	)?
	([0-5]?\d)							# seconds
	([,](\d\d?\d?))?$					# msecs
	'''
)


# classes ======================================================================

class Movie():

	def __init__(self, srt_path):
		if not os.path.exists(srt_path):
			raise FileNotFoundError('SRT file could not be found.')
		if not (os.path.isfile(srt_path) and srt_path.lower().endswith('.srt')):
			raise TypeError('The file is not a valid SRT subtitle.')

		srt_file = open(srt_path, 'r')
		srt_content = srt_file.read()
		srt_file.close()

		srt_ro = re.compile(constants.SRT_PATTERN, re.VERBOSE)
		srt_match = srt_ro.findall(srt_content)
		if not srt_match:
			raise ValueError('No subtitles to load.')
		
		self.subtitles = []
		for sub in srt_match:
			i   = int(sub[0])
			h0  = int(sub[1])
			m0  = int(sub[2])
			s0  = int(sub[3])
			ms0 = int(sub[4])
			h1  = int(sub[5])
			m1  = int(sub[6])
			s1  = int(sub[7])
			ms1 = int(sub[8])
			if sub[9] == '':
				pos = None
			else:
				pos = ( 
					int(sub[10]), 
					int(sub[11]), 
					int(sub[12]), 
					int(sub[13])
				)
			content = sub[14].strip('\r\n').replace('\r', '').split('\n')
			self.subtitles.append(Subtitle(
				i, 
				((h0 * 3600) + (m0 * 60) + (s0)) * 1000 + ms0, 
				((h1 * 3600) + (m1 * 60) + (s1)) * 1000 + ms1, 
				pos, 
				content
			))


	def offset_subtitles(self, offset_timestamp, first_index=1, last_index=None):
		offset_msecs = timestamp_to_millisecs(offset_timestamp)
		for sub in self.subtitles[first_index-1:last_index]:
			time_start = sub.time_start + offset_msecs
			time_end   = sub.time_end   + offset_msecs
			if (time_start < 0) or (time_end < 0):
				raise ValueError('Subtitle timestamp can not be negative.')
			else:
				sub.time_start = time_start
				sub.time_end   = time_end


	def scale_subtitles(self, scale_factor, first_index=1, last_index=None):
		if type(scale_factor) != float:
			raise TypeError('Scale factor needs to be a float value.')
		for sub in self.subtitles[first_index-1:last_index]:
			time_start = int(sub.time_start * scale_factor)
			time_end =   int(sub.time_end   * scale_factor)
			if (time_start < 0) or (time_end < 0):
				raise ValueError('Subtitle timestamp can not be negative.')
			else:
				sub.time_start = time_start
				sub.time_end   = time_end


	def interpolate_subtitles(self, first_timestamp, last_timestamp, first_index=1, last_index=None):
		first_time_original = self.subtitles[first_index-1].time_start
		if last_index:
			last_time_original  = self.subtitles[last_index].time_start
		else:
			last_time_original  = self.subtitles[-1].time_start
		first_time_sync = timestamp_to_millisecs(first_timestamp)
		last_time_sync  = timestamp_to_millisecs(last_timestamp)
		
		if (first_time_sync < 0) or (last_time_sync < 0):
			raise ValueError('Subtitle timestamp can not be negative.')
		
		if first_time_sync >= last_time_sync:
			raise ValueError('The last timestamp has to be higher than the first timestamp.')
			
		for sub in self.subtitles[first_index-1:last_index]:
			sub.time_start = int(linear_interpolation(
				first_time_original, 
				last_time_original, 
				first_time_sync, 
				last_time_sync, 
				sub.time_start
			))

			sub.time_end = int(linear_interpolation(
				first_time_original, 
				last_time_original, 
				first_time_sync, 
				last_time_sync, 
				sub.time_end
			))


	def get_srt_syntax(self):
		srt_string = ''
		for sub in self.subtitles:
			srt_string += sub.get_srt_syntax()
		
		assert len(re.compile(constants.SRT_PATTERN, re.VERBOSE).findall(srt_string)) == len(self.subtitles), 'Invalid srt syntax output.'

		return srt_string


class Subtitle():

	def __init__(self, index, time_start, time_end, position, content):
		self.index      = index
		self.time_start = time_start
		self.time_end   = time_end
		self.position   = position
		self.content    = content


	def get_timestamp_str(self, timestamp):
			if timestamp   == 'start':
				ms = self.time_start
			elif timestamp == 'end':
				ms = self.time_end
			else:
				raise ValueError('Invalid parameter: \'{}\''.format(timestamp))
			return millisecs_to_timestamp(ms)


	def get_position_str(self):
		if self.position:
			return ' X1:{:0>3d}'.format(self.position[0]) + \
				   ' X2:{:0>3d}'.format(self.position[1]) + \
				   ' Y1:{:0>3d}'.format(self.position[2]) + \
				   ' Y2:{:0>3d}'.format(self.position[3])
		else:
			return ''


	def get_srt_syntax(self):
		srt_string = '{}\n'.format(self.index) + \
					 '{} --> {}'.format(self.get_timestamp_str('start'), self.get_timestamp_str('end')) + \
					 '{}\n'.format(self.get_position_str()) + \
					 '{}\n\n'.format('\n'.join(self.content))
		
		return srt_string


# functions ====================================================================

def timestamp_to_millisecs(timestamp):
	timestamp_ro = re.compile(constants.TIMESTAMP_PATTERN, re.VERBOSE)

	match = timestamp_ro.search(timestamp)
	
	if match == None:
		raise ValueError('Incorrect offset syntax: [+/-]HH:MM:SS,MSC')

	if match.group(1) == '-':
		sign = -1
	else:
		sign = 1
	
	if match.group(4):
		h =  int(match.group(4))
	else:
		h = 0

	if match.group(6):
		m = int(match.group(6))
	else:
		m = 0

	if match.group(7):
		s = int(match.group(7))
	else:
		s = 0
	
	if match.group(9):
		ms = int(match.group(9)) * (10 ** (3 - len(match.group(9))))
	else:
		ms = 0

	return (((h * 3600) + (m * 60) + (s)) * 1000 + ms) * sign


def millisecs_to_timestamp(ms):
	if type(ms) != int:
		raise TypeError('\'ms\' parameter must be a positive int.')
	if ms < 0:
		raise ValueError('\'ms\' parameter must be a positive int.')
		
	h  = ms // 3600000 % 24
	m  = ms // 60000   % 60
	s  = ms // 1000    % 60
	ms = ms % 1000
	
	return '{:0>2d}:{:0>2d}:{:0>2d},{:0>3d}'.format(h, m, s, ms)


def linear_interpolation(xMin, xMax, yMin, yMax, x):
	return (((x - xMin) * (yMax - yMin)) / (xMax - xMin)) + yMin


# main =========================================================================

def main():

	# Argument parser
	parser = argparse.ArgumentParser(prog='srt_sync', description='srt_sync: Python module for syncing .srt format subtitles.')
	parser.add_argument('filepath', type=str, help='Path to the \'.srt\' subtitle file.')
	parser.add_argument('-first_index', type=int, default=1,    help='Index of the first subtitle to synchronize.')
	parser.add_argument('-last_index',  type=int, default=None, help='Index of the last subtitle to synchronize.')
	
	subparsers = parser.add_subparsers(help='Available Commands.', dest='command', required=True)

	parser_offset = subparsers.add_parser('offset')
	parser_offset.add_argument('offset_timestamp', type=str, help='Offset timestamp for all subtitles.')
	
	parser_offset = subparsers.add_parser('scale')
	parser_offset.add_argument('scale_factor', type=float, help='Scale factor for all subtitles.')

	parser_interpolate = subparsers.add_parser('interpolate')
	parser_interpolate.add_argument('first_timestamp', type=str, help='New timestamp for the first subtitle.')
	parser_interpolate.add_argument('last_timestamp',  type=str, help='New timestamp for the last subtitle.')

	args = parser.parse_args()
	logging.debug(args)
	
	try:
		# Load movie
		movie = Movie(args.filepath)

		# Offset movie
		if args.command == 'offset':
			movie.offset_subtitles(args.offset_timestamp, args.first_index, args.last_index)

		# Scale movie
		elif args.command == 'scale':
			movie.scale_subtitles(args.scale_factor, args.first_index, args.last_index)

		# Interpolate movie
		elif args.command == 'interpolate':
			movie.interpolate_subtitles(args.first_timestamp, args.last_timestamp, args.first_index, args.last_index)

		# Get SRT syntax for the synced subtitles
		movie_srt_syntax = movie.get_srt_syntax()
	
	except Exception as err:
		print('Error: ' + str(err))
		sys.exit()

	# Save synced file
	synced_file = open(args.filepath, 'w')
	synced_file.write(movie_srt_syntax)
	synced_file.close()
	

if __name__ == '__main__':
	main()
