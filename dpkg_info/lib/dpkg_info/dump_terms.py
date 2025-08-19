#!/usr/bin/env python3
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

def get_apt_versions(pkg_name, debug=False):
    try:
        if debug:
            print(f"[DEBUG] get_apt_versions({pkg_name}) called")

        out = subprocess.check_output(['apt-cache', 'policy', pkg_name], stderr=subprocess.DEVNULL)
        lines = out.decode().splitlines()
        if debug:
            print("[DEBUG] apt-cache output:")
            print(out.decode())

        installed = None
        candidate = None
        for line in lines:
            line = line.strip()
            if line.startswith('Установлен:') or line.startswith('Installed:'):
                installed = line.split(':', 1)[1].strip()
            elif line.startswith('Кандидат:') or line.startswith('Candidate:'):
                candidate = line.split(':', 1)[1].strip()

        if debug:
            print(f"[DEBUG] apt_installed={installed}, apt_candidate={candidate}")

        return installed, candidate
    except subprocess.CalledProcessError:
        return None, None

def get_pkg_name(doc):
    for term in doc.termlist():
        term_str = term.term.decode("utf-8") if isinstance(term.term, bytes) else term.term
        if term_str.startswith("XP"):
            return term_str[2:]
    return None

def dump_doc_info(db, docid, args):
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
    apt_installed, apt_candidate = get_apt_versions(pkg_name, debug=args.debug)

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

    # Вывод термов, если --full-all
    if args.full_all:
        print(f"Документ ID: {docid}")
        print("Термы документа:")
        for term in doc.termlist():
            t = term.term.decode() if isinstance(term.term, bytes) else term.term
            print(f"  {t}")

    print(f"\nДокумент ID: {docid}")
    print(f"Пакет: {pkg_name or 'неизвестен'}")
    print(f"Версия в репозитории (Xapian): {repo_version or 'не указана'}")
    print(f"Версия установленного пакета (Xapian): {installed_version_real or installed_version or 'не указана'}")
    print(f"Версия установленного пакета (dpkg): {dpkg_version or 'не установлена'}")

    print("Версии apt-cache:")
    print(f"  Установленная версия: {apt_installed or 'не установлена'}")
    print(f"  Кандидат на обновление: {apt_candidate or 'не указан'}")

    if args.full or args.full_all:
        try:
            files_output = subprocess.check_output(["dpkg", "-L", pkg_name], stderr=subprocess.DEVNULL)
            files = files_output.decode("utf-8").strip().split("\n")
            if args.full:
                files = files[:5]

            print(f"\nФайлы ({'все' if args.full_all else 'первые 5'}):")
            for f in files:
                print(f"  {f}")
        except subprocess.CalledProcessError:
            print("\nФайлы: не удалось получить список файлов (пакет, возможно, не установлен)")

def get_pkg_name_from_doc(doc):
    for term in doc.termlist():
        t = term.term.decode() if isinstance(term.term, bytes) else term.term
        if t.startswith("XP"):
            return t[2:]
    return None

def main():
    parser = argparse.ArgumentParser(description="Dump Xapian terms for packages")
    parser.add_argument("db_path", help="Путь к индексу Xapian")
    parser.add_argument("queries", nargs="+", help="docid или имя пакета для поиска")
    parser.add_argument("--match", action="store_true", help="Искать подстроку в имени пакета")
    parser.add_argument("--glob", action="store_true", help="Искать по маске (glob) имени пакета")
    parser.add_argument("--full", action="store_true", help="Показать первые 5 файлов пакета")
    parser.add_argument("--full-all", action="store_true", help="Показать все файлы пакета и термы")
    parser.add_argument("--debug", action="store_true", help="Включить отладочный вывод")

    args = parser.parse_args()

    if args.full_all:
        args.full = False

    try:
        db = xapian.Database(args.db_path)
    except Exception as e:
        print(f"Ошибка при открытии базы: {e}")
        sys.exit(1)

    def matches(name, pattern):
        if args.match:
            return pattern in name
        elif args.glob:
            return fnmatch.fnmatch(name, pattern)
        else:
            return name == pattern

    found_any = False

    for query in args.queries:
        if query.isdigit():
            docid = int(query)
            try:
                dump_doc_info(db, docid, args)
                found_any = True
            except Exception as e:
                if args.debug:
                    print(f"[DEBUG] Ошибка при обработке docid={docid}: {e}")
        else:
            doccount = db.get_doccount()
            for docid in range(1, doccount + 1):
                try:
                    doc = db.get_document(docid)
                except xapian.InvalidArgumentError:
                    continue
                name = get_pkg_name_from_doc(doc)
                if name and matches(name, query):
                    dump_doc_info(db, docid, args)
                    found_any = True
            if not found_any:
                print(f"Пакеты, соответствующие '{query}', не найдены.")

if __name__ == "__main__":
    main()
