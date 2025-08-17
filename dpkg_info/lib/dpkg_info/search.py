#!/usr/bin/env python3
import sys
import xapian

def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <index_dir> <query>")
        sys.exit(1)

    index_dir = sys.argv[1]
    query_str = " ".join(sys.argv[2:])

    db = xapian.Database(index_dir)
    enquire = xapian.Enquire(db)
    qp = xapian.QueryParser()
    qp.set_database(db)
    qp.set_stemmer(xapian.Stem("en"))
    qp.set_stemming_strategy(xapian.QueryParser.STEM_SOME)

    query = qp.parse_query(query_str)
    enquire.set_query(query)
    matches = enquire.get_mset(0, 10)

    print(f"Results for query: '{query_str}'\n")
    for match in matches:
        doc = match.document
        print(f"Rank: {match.rank}, DocID: {match.docid}")
        print(f"Package: {doc.get_data().decode('utf-8')}")
        # Вывод первых 5 value-слотов
        for val_idx in range(5):
            val = doc.get_value(val_idx)
            if val:
                try:
                    val_decoded = xapian.sortable_unserialise(val)
                    print(f"Value[{val_idx}]: {val_decoded}")
                except Exception:
                    # если не удалось декодировать, выводим raw
                    print(f"Value[{val_idx}]: (raw) {val}")
        print("-" * 40)

if __name__ == "__main__":
    main()
