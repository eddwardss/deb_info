#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from axi.indexer import Indexer, SilentProgress, Plugins
import axi


def main():
    # Пути из окружения
    db_path = os.environ.get("AXI_DB_PATH", "./xapian-index")
    cache_path = os.environ.get("AXI_CACHE_PATH", "/var/cache/apt-xapian-index")
    plugin_path = os.environ.get("AXI_PLUGIN_PATH", "/usr/share/apt-xapian-index/plugins")

    # Настройка путей
    axi.XAPIANDBPATH = db_path
    axi.XAPIANDB = os.path.join(db_path, "index")
    axi.XAPIANCACHEPATH = cache_path
    axi.PLUGINDIR = plugin_path

    progress = SilentProgress()
    indexer = Indexer(progress)

    print("Загрузка плагинов...")
    indexer.plugins = Plugins(progress=progress)
    print("Плагины:", [addon.name for addon in indexer.plugins])

    # Собираем values и values_desc вручную из info()
    indexer.values = {}
    indexer.values_desc = {}
    next_slot = 0

    for addon in indexer.plugins:
        if hasattr(addon.obj, 'info'):
            info = addon.obj.info()
            for v in info.get('values', []):
                name = v.get('name')
                desc = v.get('desc', '')
                if name and name not in indexer.values:
                    indexer.values[name] = next_slot
                    indexer.values_desc[name] = desc
                    next_slot += 1

    # Подготовка info для init()
    values_info = [{"name": name, "desc": indexer.values_desc.get(name, "")}
                   for name in indexer.values]

    # Инициализация плагинов
    for addon in indexer.plugins:
        if hasattr(addon.obj, 'init'):
            print(f"Инициализация плагина: {addon.name}")
            addon.obj.init({"values": values_info}, progress)

    print("indexer.values =", indexer.values)
    print("indexer.values_desc =", indexer.values_desc)

    # Перестроение индекса
    indexer.rebuild()
    print("Индекс обновлён.")


if __name__ == "__main__":
    main()
