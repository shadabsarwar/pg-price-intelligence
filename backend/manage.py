"""Local administrator CLI. No web token needed for an operator with filesystem access."""
import argparse
import json
from pathlib import Path

from config import load_environment
load_environment()
from services.database import Database
from services.imports import Importer, read_rows
from services.repository import Repository
from services.matches import MatchService


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', help='Database file (default: INTELLIGENCE_DB_PATH)')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('migrate')
    sub.add_parser('seed-demo')
    sub.add_parser('recalculate')
    ingest = sub.add_parser('import')
    ingest.add_argument('file', type=Path)
    ingest.add_argument('--kind', choices=['pg', 'competitor'], required=True)
    ingest.add_argument('--source', choices=['IMPORTED', 'MANUAL', 'DEMO'], default='IMPORTED')
    ingest.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    db = Database(args.db)
    if args.command == 'seed-demo':
        from services.demo_migration import migrate_demo
        result = migrate_demo(db)
    elif args.command == 'import':
        with args.file.open(encoding='utf-8-sig') as file:
            # CSV is iterated row-by-row for large catalogues; JSON is bounded by available memory.
            import csv
            rows = csv.DictReader(file) if args.file.suffix.lower() == '.csv' else json.load(file)
            result = Importer(db).run(rows, args.kind, args.source, args.dry_run)
        if not args.dry_run:
            MatchService(Repository(db)).recalculate()
    elif args.command == 'recalculate':
        result = MatchService(Repository(db)).recalculate()
    else:
        result = {'database': db.path, 'status': 'migrated'}
    print(json.dumps(result, indent=2))
    return 1 if result.get('errors') else 0


if __name__ == '__main__':
    raise SystemExit(main())
