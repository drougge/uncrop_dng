#!/usr/bin/env python
# -*- coding: iso-8859-1 -*-

from __future__ import print_function

# Taken from wellpapp, added update function
class TIFF:
	"""Pretty minimal TIFF container parser"""
	
	types = { 1: (1, "B"),  # BYTE
	          2: (1, None), # ASCII
	          3: (2, "H"),  # SHORT
	          4: (4, "I"),  # LONG
	          5: (8, "II"), # RATIONAL
	          6: (1, "b"),  # SBYTE
	          7: (1, None), # UNDEFINE
	          8: (2, "h"),  # SSHORT
	          9: (4, "i"),  # SLONG
	         10: (8, "ii"), # SRATIONAL
	         11: (4, "f"),  # FLOAT
	         12: (8, "d"),  # DOUBLE
	         13: (4, "I"),  # IFD
	        }
	
	def __init__(self, fh, allow_variants=True, short_header=False):
		from struct import unpack, pack
		self._fh = fh
		d = fh.read(4)
		if short_header:
			if d[:2] not in (b"II", b"MM"): raise Exception("Not TIFF")
			self.variant = None
		else:
			good = [b"II*\0", b"MM\0*"]
			if allow_variants:
				# Olympus ORF, Panasonic RW2
				good += [b"IIRO", b"IIU\0"]
			if d not in good: raise Exception("Not TIFF")
			self.variant = d[2:4].strip(b"\0")
		endian = {b"M": ">", b"I": "<"}[d[0]]
		self._up = lambda fmt, *a: unpack(endian + fmt, *a)
		self._up1 = lambda *a: self._up(*a)[0]
		self._pack = lambda fmt, a: pack(endian + fmt, *a)
		if short_header:
			next_ifd = short_header
		else:
			next_ifd = self._up1("I", fh.read(4))
		# Be conservative with possibly mis-detected ORF
		if self.variant == "RO":
			assert next_ifd == 8
		self.reinit_from(next_ifd, short_header)
	
	def reinit_from(self, next_ifd, short_header=False):
		self.ifd = []
		self.subifd = []
		seen_ifd = set()
		while next_ifd:
			self.ifd.append(self._ifdread(next_ifd))
			if short_header: return
			next_ifd = self._up1("I", self._fh.read(4))
			if next_ifd in seen_ifd:
				from sys import stderr
				print("WARNING: Looping IFDs", file=stderr)
				break
			seen_ifd.add(next_ifd)
			assert len(self.ifd) < 32 # way too many
		subifd = self.ifdget(self.ifd[0], 0x14a) or []
		assert len(subifd) < 32 # way too many
		for next_ifd in subifd:
			self.subifd.append(self._ifdread(next_ifd))
	
	def update(self, ifd, tag, data):
		type, vc, off = ifd[tag]
		assert vc == len(data)
		assert isinstance(off, int)
		_, fmt = self.types[type]
		data = self._pack(fmt * vc, data)
		self._fh.seek(off)
		self._fh.write(data)
	
	def ifdget(self, ifd, tag):
		if tag in ifd:
			type, vc, off = ifd[tag]
			if type not in self.types: return None
			if isinstance(off, int): # offset
				self._fh.seek(off)
				tl, fmt = self.types[type]
				off = self._fh.read(tl * vc)
				if fmt: off = self._up(fmt * vc, off)
			if type == 2:
				off = off.rstrip("\0")
			return off
	
	def _ifdread(self, next_ifd):
		ifd = {}
		self._fh.seek(next_ifd)
		count = self._up1("H", self._fh.read(2))
		for i in range(count):
			d = self._fh.read(12)
			tag, type, vc = self._up("HHI", d[:8])
			if type in self.types and self.types[type][0] * vc <= 4:
				tl, fmt = self.types[type]
				d = d[8:8 + (tl * vc)]
				if fmt:
					off = self._up(fmt * vc, d)
				else:
					off = d # ASCII
			else:
				off = self._up1("I", d[8:])
			ifd[tag] = (type, vc, off)
		return ifd

def uncrop(tiff):
	for ifd in tiff.subifd:
		if 0xc61f in ifd:
			lx, ly, hy, hx = tiff.ifdget(ifd, 0xc68d)
			for tag, values in ((0xc61f, (lx, ly)), (0xc620, (hx, hy))):
				tiff.update(ifd, tag, values)

if __name__ == "__main__":
	from sys import argv
	for fn in argv[1:]:
		with open(fn, "rb+") as fh:
			tiff = TIFF(fh)
			uncrop(tiff)
