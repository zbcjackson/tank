/**
 * Fixed-size circular buffer. When full, oldest items are overwritten.
 */
export class RingBuffer<T> {
  private buf: (T | undefined)[];
  private head = 0;
  private count = 0;
  private capacity: number;

  constructor(capacity: number) {
    this.capacity = capacity;
    this.buf = new Array<T | undefined>(capacity);
  }

  push(item: T): void {
    this.buf[this.head] = item;
    this.head = (this.head + 1) % this.capacity;
    if (this.count < this.capacity) this.count++;
  }

  /** Return all items oldest-first and reset. */
  drain(): T[] {
    if (this.count === 0) return [];
    const start = (this.head - this.count + this.capacity) % this.capacity;
    const result: T[] = [];
    for (let i = 0; i < this.count; i++) {
      result.push(this.buf[(start + i) % this.capacity] as T);
    }
    this.clear();
    return result;
  }

  clear(): void {
    this.head = 0;
    this.count = 0;
  }

  get size(): number {
    return this.count;
  }
}
