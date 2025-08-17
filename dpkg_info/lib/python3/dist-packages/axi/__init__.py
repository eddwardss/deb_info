#
# axi - apt-xapian-index python modules
#
# Copyright (C) 2007--2010  Enrico Zini <enrico@debian.org>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#

import os
import os.path
import re
import sys

# Setup configuration
PLUGINDIR = os.environ.get("AXI_PLUGIN_DIR", "/usr/share/apt-xapian-index/plugins")
XAPIANDBPATH = os.environ.get("AXI_DB_PATH", "/var/lib/apt-xapian-index")
XAPIANDBSTAMP = os.path.join(XAPIANDBPATH, "update-timestamp")
XAPIANDBLOCK = os.path.join(XAPIANDBPATH, "update-lock")
XAPIANDBUPDATESOCK = os.path.join(XAPIANDBPATH, "update-socket")
XAPIANDBVALUES = os.path.join(XAPIANDBPATH, "values")
XAPIANDBPREFIXES = os.path.join(XAPIANDBPATH, "prefixes")
XAPIANDBDOC = os.path.join(XAPIANDBPATH, "README")
XAPIANINDEX = os.path.join(XAPIANDBPATH, "index")
XAPIANCACHEPATH = os.environ.get("AXI_CACHE_PATH", "/var/cache/apt-xapian-index")

# Default value database in case one cannot be read
DEFAULT_VALUES = dict(version=0, installedsize=1, packagesize=2)
DEFAULT_VALUE_DESCS = dict(
        version="package version",
        installedsize="installed size",
        packagesize="package size"
)

def readValueDB(
    pathname: str = XAPIANDBVALUES,
    quiet: bool = False
) -> tuple[dict[str, int], dict[str, str]]:
    """
    Read the "/etc/services"-style database of value indices
    """
    try:
        re_empty = re.compile(r"^\s*(?:#.*)?$")
        re_value = re.compile(r"^(\S+)\s+(\d+)(?:\s*#\s*(.+))?$")
        values: dict[str, int] = {}
        descs: dict[str, str] = {}
        for idx, line in enumerate(open(pathname)):
            # Skip empty lines and comments
            if re_empty.match(line): continue
            # Parse teh rest
            mo = re_value.match(line)
            if not mo:
                if not quiet:
                    print("%s:%d: line is not `name value [# description]': ignored" % (pathname, idx+1), file=sys.stderr)
                continue
            # Parse the number
            name = mo.group(1)
            number = int(mo.group(2))
            desc = mo.group(3) or ""

            values[name] = number
            descs[name] = desc
        if not values:
            raise BrokenIndexError
    except (OSError, IOError, BrokenIndexError) as e:
        # If we can't read the database, fallback to defaults
        if not quiet:
            print("%s: %s. Falling back on a default value database" % (pathname, e), file=sys.stderr)
        values = DEFAULT_VALUES
        descs = DEFAULT_VALUE_DESCS
    return values, descs


class BrokenIndexError(Exception):
    pass
