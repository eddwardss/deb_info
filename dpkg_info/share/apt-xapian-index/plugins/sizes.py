try:
    import apt
    import apt_pkg
    HAS_APT=True
except ImportError:
    HAS_APT=False
import os
import os.path

import xapian


class Sizes:
    def __init__(self):
        self.val_inst_size = -1
        self.val_pkg_size = -1


    def info(self, **kw):
        res = dict(
                timestamp=0,
                values=[
                    dict(name = "installedsize", desc = "installed size"),
                    dict(name = "packagesize", desc = "package size")
                ],
        )
        if kw.get("system", True):
            if not HAS_APT: return res
            file = apt_pkg.config.find_file("Dir::Cache::pkgcache")
            if not os.path.exists(file): return res
            ts = os.path.getmtime(file)
        else:
            file = "(stdin)"
            ts = 0
        res["sources"] = [dict(path=file, desc="APT index")]
        res["timestamp"] = ts
        return res

    def doc(self):
        """
        Return documentation information for this data source.

        The documentation information is a dictionary with these keys:
          name: the name for this data source
          shortDesc: a short description
          fullDoc: the full description as a chapter in ReST format
        """
        return dict(
            name = "Sizes",
            shortDesc = "package sizes indexed as values",
            fullDoc = """
            The Sizes data source indexes the package size and the installed
            size as the ``packagesize`` and ``installedsize`` Xapian values.
            """
        )

    def init(self, info, progress):
        self.val_inst_size = -1
        self.val_pkg_size = -1
        values = info.get("values", [])
        for i, v in enumerate(values):
            name = v.get("name")
            if name == "installedsize":
                self.val_inst_size = i
            elif name == "packagesize":
                self.val_pkg_size = i


    def index(self, document, pkg):
#        if self.val_inst_size >= 0:
#            document.add_value(self.val_inst_size, xapian.sortable_serialise(pkg.installed_size))
#        if self.val_pkg_size >= 0:
#            document.add_value(self.val_pkg_size, xapian.sortable_serialise(pkg.package_size))
        if self.val_inst_size >= 0:
            # Берём размер установленного пакета, если он есть
            inst_size = pkg.installed.installed_size if pkg.installed else 0
            document.add_value(self.val_inst_size, xapian.sortable_serialise(inst_size))
        if self.val_pkg_size >= 0:
            # Берём размер пакета для загрузки (кандидата)
            pkg_size = pkg.candidate.size if pkg.candidate else 0
            document.add_value(self.val_pkg_size, xapian.sortable_serialise(pkg_size))


    def indexDeb822(self, document, pkg):
        """
        Update the document with the information from this data source.

        This is alternative to index, and it is used when indexing with package
        data taken from a custom Packages file.

        document  is the document to update
        pkg       is the Deb822 object for this package
        """
        try:
            instSize = int(pkg["Installed-Size"])
            pkgSize = int(pkg["Size"])
        except:
            return

        if self.val_inst_size != -1:
            document.add_value(self.val_inst_size, xapian.sortable_serialise(instSize));
        if self.val_pkg_size != -1:
            document.add_value(self.val_pkg_size, xapian.sortable_serialise(pkgSize));

def init():
    """
    Create and return the plugin object.
    """
    return Sizes()
