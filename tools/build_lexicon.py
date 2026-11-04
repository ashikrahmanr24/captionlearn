import argparse,sqlite3
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument("input");p.add_argument("--database",default="work/captionlearn-users.db");a=p.parse_args();c=sqlite3.connect(a.database);c.execute("CREATE TABLE IF NOT EXISTS bilingual_lexicon (source TEXT,target TEXT,source_lang TEXT,target_lang TEXT,pos TEXT,example TEXT,source_tag TEXT,PRIMARY KEY(source,source_lang,target_lang))");c.execute("CREATE INDEX IF NOT EXISTS ix_lexicon_lookup ON bilingual_lexicon(source,source_lang,target_lang)")
for line in Path(a.input).read_text(encoding="utf-8").splitlines():
 if line.strip() and not line.startswith("#"):
  en,ta,*rest=line.split("\t");pos=rest[0] if rest else "";example=rest[1] if len(rest)>1 else "";c.execute("INSERT OR REPLACE INTO bilingual_lexicon VALUES (?,?,?,?,?,?,?)",(en,ta,"en","ta",pos,example,"Wiktionary"));c.execute("INSERT OR REPLACE INTO bilingual_lexicon VALUES (?,?,?,?,?,?,?)",(ta,en,"ta","en",pos,example,"Wiktionary"))
c.commit();print("Lexicon built.")
