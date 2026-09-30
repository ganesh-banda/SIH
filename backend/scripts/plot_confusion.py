"""Write a compact SVG confusion matrix from saved evaluation numbers."""
from __future__ import annotations

import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    text=(ROOT/"reports/model_evaluation.md").read_text(encoding="utf-8")
    data=json.loads(text.split("```json",1)[1].split("```",1)[0])
    out=ROOT/"reports/plots"
    out.mkdir(exist_ok=True)
    for model in ("xgboost","logistic_baseline"):
        cells=data[model]["test"]["confusion_matrix"]
        maximum=max(max(row) for row in cells)
        rects=[]
        for r in range(2):
            for c in range(2):
                n=cells[r][c]
                intensity=round(245-140*n/maximum)
                rects.append(f'<rect x="{150+c*130}" y="{90+r*100}" width="120" height="90" fill="rgb({intensity},{intensity+5},250)" stroke="#51617a"/><text x="{210+c*130}" y="{143+r*100}" text-anchor="middle" font-size="25" fill="#17243a">{n}</text>')
        svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="440" height="340" viewBox="0 0 440 340">
<rect width="440" height="340" fill="white"/>
<text x="220" y="35" text-anchor="middle" font-size="20" font-family="Arial">{model} — test confusion matrix</text>
<text x="275" y="75" text-anchor="middle" font-size="14" font-family="Arial">Predicted licit / illicit</text>
<text x="70" y="145" font-size="14" font-family="Arial">Actual licit</text>
<text x="65" y="245" font-size="14" font-family="Arial">Actual illicit</text>
{''.join(rects)}
<text x="220" y="317" text-anchor="middle" font-size="12" font-family="Arial">Chronological held-out test; rows actual, columns predicted</text>
</svg>'''
        (out/f"{model}_test_confusion.svg").write_text(svg,encoding="utf-8")
        print(out/f"{model}_test_confusion.svg")


if __name__=="__main__": main()
