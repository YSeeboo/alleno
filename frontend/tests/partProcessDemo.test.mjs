import test from 'node:test';
import assert from 'node:assert/strict';
import { initialState, getPart, available, createSpec, sendProcessing, receiveProcessing, requirements, allocate, updateBom } from '../public/demos/part-process/domain.js';

const GOLD = 'PJ-DZ-00001-G';
const RED = 'DEMO-P-003';
test('create a zero-stock spec without duplicating public material information', () => {
  const state = initialState();
  const result = createSpec(state, { group: 'flower', plating: '金色', oil: '黄色', area: '花瓣' });
  assert.equal(result.created, true);
  assert.equal(result.part.stock, 0);
  assert.equal(result.part.group, 'flower');
  assert.equal(state.parts.length, 8);
  assert.equal('material' in result.part, false);
});
test('reuse an existing spec, including trimmed inputs, without modifying stock', () => {
  const state = initialState();
  const result = createSpec(state, { group: 'flower', plating: ' 金色 ', oil: '红色 ', area: ' 花瓣' });
  assert.equal(result.created, false);
  assert.equal(result.part.id, RED);
  assert.equal(result.part.stock, 24);
  assert.equal(state.parts.length, 7);
});
test('placement distinguishes specs, while no-oil ignores placement', () => {
  const state = initialState();
  assert.equal(createSpec(state, { group: 'flower', plating: '金色', oil: '红色', area: '花心' }).created, true);
  assert.equal(createSpec(state, { group: 'flower', plating: '金色', oil: '无', area: '花瓣' }).part.id, GOLD);
  assert.throws(() => createSpec(state, { group: 'flower', plating: '金色', oil: '黄色', area: '' }));
});
test('send deducts source only; receipt increases target and records explicit loss', () => {
  const state = initialState();
  const order = sendProcessing(state, GOLD, RED, 100);
  assert.equal(getPart(state, GOLD).stock, 100);
  assert.equal(getPart(state, RED).stock, 24);
  receiveProcessing(state, order.id, 98);
  assert.equal(getPart(state, RED).stock, 122);
  assert.equal(order.loss, 2);
  assert.equal(order.status, 'completed');
  assert.deepEqual(state.logs.map(log => log.qty), [98, -100]);
  assert.throws(() => receiveProcessing(state, order.id, 98));
  assert.equal(getPart(state, RED).stock, 122);
});
test('invalid send does not mutate stock, orders, or logs', () => {
  for (const [target, qty] of [[RED, 201], [RED, -1], [RED, 1.5], [GOLD, 10], ['PJ-X-00002-G', 10]]) {
    const state = initialState(), before = structuredClone(state);
    assert.throws(() => sendProcessing(state, GOLD, target, qty));
    assert.deepEqual(state, before);
  }
});
test('invalid receipt does not settle an order', () => {
  const state = initialState(), order = sendProcessing(state, GOLD, RED, 100);
  for (const qty of [-1, 101, 0.5, NaN]) assert.throws(() => receiveProcessing(state, order.id, qty));
  assert.equal(order.status, 'processing');
  assert.equal(getPart(state, RED).stock, 24);
  receiveProcessing(state, order.id, 0);
  assert.equal(order.loss, 100);
});
test('BOM counts only the required color, not available unprocessed stock', () => {
  const state = initialState(), row = requirements(state)[0];
  assert.equal(row.need, 96);
  assert.equal(row.shortage, 72);
  assert.equal(getPart(state, GOLD).stock, 200);
  assert.throws(() => allocate(state));
  assert.deepEqual(state.allocations, {});
});
test('receipt allows allocation without changing physical stock', () => {
  const state = initialState(), order = sendProcessing(state, GOLD, RED, 100);
  receiveProcessing(state, order.id, 98);
  allocate(state);
  assert.equal(getPart(state, RED).stock, 122);
  assert.equal(state.allocations[RED], 96);
  assert.equal(available(state, RED), 26);
  assert.equal(available(state, 'PJ-X-00002-G'), 384);
  assert.throws(() => allocate(state));
  assert.throws(() => sendProcessing(state, RED, GOLD, 27));
  assert.throws(() => updateBom(state, GOLD, 2));
  state.allocations = {};
  assert.equal(available(state, RED), 122);
});
test('repeated processing reuses the same target part; no extra specs created', () => {
  const state = initialState();
  for (let i = 0; i < 2; i++) {
    const order = sendProcessing(state, GOLD, RED, 50);
    receiveProcessing(state, order.id, 49);
  }
  assert.equal(state.parts.length, 7);
  assert.equal(state.orders.length, 2);
  assert.equal(getPart(state, RED).stock, 122);
});
test('changing BOM selects a real part ID and recalculates demand without stock changes', () => {
  const state = initialState(), before = structuredClone(state.parts);
  updateBom(state, 'DEMO-P-004', 1);
  assert.equal(requirements(state)[0].need, 48);
  assert.equal(requirements(state)[0].shortage, 12);
  assert.deepEqual(state.parts, before);
});
