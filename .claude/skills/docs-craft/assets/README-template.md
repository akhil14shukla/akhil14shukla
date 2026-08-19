# <project-name>

<!-- One sentence: what this does and for whom. Concrete. A reader decides in
     ten seconds whether this repository is relevant to them.
     Good: "A CLI that syncs Postgres tables into BigQuery on a schedule."
     Bad:  "A project for managing data." -->

<!-- Badges once CI exists: build status, coverage, version, license. -->

## Requirements

<!-- Language version and every external service needed to run this. Finding
     the fourth prerequisite by hitting an error is the most common newcomer
     experience and is entirely avoidable. -->

- <language> <version>
- <database / queue / credentials>

## Quick start

<!-- The shortest path from clone to running. Every command copy-pasteable, in
     this order, from a clean clone. Run them yourself before committing this. -->

```bash
git clone <url> && cd <project>
<install command>
cp .env.example .env      # fill in the values described below
<run command>
```

<!-- Say what success looks like: the output, the URL, the file produced. -->

## Usage

<!-- Two or three real examples with real values. Link to docs/ for depth. -->

```bash
<a real command someone will actually run>
```

## Configuration

<!-- Every environment variable. Keep in sync with .env.example. -->

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | yes | — | Postgres connection string |
| `LOG_LEVEL` | no | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

## Development

```bash
<install dev dependencies>
<format> && <lint> && <typecheck> && <test>
```

<!-- One command to run the tests. Its absence is why contributors submit
     untested changes. -->

## Project layout

<!-- One line per top-level directory so a newcomer can navigate without
     opening files. -->

```
src/        <what lives here>
tests/      <what lives here>
docs/       <what lives here>
scripts/    <what lives here>
```

## Documentation

<!-- Delete the lines that do not exist yet. -->

- [Getting started](docs/tutorials/getting-started.md)
- [How-to guides](docs/how-to/)
- [Reference](docs/reference/)
- [Architecture and decisions](docs/adr/)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

<!-- Name the license and link the file. Without a LICENSE file, nobody may
     legally use this code. -->
