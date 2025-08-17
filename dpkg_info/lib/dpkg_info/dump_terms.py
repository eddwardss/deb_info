import xapian
import sys
import struct
import datetime
import subprocess
import fnmatch
import argparse

def decode_time(raw):
    if len(raw) == 4:
        timestamp = struct.unpack(">I", raw)[0]
        try:
            return f"{timestamp} (время: {datetime.datetime.fromtimestamp(timestamp, datetime.UTC)})"
        except Exception:
            return str(timestamp)
    return str(int.from_bytes(raw, byteorder="big"))

def decode_version(raw):
    try:
        version_str = raw.decode('utf-8')
        if all(32 <= ord(c) <= 126 for c in version_str):
            return version_str
        else:
            return raw.hex()
    except Exception:
        return raw.hex()

def get_dpkg_version(pkg_name):
    try:
        output = subprocess.check_output(
            ["dpkg-query", "-W", "-f=${Version}", pkg_name],
            stderr=subprocess.DEVNULL
        )
        return output.decode().strip()
    except subprocess.CalledProcessError:
        return None

def get_pkg_name(doc):
    for term in doc.termlist():
        term_str = term.term.decode("utf-8") if isinstance(term.term, bytes) else term.term
        if term_str.startswith("XP"):
            return term_str[2:]
    return None

def find_docid_by_name(db, pkg_name):
    doccount = db.get_doccount()
    for docid in range(1, doccount + 1):
        try:
            doc = db.get_document(docid)
        except xapian.InvalidArgumentError:
            continue
        name = get_pkg_name(doc)
        if name == pkg_name:
            return docid
    return None

def dump_doc_info(db, docid):
    doc = db.get_document(docid)

    pkg_name = None
    repo_version = None
    for term in doc.termlist():
        term_str = term.term.decode() if isinstance(term.term, bytes) else term.term
        if term_str.startswith("XP"):
            pkg_name = term_str[2:]
        elif term_str.startswith("XV"):
            repo_version = term_str[2:]

    dpkg_version = get_dpkg_version(pkg_name)

    installed_raw = doc.get_value(0)
    installed_version = decode_version(installed_raw) if installed_raw else None

    installed_flag = False
    installed_version_real = None

    val1 = doc.get_value(1)
    if val1 and (val1[0] & 0x80):
        installed_flag = True
        val_version = doc.get_value(3)
        if val_version:
            installed_version_real = decode_version(val_version)

    depends = []
    build_depends = []
    recommends = []
    suggests = []
    enhances = []
    pre_depends = []
    breaks = []
    conflicts = []

    for term in doc.termlist():
        t = term.term.decode() if isinstance(term.term, bytes) else term.term
        if t.startswith("XD"):
            depends.append(t[2:])
        elif t.startswith("XRR"):
            recommends.append(t[3:])
        elif t.startswith("XR"):
            if len(t) > 3:
                dep_type = t[2]
                pkg = t[3:]
                if dep_type == 'D':
                    depends.append(pkg)
                elif dep_type == 'B':
                    build_depends.append(pkg)
                elif dep_type == 'R':
                    recommends.append(pkg)
                elif dep_type == 'S':
                    suggests.append(pkg)
                elif dep_type == 'E':
                    enhances.append(pkg)
                elif dep_type == 'P':
                    pre_depends.append(pkg)
                elif dep_type == 'K':
                    breaks.append(pkg)
                elif dep_type == 'C':
                    conflicts.append(pkg)

    print(f"Документ ID: {docid}")
    print(f"Пакет: {pkg_name or 'неизвестен'}")
    print(f"Версия в репозитории: {repo_version or 'не указана'}")
    print(f"Статус установки (Xapian): {'Установлен' if installed_flag else 'Не установлен'}")
    print(f"Версия установленного пакета (Xapian): {installed_version_real or installed_version or 'не указана'}")
    print(f"Версия установленного пакета (dpkg): {dpkg_version or 'не установлена'}")

    def format_deps(lst):
        return ', '.join(lst) if lst else 'нет'

    print(f"Зависит от (Depends): {format_deps(depends)}")
    print(f"Build-Depends: {format_deps(build_depends)}")
    print(f"Recommends: {format_deps(recommends)}")
    print(f"Suggests: {format_deps(suggests)}")
    print(f"Enhances: {format_deps(enhances)}")
    print(f"Pre-Depends: {format_deps(pre_depends)}")
    print(f"Breaks: {format_deps(breaks)}")
    print(f"Conflicts: {format_deps(conflicts)}")

    print("\nТермины:")
    for term in doc.termlist():
        term_str = term.term.decode("utf-8") if isinstance(term.term, bytes) else term.term
        print(f"  {term_str}")

    print("\nЗначения (values):")
    for i in range(doc.values_count()):
        raw = doc.get_value(i)
        try:
            text = raw.decode('utf-8')
        except Exception:
            text = "<не UTF-8>"
        print(f"  Value[{i}]: {text} (raw hex: {raw.hex()})")

    print("=" * 60 + "\n")

def main():
    parser = argparse.ArgumentParser(description="Dump Xapian terms for packages")
    parser.add_argument("db_path", help="Путь к индексу Xapian")
    parser.add_argument("queries", nargs="+", help="docid или имя пакета для поиска")
    parser.add_argument("--match", action="store_true", help="Искать подстроку в имени пакета")
    parser.add_argument("--glob", action="store_true", help="Искать по маске (glob) имени пакета")
    args = parser.parse_args()

    db = xapian.Database(args.db_path)

    def matches(name, pattern):
        if args.match:
            return pattern in name
        elif args.glob:
            return fnmatch.fnmatch(name, pattern)
        else:
            return name == pattern

    for query in args.queries:
        if query.isdigit():
            docid = int(query)
            dump_doc_info(db, docid)
        else:
            doccount = db.get_doccount()
            found = False
            for docid in range(1, doccount + 1):
                try:
                    doc = db.get_document(docid)
                except xapian.InvalidArgumentError:
                    continue
                name = get_pkg_name(doc)
                if name and matches(name, query):
                    dump_doc_info(db, docid)
                    found = True
            if not found:
                print(f"Пакеты, соответствующие '{query}', не найдены.")

if __name__ == "__main__":
    main()
