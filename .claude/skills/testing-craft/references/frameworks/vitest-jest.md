# vitest / jest

The features that change how tests read in vitest / jest, and the specific
traps in it.

```ts
describe('cartTotal', () => {
  it('applies the bulk discount above ten items', () => {
    const cart = makeCart({ items: 11 });
    expect(cartTotal(cart)).toBe(990);
  });

  it.each([
    [0, 0],
    [1, 100],
    [10, 1000],
  ])('charges full price for %i items', (items, expected) => {
    expect(cartTotal(makeCart({ items }))).toBe(expected);
  });
});
```

- `toBe` for primitives and identity, `toEqual` for deep structural equality,
  `toStrictEqual` when `undefined` keys and class identity matter.
- Async: `await expect(fn()).rejects.toThrow(HttpError)` — a forgotten `await`
  makes the assertion silently pass.
- Fake timers (`vi.useFakeTimers()` / `jest.useFakeTimers()`) with
  `advanceTimersByTime` for debounce, retry, and polling logic; always restore
  in `afterEach`.
- `vi.mock('./module')` is hoisted above imports — a common surprise. Prefer
  dependency injection over module mocking where you control the code.
- React: use Testing Library and query the way a user does (`getByRole`,
  `getByLabelText`), not by test id or class name. `userEvent` over `fireEvent`
  so the interaction is realistic.
- Reset state between tests: `restoreMocks: true` and `clearMocks: true` in the
  config, so a stub does not leak into the next file.
