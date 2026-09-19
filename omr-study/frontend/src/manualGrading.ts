export type Question = {number:number;grading_status?:string|null;correct_answer?:string|null;user_answer:string;score_value?:number|null};
export function gradingOutcome(q: Question):string {
  if(q.grading_status === 'CORRECT' || q.grading_status === 'WRONG') return q.grading_status;
  if(q.correct_answer != null && q.correct_answer !== '') return String(q.user_answer)===String(q.correct_answer)?'CORRECT':'WRONG';
  return 'UNGRADED';
}
export function gradeQuestion<T extends Question>(q:T,status:'CORRECT'|'WRONG'|null):T {
  return {...q,grading_status:status,correct_answer:null,score_value:status==='WRONG'?q.score_value??null:null};
}
export function gradingSummary(questions:Question[],subject:string){
  const expected=subject==='math'?30:45;
  const correct=questions.filter(q=>gradingOutcome(q)==='CORRECT').length;
  const wrong=questions.filter(q=>gradingOutcome(q)==='WRONG');
  const ungraded=expected-correct-wrong.length;
  const missing=wrong.filter(q=>q.score_value==null).map(q=>q.number);
  const deduction=wrong.reduce((total,q)=>total+(q.score_value??0),0);
  const invalid=wrong.some(q=>q.score_value!=null&&(!Number.isFinite(q.score_value)||q.score_value<0))||deduction>100;
  return {correct,wrong:wrong.length,ungraded,missing,deduction,score:!ungraded&&!missing.length&&!invalid?100-deduction:null,invalid};
}
export function applyRecognizedDates(dates:(string|null)[]){
  const distinct=[...new Set(dates.filter((v):v is string=>!!v))];
  const needsReview=dates.some(v=>!v)||distinct.length!==1;
  return {exam_date:needsReview?'':distinct[0],date_needs_review:needsReview};
}
