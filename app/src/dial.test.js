import assert from 'node:assert/strict'
import { test } from 'node:test'
import { angleToValue, arcPath, keyToValue, pointerAngle, valueToAngle } from './dial.js'

test('dial maps the 270° arc to 1–100 % clockwise from bottom-left', () => {
  assert.equal(valueToAngle(1), 135)
  assert.equal(valueToAngle(100), 405)
  assert.equal(angleToValue(135), 1)
  assert.equal(angleToValue(-90), 51) // straight up is the middle
  assert.equal(angleToValue(45), 100)
  assert.equal(angleToValue(180), 18) // 1 + 45/270 * 99 = 17.5
  for (const value of [1, 13, 50, 87, 100]) assert.equal(angleToValue(valueToAngle(value)), value)
})

test('pointer angles use screen coordinates (y grows downwards)', () => {
  assert.equal(pointerAngle(10, 0, 0, 0), 0)
  assert.equal(pointerAngle(0, 10, 0, 0), 90)
  assert.equal(pointerAngle(0, -10, 0, 0), -90)
})

test('the gap at the bottom snaps to the nearer end', () => {
  assert.equal(angleToValue(60), 100)
  assert.equal(angleToValue(89), 100)
  assert.equal(angleToValue(91), 1)
  assert.equal(angleToValue(120), 1)
})

test('dragging never jumps across the gap', () => {
  assert.equal(angleToValue(150, 98), 100)
  assert.equal(angleToValue(30, 3), 1)
  assert.equal(angleToValue(-80, 50), 54)
  // Moving into the gap from either end stops at that end.
  assert.equal(angleToValue(70, 95), 100)
  assert.equal(angleToValue(110, 4), 1)
})

test('a fast move over half the dial is accepted when it does not cross the gap', () => {
  assert.equal(angleToValue(-26.57, 22), 74)
  assert.equal(angleToValue(235, 90), 38) // 143° back along the arc
})

test('keyboard steps stay within 1–100', () => {
  assert.equal(keyToValue('ArrowUp', 50), 51)
  assert.equal(keyToValue('ArrowLeft', 50, { shift: true }), 40)
  assert.equal(keyToValue('PageUp', 95), 100)
  assert.equal(keyToValue('PageDown', 4), 1)
  assert.equal(keyToValue('Home', 50), 1)
  assert.equal(keyToValue('End', 50), 100)
  assert.equal(keyToValue('Enter', 50), null)
})

test('arc path is a large clockwise arc', () => {
  assert.match(arcPath(130, 130, 100), /^M 59\.289 200\.711 A 100 100 0 1 1 200\.711 200\.711$/)
})
