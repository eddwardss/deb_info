#!/usr/bin/env python3
import xapian
import sys
import struct
import datetime
import subprocess
import fnmatch
import argparse
import os
import re
import difflib

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

def get_available_versions(pkg_name, debug=False):
    try:
        out = subprocess.check_output(['apt-cache', 'madison', pkg_name], stderr=subprocess.DEVNULL)
        lines = out.decode().strip().splitlines()
        versions = []
        if debug:
            print(f"[DEBUG] apt-cache madison output for {pkg_name}:")
            print(out.decode())
        for line in lines:
            parts = line.strip().split('|')
            if len(parts) >= 3:
                version = parts[1].strip()
                repo = parts[2].strip()
                versions.append((version, repo))
        return versions
    except subprocess.CalledProcessError:
        if debug:
            print(f"[DEBUG] apt-cache madison failed for {pkg_name}")
        return []


def get_package_metadata(pkg_name, lang=None, debug=False):
    section = None
    description = None

    if lang is None:
        # Извлечь язык из локали, например 'ru' из 'ru_RU.UTF-8'
        lang = os.environ.get("LANG", "en").split('.')[0].split('_')[0]

    if debug:
        print(f"[DEBUG] Ищем описание на языке: {lang}")

    try:
        out = subprocess.check_output(["apt-cache", "show", pkg_name], stderr=subprocess.DEVNULL)
        text = out.decode("utf-8", errors="replace")

        # Разбиваем вывод на блоки по пустой строке (один блок = один пакет)
        blocks = text.strip().split("\n\n")

        for block in blocks:
            lines = block.splitlines()

            current_section = None
            desc_dict = {}  # словарь для всех Description-*

            current_desc_key = None
            desc_lines = []

            for line in lines:
                # Секция
                if line.startswith("Section:"):
                    current_section = line.split(":", 1)[1].strip()

                # Поиск Description и Description-*
                m = re.match(r"^(Description(-[a-z]{2})?):\s*(.*)$", line)
                if m:
                    # Сохраняем предыдущий Description, если был
                    if current_desc_key and desc_lines:
                        desc_dict[current_desc_key] = "\n".join(desc_lines).strip()

                    current_desc_key = m.group(1)  # например, Description-ru или Description
                    desc_lines = [m.group(3).strip()]  # <-- именно здесь исправлено с m.group(4) на m.group(3)
                else:
                    # Если продолжается описание (отступ пробел)
                    if current_desc_key and line.startswith(" "):
                        desc_lines.append(line.strip())
                    else:
                        # Конец описания
                        if current_desc_key and desc_lines:
                            desc_dict[current_desc_key] = "\n".join(desc_lines).strip()
                        current_desc_key = None
                        desc_lines = []

            # После цикла — сохранить последний description
            if current_desc_key and desc_lines:
                desc_dict[current_desc_key] = "\n".join(desc_lines).strip()

            # Ищем локализованное описание по lang, fallback на Description
            description = desc_dict.get(f"Description-{lang}")
            if not description:
                description = desc_dict.get("Description")

            section = current_section
            if description:
                break  # нашли нужный блок, можно выйти

    except subprocess.CalledProcessError:
        if debug:
            print("[DEBUG] Ошибка при вызове apt-cache show")

    # fallback dpkg-query, если нет данных
    if not section or not description:
        try:
            if debug:
                print("[DEBUG] Пытаемся dpkg-query -s")
            out = subprocess.check_output(["dpkg-query", "-s", pkg_name], stderr=subprocess.DEVNULL)
            lines = out.decode("utf-8", errors="replace").splitlines()

            in_description = False
            description_lines = []

            for line in lines:
                if line.startswith("Section:"):
                    section = line.split(":", 1)[1].strip()
                elif line.startswith("Description:"):
                    description = line.split(":", 1)[1].strip()
                    in_description = True
                elif in_description:
                    if line.startswith(" "):
                        description_lines.append(line.strip())
                    else:
                        break

            if description_lines:
                description += "\n" + "\n".join(description_lines)

        except subprocess.CalledProcessError:
            if debug:
                print("[DEBUG] Ошибка при вызове dpkg-query")

    return section, description


def get_pkg_name(doc):
    for term in doc.termlist():
        term_str = term.term.decode("utf-8") if isinstance(term.term, bytes) else term.term
        if term_str.startswith("XP"):
            return term_str[2:]
    return None

def get_pkg_name_from_doc(doc):
    for term in doc.termlist():
        t = term.term.decode() if isinstance(term.term, bytes) else term.term
        if t.startswith("XP"):
            return t[2:]
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

    # Вывод секции и описания
    section, description = get_package_metadata(pkg_name, lang=args.lang, debug=args.debug)
    print(f"Раздел (Section): {section or 'не указан'}")
    print(f"Описание: {description or 'не указано'}")

    print("Версии apt-cache:")
    print(f"  Установленная версия: {apt_installed or 'не указана'}")
    print(f"  Кандидат на установку: {apt_candidate or 'не указана'}")

    if args.debug:
        print("\n[DEBUG] Детальная информация:")
        print(f"Installed flag: {installed_flag}")
        print(f"Raw installed version (value 0): {installed_raw}")
        print(f"Raw installed version (value 3): {doc.get_value(3)}")

    if args.full or args.full_all:
        print("\nДоступные версии в репозиториях:")
        available_versions = get_available_versions(pkg_name, debug=args.debug)
        if available_versions:
            for ver, repo in available_versions:
                markers = []
                if ver == apt_installed:
                    markers.append("*установлена*")
                if ver == apt_candidate:
                    markers.append("→ кандидат")
                marker_str = "  " + ", ".join(markers) if markers else ""
                print(f"  {ver:25} ({repo}){marker_str}")
        else:
            print("  Нет данных или пакет не найден в репозиториях.")

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


def list_packages_in_group(db, group_name):
    groups = set()
    doccount = db.get_doccount()
    for docid in range(1, doccount + 1):
        try:
            doc = db.get_document(docid)
        except Exception:
            continue
        pkg_name = get_pkg_name_from_doc(doc)
        if not pkg_name:
            continue
        section, _ = get_package_metadata(pkg_name)
        if section:
            groups.add(section)

    if group_name not in groups:
        # Найдем похожие группы
        close_matches = difflib.get_close_matches(group_name, groups, n=5, cutoff=0.5)
        print(f"Группа '{group_name}' не найдена.")
        if close_matches:
            print("Возможно, вы имели в виду одну из этих групп?")
            for gm in close_matches:
                print(f"  {gm}")
        else:
            print("Похожие группы не найдены.")
        return

    # Если группа найдена, выводим пакеты
    found = False
    for docid in range(1, doccount + 1):
        try:
            doc = db.get_document(docid)
        except Exception:
            continue
        pkg_name = get_pkg_name_from_doc(doc)
        if not pkg_name:
            continue
        section, _ = get_package_metadata(pkg_name)
        if section == group_name:
            print(pkg_name)
            found = True
    if not found:
        print(f"Пакеты группы '{group_name}' не найдены.")

def list_groups(db):
    groups = set()
    doccount = db.get_doccount()
    for docid in range(1, doccount + 1):
        try:
            doc = db.get_document(docid)
        except Exception:
            continue

        for term in doc.termlist():
            term_str = term.term.decode() if isinstance(term.term, bytes) else term.term
            if term_str.startswith("XS"):  # XS — section
                section = term_str[2:]
                groups.add(section)
                break  # одна секция на пакет, можно прервать цикл

    for group in sorted(groups):
        print(group)


def list_packages_in_group(db, group_name):
    doccount = db.get_doccount()
    found = False
    for docid in range(1, doccount + 1):
        try:
            doc = db.get_document(docid)
        except Exception:
            continue

        # Проверяем, есть ли у документа термин секции, совпадающий с group_name
        section = None
        for term in doc.termlist():
            term_str = term.term.decode() if isinstance(term.term, bytes) else term.term
            if term_str.startswith("XS") and term_str[2:] == group_name:
                section = group_name
                break

        if section == group_name:
            # Берём имя пакета из документа
            pkg_name = get_pkg_name_from_doc(doc)
            if pkg_name:
                print(pkg_name)
                found = True

    if not found:
        print(f"Пакеты группы '{group_name}' не найдены.")


def main():
    parser = argparse.ArgumentParser(description="Работа с Xapian индексом пакетов")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # info команда
    info_parser = subparsers.add_parser("info")
    info_parser.add_argument("db_path", help="Путь к базе Xapian")
    info_parser.add_argument("queries", nargs="+", help="Имя пакета или ID документа")
    info_parser.add_argument("--full", action="store_true", help="Вывести полную информацию")
    info_parser.add_argument("--full-all", action="store_true", help="Вывести все термы")
    info_parser.add_argument("--debug", action="store_true", help="Режим отладки")
    info_parser.add_argument("--lang", help="Язык описания")

    # group команда
    group_parser = subparsers.add_parser("group")
    group_parser.add_argument("--list-groups", action="store_true", help="Вывести список групп")
    group_parser.add_argument("--list-packages", help="Вывести пакеты группы")
    group_parser.add_argument("db_path", help="Путь к базе Xapian")

    # search команда (если нужна)
    # list команда (если нужна)

    args = parser.parse_args()

    # Открываем базу
    try:
        db = xapian.Database(args.db_path)
    except Exception as e:
        print(f"Ошибка при открытии базы: {e}")
        sys.exit(1)

    if args.command == "info":
        for query in args.queries:
            if query.isdigit():
                docid = int(query)
                try:
                    dump_doc_info(db, docid, args)
                except Exception as e:
                    print(f"Ошибка при обработке документа с ID={docid}: {e}")
            else:
                found_any = False
                doccount = db.get_doccount()
                for docid in range(1, doccount + 1):
                    try:
                        doc = db.get_document(docid)
                    except xapian.InvalidArgumentError:
                        continue
                    name = get_pkg_name_from_doc(doc)
                    if not name:
                        continue
                    if name == query:
                        dump_doc_info(db, docid, args)
                        found_any = True
                if not found_any:
                    print(f"Пакеты, соответствующие '{query}', не найдены.")

    elif args.command == "group":
        if args.list_groups:
            list_groups(db)
        elif args.list_packages:
            list_packages_in_group(db, args.list_packages)
        else:
            print("Ошибка: для команды group нужно указать --list-groups или --list-packages <group_name>")
            sys.exit(1)
    else:
        print(f"Неизвестная команда: {args.command}")
        sys.exit(1)

if __name__ == "__main__":
    main()
