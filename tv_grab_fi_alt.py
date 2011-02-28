#!/usr/bin/python
"""
tv_grab_fi_alt.py - Grab TV listings for Finland from www.tvnyt.fi
Copyright (C) 2010  Pekka Korpinen <pekka.korpinen@iki.fi>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

VERSION='20110228'

from optparse import OptionParser
from xml.sax import saxutils
import json
import urllib
import datetime
import codecs
import re
import sys
import os

class xmltv:
	def __init__(self, src):
		self.src = src
		self.channels = {}
		self.channel_data = []
		self.configuration = []

	def read_configuration(self, filename):
		try:
			for line in file(filename).readlines():
				m = re.match(r'^channel (\d+) (.*)$', line.strip())
				if m:
					self.channels[int(m.group(1))] = m.group(2)
		except:
			sys.stderr.write('Error while reading configuration file')
			sys.exit(-1)
		sys.stderr.write('Found %d channels active\n' % len(self.channels))

	def write_configuration(self, filename, query=True):
		options = ['yes','no','all','none']
		f = file(filename, 'w')
		for nr,name in self.channels.items():
			if query:
				res = None
				while res not in options:
					res = raw_input('add channel %s? [%s (default=yes)] ' % (name, ','.join(options)))
					if res=='':
						res = 'yes'
					elif res=='all':
						res = 'yes'
						query = False
					elif res=='none':
						res = 'no'
						query = False

			if res=='yes': f.write('channel %d %s\n' % (nr, name))
			else:          f.write('#channel %d %s\n' % (nr, name))
		f.close()

	def add(self, str):
		self.xml += str + "\n"

	def add_header(self):
		self.add('<?xml version="1.0" encoding="UTF-8"?>')
		self.add('<!DOCTYPE tv SYSTEM "xmltv.dtd">')
		self.add('<tv source-info-url="%s" source-data-url="%s" generator-info-name="XMLTV" generator-info-url="http://xmltv.org/">' % (self.src, self.src))

	def add_channel(self, id, name):
		self.add('  <channel id="%s">' % id)
		self.add('    <display-name>%s</display-name>' % name)
		self.add('  </channel>')

	def add_program(self, toffset, start, stop, channel, title, desc):
		# start="20101207035500 +0000" stop="20101207042500 +0000
		self.add('  <programme start="%s +%s" stop="%s +%s" channel="%s">' % (start, toffset, stop, toffset, channel))
		self.add('    <title lang="fi">%s</title>' % saxutils.escape(title))
		if not desc=='':
			self.add('    <desc lang="fi">%s</desc>' % saxutils.escape(desc))
		self.add('  </programme>')

	def add_footer(self):
		self.add('</tv>')

	def write_xml(self, filename):
		self.xml = ''
		self.add_header()
		for nr,name in self.channels.items():
			self.add_channel(self.channel_id(nr), name)
		for d in self.channel_data:
			self.add_program(d[0], d[1], d[2], d[3], d[4], d[5])
		self.add_footer()

		if filename:
			sys.stderr.write('Writing to %s...\n' % filename)
			f = codecs.open(filename, encoding='utf-8', mode='w')
			f.write(self.xml)
			f.close()
		else:
			print self.xml

class xmltv_tvnyt_fi(xmltv):
	TOFFSET = '0200'
	def __init__(self):
		xmltv.__init__(self, 'http://www.tvnyt.fi/')
		self.errors_detected = False

	def channel_id(self, nr):
		return '%s.tvnyt.fi' % nr

	def download_channel_list(self):
		sys.stderr.write('Downloading channel listing...\n')
		url = "http://www.tvnyt.fi/ohjelmaopas/wp_channels.js?timestamp=0"
		f = urllib.urlopen(url)
		for line in f.readlines():
			# strChannels += '...'
			if not 'strChannels +=' in line:
				continue
			for c in re.findall(r'\[.*?\]', line):
				# ["1","TV1","tv1.gif"]
				m = re.match(r'\["(\d+)","(.*)",".*"\]', c)
				if not m:
					continue
				self.channels[int(m.group(1))] = m.group(2)
		sys.stderr.write('Found %d channels\n' % len(self.channels))

	def download_channel_data(self, nr, date):
		d = date.strftime('%Y%m%d')
		url = "http://www.tvnyt.fi/ohjelmaopas/getChannelPrograms.aspx?channel=%d&start=%s0000&timestamp=0" % (nr, d)
		f = urllib.urlopen(url)
		s = f.read()
		# fix lazy json formatting
		# - keys are not properly quoted
		s = s.replace('{1:', '{"1":')
		s = s.replace('{id:"', '{"id":"')
		s = s.replace('", desc:"', '", "desc":"')
		s = s.replace('", title:"', '", "title":"')
		s = s.replace('", category:"', '", "category":"')
		s = s.replace('", start:"', '", "start":"')
		s = s.replace('", stop:"', '", "stop":"')
		# - inproper escape codes (some program descriptions contained \o)
		s = s.replace('\\', '\\\\')
		# - unallowed control characters
		s = s.translate(None, ''.join([chr(x) for x in range(0x20)]))
		
		# decode json
		try:
			js = json.loads(s)
		except ValueError as e:
			self.errors_detected = True
			dumpfile = 'tv_grab_fi_alt.debug'
			sys.stderr.write('Error while parsing JSON data. Dump appended to %s.\n' % dumpfile)
			dump = file(dumpfile, 'a')
			dump.write("%s\n%s\n%s\n" % (url, e, s))
			dump.close()
			return

		# "parse"
		chid = self.channel_id(nr)
		r = js['1']
		for p in r:
			desc = p['desc']
			# remove empty descriptions
			if desc==u'&#x20;': desc = ''
			self.channel_data.append([self.TOFFSET, p['start'], p['stop'], chid, p['title'], desc])

	def download_all_data(self, days, offset=0):
		for nr in self.channels.keys():
			date = datetime.date.today() + datetime.timedelta(offset)
			for i in range(days):
				sys.stderr.write('Processing channel %d on %s\n' % (nr, date))
				self.download_channel_data(nr, date)
				date += datetime.timedelta(1)

if __name__=='__main__':
	parser = OptionParser(version='%prog '+VERSION)
	parser.add_option("--config-file", dest="config", type="string",
					  default=os.path.expanduser("~/.xmltv/tv_grab_fi.conf"),
					  help="Set the name of the configuration file")
	parser.add_option("--configure", dest="configure", action="store_true", default=False,
					  help="create configuration file")
	parser.add_option("--list-channels", dest="listchannels", action="store_true", default=False,
					  help="List channels")
	parser.add_option("--days", dest="days", type="int", default=14,
					  help="grab N days")
	parser.add_option("--offset", dest="offset", type="int", default=0,
					  help="skip first N days")
	parser.add_option("--output", dest="output", type="string",
					  help="write to OUTPUT (defaultrather than standard output")
	(options, args) = parser.parse_args()

	x = xmltv_tvnyt_fi()
	sys.stderr.write("Using config filename " + options.config + "\n")

	if options.configure:
		x.download_channel_list()
		x.write_configuration(options.config)
	elif options.listchannels:
		x.download_channel_list()
		x.write_xml(options.output)
	elif options.days>0:
		x.read_configuration(options.config)
		x.download_all_data(options.days, options.offset)
		x.write_xml(options.output)

	if x.errors_detected:
		sys.stderr.write("One or more errors occured while parsing the data.\n")
		sys.exit(1)
		
	sys.exit(0)
