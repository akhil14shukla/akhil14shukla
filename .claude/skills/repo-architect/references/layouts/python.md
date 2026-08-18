# Python layouts

Annotated trees for Python projects — library, CLI, web service, and data/ML.
Copy the one that matches and adapt it; the comments explain why each piece is
where it is, so you can deviate knowingly rather than cargo-culting.

## Python: library

```
mylib/
├── pyproject.toml           # metadata, deps, and every tool's config
├── uv.lock                  # committed
├── README.md  LICENSE  CHANGELOG.md  .gitignore  .editorconfig
├── src/
│   └── mylib/
│       ├── __init__.py      # the public API: import and re-export, define __all__
│       ├── py.typed         # marks the package as typed so consumers get checking
│       ├── _internal.py     # leading underscore = private, freely changeable
│       ├── models.py
│       └── errors.py        # one exception hierarchy, exported from __init__
├── tests/
│   ├── conftest.py          # shared fixtures
│   └── test_models.py
├── docs/
└── .github/workflows/ci.yml
```

`src/` is not optional for a library: without it, tests import the source
directory rather than the installed package, so packaging bugs (a missing
module, an uncommitted data file) ship undetected. `py.typed` is what makes your
annotations visible to consumers — without it they get `Any` for your whole API.

`__init__.py` is your API contract. Import the names you intend people to use
and list them in `__all__`; everything else stays private and can change without
a major version.

## Python: CLI tool

```
mytool/
├── pyproject.toml           # [project.scripts] mytool = "mytool.cli:main"
├── src/mytool/
│   ├── __init__.py
│   ├── cli.py               # argument parsing and exit codes ONLY
│   ├── commands/            # one module per subcommand
│   │   ├── build.py
│   │   └── deploy.py
│   ├── core/                # the actual logic — importable, testable, no argparse
│   └── config.py            # load + validate config in one place
└── tests/
```

The separation that matters: `cli.py` translates argv into typed arguments and
calls into `core/`. Because `core/` knows nothing about argparse, it is testable
without subprocesses and reusable as a library. `main()` returns an exit code
and is invoked by `raise SystemExit(main())`.

## Python: web service

```
myservice/
├── pyproject.toml  docker-compose.yml  Dockerfile  .env.example
├── src/myservice/
│   ├── main.py              # app factory + wiring only; no business logic
│   ├── config.py            # env → typed settings object, validated at startup
│   ├── orders/              # a domain: everything about orders lives here
│   │   ├── router.py        # HTTP layer: parse, validate, call service, respond
│   │   ├── service.py       # use cases — the only place business rules live
│   │   ├── models.py        # domain types
│   │   ├── schemas.py       # request/response shapes (pydantic) — boundary only
│   │   └── repository.py    # persistence for this domain
│   ├── payments/            # same shape
│   └── shared/
│       ├── db.py  logging.py  errors.py  middleware.py
├── migrations/              # versioned, forward-only, reviewed
├── tests/
│   ├── unit/                # fast, no I/O
│   └── integration/         # real database, marked so they can be skipped locally
└── .github/workflows/ci.yml
```

`router.py` contains no `if` about business meaning. `service.py` contains no
`Request`/`Response`. That line is what lets you test pricing rules without
booting a web server, and it is the first thing to check in review.

## Python: data / ML project

```
project/
├── pyproject.toml
├── README.md                # what question this answers, and how to reproduce it
├── data/                    # ALL git-ignored except the schema/README
│   ├── raw/                 # immutable; never write here after download
│   ├── interim/
│   └── processed/
├── notebooks/               # exploration only, numbered: 01-explore-signups.ipynb
├── src/project/
│   ├── data/                # loading + cleaning, importable by notebooks
│   ├── features/
│   ├── models/              # train.py, predict.py, evaluate.py
│   └── pipeline.py          # the reproducible end-to-end run
├── configs/                 # experiment configs, versioned
├── tests/
└── models/                  # serialised artefacts, git-ignored (DVC/S3/registry)
```

The rule that makes data projects reproducible: **notebooks import from `src/`,
never the reverse, and no logic lives only in a notebook.** A notebook is a lab
notebook — a record of exploration. The moment a transformation matters, it moves
into `src/` where it can be tested and re-run. Raw data is immutable; every
derived artefact must be regenerable by running the pipeline, and the README
must say exactly how.
