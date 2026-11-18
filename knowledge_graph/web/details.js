function content(n){const a=n.attrs;let html='';
 if(n.kind==='program'){
  html+=section('무엇을 하는 프로그램인가요?',a.definition_ko)+kv('목적',a.purpose_primary_label)+kv('통상 대상',a.target_default)+kv('운영 방식',a.mode_default)+kv('필요 자원',a.resource_default)+kv('주요 운영 월',a.month_peak+'월')+kv('기록 / 시행 단지',fmt(a.n_records)+'건 / '+fmt(a.n_complexes)+'곳');
  html+='<div class="notice">위 대상·자원은 유형의 통상 속성입니다. 개별 단지에 실제 존재하거나 필수라고 확정한 값이 아닙니다.</div>';
 }else if(n.kind==='complex'){
  html+=kv('주소',a.기본주소)+kv('세대수 / 기준연도',fmt(a.세대수)+'세대 / '+fmt(a.세대수_기준연도))+kv('거주 인구',fmt(a.총거주인구)+'명')+kv('60세 이상',pct(a.인구_60세이상_비율))+kv('공급 유형',a.공급유형);
  const p=a['모델 프로파일'];if(p){html+='<h3>필요 지표의 추정 구간</h3><p>실제 수요 조사값이 아닌 지표 기반 백분위입니다.</p>';for(let i=1;i<=6;i++)html+=kv(['안부와 관계','생활과 경제','건강과 돌봄','주거환경과 생활안전','문화와 활동','일자리와 학습'][i-1],`${pct(p['need_N'+i])} · 구간 ${pct(p['need_lo_N'+i])}–${pct(p['need_hi_N'+i])}`);}
  if(n.monthly?.length){const vals=n.monthly.map(x=>Number(x.지원내용총건수||0)),max=Math.max(...vals,1);html+='<h3>홈닥터 월별 기록</h3><div class="mini-bars">'+n.monthly.map((x,i)=>`<i title="${esc(x.기간)} · ${fmt(vals[i])}건" style="height:${Math.max(2,vals[i]/max*62)}px"></i>`).join('')+'</div><div class="spark-note">'+esc(n.monthly[0].기간)+' ~ '+esc(n.monthly.at(-1).기간)+' · 관측된 월만 표시, 고유 수혜자 수 아님</div>';}
 }else if(n.kind==='record'){
  html+=kv('실행 시점',a.start_date)+kv('프로그램 분류',a.std_name)+kv('활동 횟수',fmt(a.activity_count))+kv('기록 참여인원',fmt(a.participants_total))+section('기록된 활동',a.activity_content_masked)+kv('장소',a.place_masked)+kv('협력기관 유형',a.partner_org_labels);
  html+='<div class="notice">참여인원은 반복 참여가 가능한 기록 인원입니다. 자동 분류는 전문가 확정 정답과 구분합니다.'+(a.dup_exact_first_flag==='0'?' 이 행은 중복 집계에서 제외됩니다.':'')+'</div>';
 }else if(n.kind==='case'){
  html+=section('사례의 맥락',a.summary)+kv('사례 지역',a.region);
 }else if(n.kind==='card'){
  for(const [field,title]of [['need','왜 시작했나요?'],['target','누구를 대상으로 했나요?'],['partners','누구와 협력했나요?'],['operation','어떻게 운영했나요?'],['how_it_runs','실행 방법'],['obstacles_and_solutions','어려움과 해결'],['outcomes','사례집에 기술된 성과'],['lessons','실행할 때 참고할 점']])html+=section(title,a[field]);
  html+='<div class="notice">사례집에 기술된 내용이며, 다른 단지에서도 같은 효과가 난다는 뜻은 아닙니다.</div>';
 }else if(n.kind==='obstacle'){
  html+=section('어떤 어려움이 있었나요?',a.obstacle)+section('사례집의 해결 방법',a.solution)+kv('해결 전략',a.solution_strategy)+kv('기록된 상태',a.status);
 }else if(n.kind==='news'){
  html+=kv('매체',a.outlet)+kv('발행일',a.date);const url=safeURL(a.url);if(url)html+=`<p><a class="linkbtn" href="${esc(url)}" target="_blank" rel="noopener noreferrer">기사 원문에서 확인 ↗</a></p>`;html+='<div class="notice">기사는 현장 보도 참고 자료입니다. 이용허락 미확인 본문은 이 화면에 재게시하지 않습니다.</div>';
 }else if(n.kind==='survey'){
  html+=kv('조사 대상',a.population)+kv('집계 범위',a.scope)+kv('응답자 구분',[a.group,a.subgroup].filter(Boolean).join(' · '))+kv('응답 항목',a.metric)+kv('응답값',fmt(a.value)+'%')+kv('응답 표본 수',fmt(a.n))+kv('복수응답',a.multiple_response)+'<div class="notice">전국 또는 응답자 집계입니다. 특정 단지의 실제 수요로 복제하거나 학습 정답으로 쓰지 않습니다.</div>';
 }else if(n.kind==='voc'){
  html+=section('주민 의견',a.text)+kv('범위',a.scope)+kv('원문에 적힌 빈도',fmt(a.frequency_explicit))+'<div class="notice">이 의견은 특정 단지의 응답으로 연결하지 않았습니다.</div>';
 }else if(n.kind==='office'){
  html+=kv('관리소',a.source_name)+kv('전체 사례수',fmt(a.n_total))+kv('복지 항목 사례수',fmt(a.n_welfare))+kv('복지서비스 만족도',fmt(a.welfare_satisfaction))+kv('표본 30명 미만',a.small_sample)+'<div class="notice">만족도는 필요나 프로그램 효과의 정답이 아닙니다. 전체 사례수를 복지 항목의 응답 분모로 쓰지 않으며, 공유 관리소 점수를 각 단지에 복제하지 않습니다.</div>';
 }else if(n.kind==='recommendation'){
  html+='<div class="notice">모델이 계산한 검토 후보입니다. 채택·실행·효과가 확인된 기록이 아닙니다.</div>'+kv('순위',a.rank)+kv('근거 점수',fmt(a.evidence_pct))+kv('필요 적합 점수',fmt(a.need_fit_pct))+section('기존 근거 설명',a.explanation);
  if(n.local_explanation)html+=section('프로그램 제안 이유',n.local_explanation.text);
  html+=kv('연간 비용 추정',fmt(a.check?.cost_year_est)+'원')+kv('인력 부담 추정',a.check?.staff_tier+' / 5')+section('점검할 공간',(a.check?.place||[]).join(' · '));
 }else{html+=section('설명',a.description||a.definition_ko||a.summary||a.text);if(!html)html='<p class="empty">연결된 프로그램과 사례에서 더 자세한 내용을 살펴보세요.</p>';}
 return html;
}