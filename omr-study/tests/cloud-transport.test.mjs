import test from 'node:test';
import assert from 'node:assert/strict';
import { analyzeUpload, uploadAttachment, importBackup } from '../frontend/src/cloud.ts';

test('large files go directly to storage; PDF pages use separate small API requests', async () => {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push({url, options});
    const reply = (value) => new Response(JSON.stringify(value), {status: 200});
    if (url === '/api/config') return reply({direct_upload: true});
    if (url === '/api/uploads/sign') return reply({file_id: 'upload-1', upload_url: 'https://private-storage.test/signed-upload'});
    if (url === 'https://private-storage.test/signed-upload') return reply({});
    if (url === '/api/uploads/complete') return reply({id: 'upload-1', pages: 3});
    if (url === '/api/omr/analyze-page') {
      const {page} = JSON.parse(options.body);
      return reply({pages: [{page}], file_ids: ['upload-1', `crop-${page}`]});
    }
    throw new Error(`Unexpected call ${url}`);
  };
  try {
    const file = new File([new Uint8Array(5 * 1024 * 1024)], 'exam.pdf', {type: 'application/pdf'});
    const updates = [];
    const result = await analyzeUpload(file, message => updates.push(message));
    assert.equal(result.pages.length, 3);
    assert.deepEqual(result.file_ids, ['upload-1', 'crop-1', 'crop-2', 'crop-3']);
    assert.equal(calls.find(c => c.url.startsWith('https:')).options.body, file);
    for (const call of calls.filter(c => c.url.startsWith('/api') && c.options.body)) assert.ok(call.options.body.length < 1000);
    assert.equal(updates.length, 4);
    await uploadAttachment(file, 'exam-1');
    const sign = calls.filter(c => c.url === '/api/uploads/sign').at(-1);
    assert.equal(JSON.parse(sign.options.body).exam_id, 'exam-1');
  } finally { globalThis.fetch = original; }
});

test('cloud restore skips known records and sends file IDs instead of base64', async () => {
  const original = globalThis.fetch;
  let imported;
  globalThis.fetch = async (url, options = {}) => {
    const reply = value => new Response(JSON.stringify(value));
    if (url === '/api/config') return reply({direct_upload: true});
    if (url === '/api/exams') return reply([{id: 'existing'}]);
    if (url === '/api/import/check') return reply({exists: false});
    if (url === '/api/uploads/sign') return reply({file_id: 'new-file', upload_url: 'https://private-storage.test/upload'});
    if (url === 'https://private-storage.test/upload') return reply({});
    if (url === '/api/uploads/complete') return reply({id: 'new-file', pages: 1});
    if (url === '/api/import') { imported = JSON.parse(options.body); return reply({added: 1, skipped: 0}); }
    throw new Error(`Unexpected call ${url}`);
  };
  try {
    const result = await importBackup(new File([JSON.stringify({version: 1, exams: [{id: 'existing'}, {id: 'new', file_ids: ['old-file']}], files: [{id: 'old-file', extension: '.png', kind: 'crop', data: btoa('image')}]})], 'backup.json'));
    assert.deepEqual(result, {added: 1, skipped: 1});
    assert.equal(imported.files[0].stored_file_id, 'new-file');
    assert.equal(imported.files[0].data, undefined);
  } finally { globalThis.fetch = original; }
});
