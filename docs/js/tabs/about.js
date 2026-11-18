// 안내: 이 플랫폼이 무엇을 어떻게 계산하는지, 표시의 뜻, 한계
import { S, api, esc } from '../core.js';

export async function render(view) {
  const m = S.meta, llm = S.llm || await api('llm/status').catch(() => ({ available: false }));
  view.innerHTML = `<div class="page" style="max-width:980px">
    <div class="page-head"><div><h2>안내</h2><p>온터는 단지마다 검토할 복지 프로그램 후보를 근거와 함께 보여 주는 도구입니다. 결정은 관리소 직원과 주거복지사가 합니다.</p></div></div>
    <div class="panel"><h3>화면 구성</h3>
      <table class="tbl"><tbody>
        <tr><td><b><a href="#/map">지도</a></b></td><td>전국 ${m.counts.complexes}개 단지를 지도에서 고릅니다. 색 기준을 바꿔 고령 비율, 필요 분야, 기록 수, 만족도를 볼 수 있습니다.</td></tr>
        <tr><td><b><a href="#/complex">단지 현황</a></b></td><td>단지 카드, 분야별 필요와 공급, 확인된 필요 입력, 운영 이력, 프로그램 상태표, 비슷한 단지.</td></tr>
        <tr><td><b><a href="#/recommend">프로그램 추천</a></b></td><td>검토 후보와 추천 근거, 비슷한 단지 운영 사례, 사례집의 걸림돌·해결, 실행 점검표. 조절 손잡이로 다시 계산합니다.</td></tr>
        <tr><td><b><a href="#/plan">실행 계획</a></b></td><td>예산·인력 한도 안에서 한 해 묶음을 정수계획으로 고릅니다.</td></tr>
        <tr><td><b><a href="#/programs">프로그램 사전</a></b></td><td>표준 프로그램 ${m.counts.programs}종의 정의, 요건, 운영 현황, 사례. 자유 검색.</td></tr>
        <tr><td><b><a href="#/cases">사례·소식</a></b></td><td>사례집 카드, 걸림돌·해결 정리, 뉴스 제목과 링크.</td></tr>
        <tr><td><b><a href="#/happycall">해피콜</a></b></td><td>관리소별 만족도, 주민이 말한 수요, 수요·공급·추천 분포, 주민 의견.</td></tr>
        <tr><td><b><a href="#/analysis">분석</a></b></td><td>변수 탐색기, 전국 수요와 공급, 실험 결과 표.</td></tr>
        <tr><td><b><a href="#/kg">Knowledge Graph</a></b></td><td>단지·프로그램·기록·사례·소식의 연결을 그래프로 탐색합니다.</td></tr>
      </tbody></table></div>
    <div class="panel"><h3>추천은 이렇게 계산합니다</h3>
      <ol style="margin:0;padding-left:20px">
        <li><b>근거 점수</b>: 비슷한 단지 20곳 가운데 운영한 비율, 이 단지가 하는 프로그램과 함께 운영되는 정도, 전체 단지 운영 비율을 순위로 바꿔 평균합니다.</li>
        <li><b>필요 적합</b>: 단지의 분야별 필요(인구·주택·접근성 지표)와 프로그램의 분야 소속, 주민 구성과 프로그램 대상의 맞음으로 계산합니다. 활동 기록은 쓰지 않습니다.</li>
        <li><b>섞기</b>: 근거 ${(1 - m.defaults.w).toFixed(1)} + 필요 ${m.defaults.w.toFixed(1)}(기본값). '필요 반영 정도'로 바꿀 수 있습니다.</li>
        <li><b>분야 고르게</b>: 목록의 분야 구성이 단지의 목표 분포에서 너무 벗어나지 않게 고릅니다(기본 ${m.defaults.lam}).</li>
        <li><b>실행 검토</b>: 비용·인력·공간·협력기관은 순위에 넣지 않고 점검표와 한도(정수계획)로 따로 봅니다.</li>
      </ol>
      <div class="note" style="margin-top:8px">순위 점수는 평소에 감춰 두었습니다. 점수는 줄을 세우는 데만 쓰이고 필요나 효과의 크기를 뜻하지 않기 때문입니다. 후보 카드의 '점수 ⓘ'에 마우스를 올리면 볼 수 있습니다.</div></div>
    <div class="panel"><h3>상태 표시의 뜻</h3>
      <table class="tbl"><tbody>
        <tr><td><span class="na">자료 없음</span></td><td><b>결측.</b> 값이 비어 있습니다. 0이 아닙니다(예: 시설까지 거리, 복지 만족도).</td></tr>
        <tr><td><span class="st no_record">기록 없음</span></td><td>단지의 활동 기록 자체가 없습니다(${m.counts.complexes - m.counts.with_records}곳). 프로그램을 안 한 것인지 알 수 없습니다.</td></tr>
        <tr><td><span class="st not_run">미운영</span></td><td>단지에 활동 기록은 있는데 이 프로그램의 기록은 없습니다. 추천 후보가 됩니다.</td></tr>
        <tr><td><span class="st running">운영 중</span> <span class="st paused">과거 운영</span></td><td>최근 12개월 안에 기록이 있으면 운영 중, 그보다 오래되면 과거 운영(재개 검토)입니다.</td></tr>
        <tr><td><span class="st infeasible">운영 불가능</span></td><td>사용자가 이 단지에서는 할 수 없다고 표시했습니다. 다시 추천하지 않습니다.</td></tr>
        <tr><td><span class="st snoozed">보류</span></td><td>'지금은 아님'으로 뺐습니다. 새 후보가 모자랄 때만, ${m.max_resurface}번 뺄 때까지는 다시 보여 줄 수 있습니다. 그보다 더 빼면 나오지 않습니다.</td></tr>
        <tr><td><span class="st declared">운영 중(기록 누락)</span></td><td>사용자가 이미 하고 있다고 표시했습니다. 후보에서 빼고 기록 누락으로 구분합니다.</td></tr>
      </tbody></table>
      <div class="note" style="margin-top:8px">후보가 모자랄 때 채우는 순서: 새 후보 → 과거 운영(재개 검토) → 보류 ${m.max_resurface}번 이하. 운영 불가능과 이미 운영 중은 채우는 데 쓰지 않습니다.</div></div>
    <div class="panel"><h3>LLM은 문장에만 씁니다 <span class="chip ${llm.available ? 'ok' : 'warn'}">${llm.static ? '미리 만들어 둔 문장' : llm.available ? '사용 가능 · ' + esc(llm.model || '') : '연결 안 됨'}</span></h3>
      <p style="margin:0">로컬 LLM(Ollama)은 추천 근거 문장 다듬기, 실행 점검표, 묶음 설명에만 씁니다. 순위·필요·비용 계산에는 쓰지 않습니다. 입력은 계산된 사실 목록뿐이고, 출력에 사실에 없는 숫자나 단정 표현, 뜻이 바뀐 수치가 있으면 버리고 규칙으로 만든 문장을 보여 줍니다. 자료는 이 PC 밖으로 나가지 않습니다.</p></div>
  </div>`;
}
