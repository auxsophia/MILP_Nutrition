import data_loader as dl, repertoire_store as store
rows, *_ = dl.build_repertoire_table(store.load())
# lysine = 1214, methionine = 1215
have = [r["label"] for r in rows if 1214 in r["per_100g"]]
lack = [r["label"] for r in rows if 1214 not in r["per_100g"]]
print(f"have amino acid data: {len(have)} / {len(rows)}")
print("missing:", lack[:15])