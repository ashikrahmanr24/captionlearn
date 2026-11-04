import csv,argparse
p=argparse.ArgumentParser();p.add_argument("--gold",default="tests/gold_meanings.csv");a=p.parse_args();rows=list(csv.DictReader(open(a.gold,encoding="utf-8")));print(f"Loaded {len(rows)} gold rows. Run cards through the pipeline, then calculate chrF with sacrebleu.")
