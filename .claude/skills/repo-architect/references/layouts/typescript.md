# TypeScript layouts

Annotated trees for TypeScript projects — Node service, React application, and
monorepo. Copy the one that matches and adapt it; the comments explain why
each piece is where it is.

## TypeScript: Node service

```
service/
├── package.json  pnpm-lock.yaml  tsconfig.json  .env.example
├── src/
│   ├── index.ts             # composition root: build deps, start server
│   ├── config.ts            # env parsed + validated with zod, exported typed
│   ├── orders/
│   │   ├── orders.routes.ts
│   │   ├── orders.service.ts
│   │   ├── orders.repository.ts
│   │   ├── orders.types.ts
│   │   └── orders.test.ts
│   └── shared/  db.ts  logger.ts  errors.ts  http.ts
├── tests/                   # integration/e2e; unit tests sit beside their source
└── .github/workflows/ci.yml
```

Co-locate unit tests with source (`orders.service.test.ts`) — a file and its test
move together, and an untested file is visible at a glance. Keep integration
tests separate since they need infrastructure.

## TypeScript: React application

```
app/
├── src/
│   ├── main.tsx  App.tsx
│   ├── features/            # by feature, each self-contained
│   │   └── checkout/
│   │       ├── CheckoutPage.tsx
│   │       ├── components/  PaymentForm.tsx
│   │       ├── hooks/       useCheckout.ts
│   │       ├── api.ts
│   │       └── types.ts
│   ├── components/          # genuinely generic, no domain knowledge: Button, Modal
│   ├── lib/                 # framework-agnostic helpers (formatting, http client)
│   ├── hooks/               # generic hooks used across features
│   └── styles/
└── tests/e2e/
```

The distinction that keeps this clean: `components/` may not import from
`features/`. If a "generic" component knows what an order is, it belongs in that
feature. A feature directory should be deletable in one command.

## TypeScript: monorepo

```
repo/
├── pnpm-workspace.yaml  turbo.json  tsconfig.base.json
├── apps/
│   ├── web/                 # may import packages/*, never apps/*
│   └── api/
├── packages/
│   ├── ui/                  # may import packages/*, never apps/*
│   ├── domain/              # shared types and business rules — no framework code
│   └── config/              # shared eslint/tsconfig/prettier presets
└── .github/workflows/ci.yml
```

Use workspace protocol references (`"@repo/domain": "workspace:*"`) and
TypeScript project references so builds are incremental and the dependency graph
is explicit. Enforce the "apps never import apps" rule in CI — it is the only
thing standing between a monorepo and a distributed monolith.
