"""전체 재실행: 실험 → 전문가 응답 반영 → 보고서 → 산출물.  python run_all.py  (약 3분)

전문가 요청 엑셀(make_expert_xlsx.py)은 응답을 받은 뒤라 여기서 다시 만들지 않는다(다시 만들면 평가ID가 달라질 수 있다)."""
import subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STEPS = ["experiments/exp_ranking.py", "experiments/exp_modules.py", "experiments/exp_expert.py", "experiments/make_report.py", "build_outputs.py"]

for s in STEPS:
    t = time.time()
    r = subprocess.run([sys.executable, str(ROOT / s)], cwd=ROOT)
    print(f"[{'ok' if r.returncode == 0 else 'FAIL'}] {s} {time.time() - t:.0f}s", flush=True)
    if r.returncode:
        sys.exit(r.returncode)
