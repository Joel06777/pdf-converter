"""Uso: python scripts/convert_cli.py archivo.pdf excel|word|pptx [salida] [layout]

layout (solo Excel): 'pages' (una hoja por página) o 'continuous' (una hoja).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.converters import TARGETS, convert  # noqa: E402

if len(sys.argv) < 3:
    sys.exit(__doc__)
src, target = sys.argv[1], sys.argv[2]
dst = sys.argv[3] if len(sys.argv) > 3 else str(Path(src).with_suffix("." + TARGETS[target][0]))
layout = sys.argv[4] if len(sys.argv) > 4 else "pages"
print(json.dumps(convert(src, dst, target, layout=layout), indent=2, ensure_ascii=False))
print("->", dst)
