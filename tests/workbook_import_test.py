from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data_loader import load_rudder_pricing_workbook

SOURCE = Path('/mnt/data/Wine Prices_Paso - 2025-11-15.xlsx')

if SOURCE.exists():
    with SOURCE.open('rb') as f:
        df = load_rudder_pricing_workbook(f)
    assert len(df) == 120, len(df)
    assert df['winery'].nunique() == 5
    print('workbook import ok', len(df), 'rows', df['winery'].nunique(), 'wineries')
else:
    print('source workbook not present; skipped')
