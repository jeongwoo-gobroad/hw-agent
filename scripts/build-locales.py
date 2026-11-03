"""Compile editable i18next JSON and GNU gettext PO catalogs (development only)."""
import json
from pathlib import Path
from babel.messages.pofile import read_po
from babel.messages.mofile import write_mo

ROOT=Path(__file__).resolve().parents[1]/'src/hw_agent'
static=ROOT/'web/static'
resources={code:{'translation':json.loads((static/f'locales/{code}.json').read_text('utf8'))}
           for code in ('en','ko')}
assert resources['en']['translation'].keys()==resources['ko']['translation'].keys()
(static/'locales.js').write_text('window.AlterLocales = '+json.dumps(resources,ensure_ascii=False)+';\n','utf8')
for source in (ROOT/'locales').glob('*/LC_MESSAGES/*.po'):
    with source.open('rb') as f:catalog=read_po(f)
    with source.with_suffix('.mo').open('wb') as f:write_mo(f,catalog)
