import test from 'node:test';
import assert from 'node:assert/strict';
import {gradingOutcome,gradeQuestion,gradingSummary,applyRecognizedDates} from '../frontend/src/manualGrading.ts';
const questions=()=>Array.from({length:30},(_,i)=>({number:i+1,user_answer:'?',grading_status:null,score_value:null}));
test('bulk correct gives 100 without keys or weights',()=>{
 const rows=questions().map(q=>gradeQuestion(q,'CORRECT'));
 assert.equal(gradingSummary(rows,'math').score,100);
 assert.equal(rows[0].user_answer,'?');
 assert.ok(rows.every(q=>q.correct_answer===null&&q.score_value===null));
});
test('individual wrong, missing weight, deduction, and return to correct',()=>{
 const rows=questions().map(q=>gradeQuestion(q,'CORRECT'));
 rows[15]=gradeQuestion(rows[15],'WRONG');
 assert.equal(gradingSummary(rows,'math').score,null);
 rows[15].score_value=4;
 assert.equal(gradingSummary(rows,'math').score,96);
 rows[15]=gradeQuestion(rows[15],'CORRECT');
 assert.equal(rows[15].score_value,null);
 assert.equal(gradingSummary(rows,'math').score,100);
});
test('bulk wrong requires only wrong weights; unchecking removes grade',()=>{
 const rows=questions().map(q=>({...gradeQuestion(q,'WRONG'),score_value:3}));
 assert.equal(gradingSummary(rows,'math').score,10);
 rows[0]=gradeQuestion(rows[0],null);
 assert.equal(gradingOutcome(rows[0]),'UNGRADED');
 assert.equal(gradingSummary(rows,'math').score,null);
});
test('OMR date succeeds, fails, or conflicts without silent today fallback',()=>{
 assert.deepEqual(applyRecognizedDates(['2026-09-17']),{exam_date:'2026-09-17',date_needs_review:false});
 assert.deepEqual(applyRecognizedDates([null,'2026-09-17']),{exam_date:'',date_needs_review:true});
 assert.equal(applyRecognizedDates(['2026-09-17','2026-09-18']).date_needs_review,true);
});
