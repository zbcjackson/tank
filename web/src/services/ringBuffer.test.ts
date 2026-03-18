import { describe, expect, it } from 'vitest';
import { RingBuffer } from './ringBuffer';

describe('RingBuffer', () => {
  it('starts empty', () => {
    const buf = new RingBuffer<number>(3);
    expect(buf.size).toBe(0);
    expect(buf.drain()).toEqual([]);
  });

  it('push and drain returns items oldest-first', () => {
    const buf = new RingBuffer<number>(5);
    buf.push(1);
    buf.push(2);
    buf.push(3);
    expect(buf.size).toBe(3);
    expect(buf.drain()).toEqual([1, 2, 3]);
    expect(buf.size).toBe(0);
  });

  it('overwrites oldest items when full', () => {
    const buf = new RingBuffer<number>(3);
    buf.push(1);
    buf.push(2);
    buf.push(3);
    buf.push(4); // overwrites 1
    buf.push(5); // overwrites 2
    expect(buf.size).toBe(3);
    expect(buf.drain()).toEqual([3, 4, 5]);
  });

  it('clear resets the buffer', () => {
    const buf = new RingBuffer<string>(3);
    buf.push('a');
    buf.push('b');
    buf.clear();
    expect(buf.size).toBe(0);
    expect(buf.drain()).toEqual([]);
  });

  it('drain after overflow then push works correctly', () => {
    const buf = new RingBuffer<number>(2);
    buf.push(1);
    buf.push(2);
    buf.push(3); // overwrites 1
    buf.drain();
    buf.push(10);
    buf.push(20);
    expect(buf.drain()).toEqual([10, 20]);
  });

  it('works with typed arrays', () => {
    const buf = new RingBuffer<Int16Array>(2);
    const a = new Int16Array([1, 2]);
    const b = new Int16Array([3, 4]);
    buf.push(a);
    buf.push(b);
    const result = buf.drain();
    expect(result).toHaveLength(2);
    expect(Array.from(result[0])).toEqual([1, 2]);
    expect(Array.from(result[1])).toEqual([3, 4]);
  });
});
