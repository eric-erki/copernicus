# This file is part of Copernicus
# http://www.copernicus-computing.org/
# 
# Copyright (C) 2011, Sander Pronk, Iman Pouya, Erik Lindahl, and others.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as published 
# by the Free Software Foundation
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.



import math


def sqrt(a):
    return { "c" : math.sqrt(a) }

def pow(a,b):
    return { "c" : math.pow(a,b) }

def exp(a):
    return { "b" : math.exp(a) }

def sin(a):
    return { "c" : math.sin(a) }

def cos(a):
    return { "c" : math.cos(a) }

def pi():
    return { "c" : math.pi }


