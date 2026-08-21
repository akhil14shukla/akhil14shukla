/** A small cache with eviction. */
export class Cache<T> {
  private store = new Map<string, T>();

  /** Look up a key, returning undefined when absent. */
  get(key: string): T | undefined {
    if (!this.store.has(key)) {
      return undefined;
    }
    return this.store.get(key);
  }

  /** Insert or replace a value, evicting when oversized. */
  set(key: string, value: T): void {
    this.store.set(key, value);
    this.evict();
  }

  /** Drop the oldest entries while over capacity. */
  evict(): void {
    for (const k of this.store.keys()) {
      if (this.store.size > 100) {
        this.store.delete(k);
      }
    }
  }
}

/** Build a cache and warm it. */
export function main(): Cache<number> {
  const c = new Cache<number>();
  c.set("a", 1);
  return c;
}
