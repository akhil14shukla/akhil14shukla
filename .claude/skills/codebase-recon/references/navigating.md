# Navigating a codebase: per-ecosystem commands and git archaeology

Read this when the generic grep-then-read loop is not enough — you need to
resolve a symbol across a large project, or work out *why* a piece of code
exists before changing it.

## Contents
- [Finding a definition fast](#finding-a-definition-fast)
- [Per-ecosystem navigation](#per-ecosystem-navigation)
- [Finding all callers before you change a signature](#finding-all-callers-before-you-change-a-signature)
- [Git archaeology: why does this exist](#git-archaeology-why-does-this-exist)
- [Mapping an unfamiliar system](#mapping-an-unfamiliar-system)
- [Signals that tell you where the risk is](#signals-that-tell-you-where-the-risk-is)

## Finding a definition fast

Order these by cost. Stop at the first that answers.

```bash
# 1. The declaration keyword plus the name — usually one hit, near-free
grep -rn "def process_order\|class OrderService" --include='*.py' .
grep -rn "func (s \*Service) Process\|type Service struct" --include='*.go' .

# 2. Restrict to where source lives, so vendored copies and build output
#    do not drown the result
git grep -n "processOrder" -- 'src/**' ':!*.test.*' ':!*_test.go'

# 3. Only then, read the range around the hit
sed -n '120,180p' src/orders/service.py
```

`git grep` is the right default in a repository: it respects `.gitignore`, so it
never searches `node_modules/`, `target/`, `.venv/`, or build artefacts — which
is usually 90% of the bytes and 0% of the answer.

## Per-ecosystem navigation

**Python**
```bash
python -c "import mypkg.mod as m, inspect; print(inspect.getsourcefile(m))"
python -c "import mypkg; help(mypkg.thing)"       # docstring without reading the file
ruff check --select F401 .                        # unused imports reveal dead links
```

**TypeScript / JavaScript**
```bash
npx tsc --noEmit --listFiles | head              # what actually compiles into the build
grep -rn "export function foo\|export const foo" src/
grep -rn "from '.*module-name'" src/             # who imports a module
```
`package.json` `"exports"` tells you the real public surface of a dependency —
more reliable than reading its source.

**Go**
```bash
go doc ./internal/order              # package surface, no file reading
go doc ./internal/order Service.Process
go list -deps ./... | head           # dependency graph
grep -rn "func (s \*Service)" internal/order/
```

**Rust**
```bash
cargo doc --open                     # generated API surface
cargo tree                           # dependency graph with versions
grep -rn "pub fn \|pub struct " src/
```

**Java / Kotlin**
```bash
grep -rn "class OrderService\|interface OrderRepository" --include='*.java' src/main
./gradlew dependencies --configuration runtimeClasspath | head -40
```

**Any language, when a language server is available**: an editor's
go-to-definition and find-references is more accurate than grep for overloaded
names. Use it when you have it; grep is the portable fallback.

## Finding all callers before you change a signature

Changing a function without finding its callers is how a "small" change breaks
the build in four places. Two minutes here saves the round trip.

```bash
git grep -n "processOrder(" -- ':!*test*'        # direct calls
git grep -n "processOrder"                        # plus references, exports, docs
git grep -n "\.process_order\b"                   # method calls
```

Watch for the callers grep cannot see: dynamic dispatch (`getattr`,
reflection, a string in a config or route table), calls from another repository
against a published API, database-stored handler names, and calls from tests
that use string-based mocking. If a symbol is part of a published interface,
grep in your own repository proves nothing about who else depends on it.

## Git archaeology: why does this exist

The single most valuable question about strange-looking code, and the cheapest
way to avoid re-introducing a bug someone already fixed.

```bash
git log --oneline -10 -- path/to/file.py         # recent history of one file
git log -S "retry_limit" --oneline               # commits that ADDED or REMOVED a string
git log -p -1 --format=%B <sha>                  # the message and diff of one commit
git blame -L 120,140 path/to/file.py             # who last touched these lines, and when
git log --oneline --merges -5                    # recent merges, to find the PR
```

`git log -S` ("pickaxe") is the one people forget: it finds the commit that
introduced a specific string, which usually carries the message explaining why.
When you find an odd workaround, run it before removing the workaround.

`git blame` on a line, then reading that commit's message, answers "why is this
here" far more often than reading the surrounding code does. If the message is
useless, the merge commit or the PR it references often is not.

## Mapping an unfamiliar system

```bash
# Where is the weight? Biggest directories by file count
git ls-files | sed 's|/[^/]*$||' | sort | uniq -c | sort -rn | head -20

# Biggest files — usually where the structural problem lives
git ls-files | xargs wc -l 2>/dev/null | sort -rn | head -20

# Entry points
git grep -ln "__main__\|func main(\|fn main()\|export default app"

# The external surface: routes, commands, queues
git grep -n "@app.route\|@router\.\|app.get(\|http.HandleFunc\|@RestController"

# What it talks to
cat .env.example 2>/dev/null; git grep -n "os.environ\|process.env" | head -20
```

Read in this order: manifest (what it depends on) → entry point (how it starts)
→ routes or commands (what it exposes) → one path through the middle. That is
four cheap steps to a working mental model.

## Signals that tell you where the risk is

Before changing anything, these tell you which files deserve care:

```bash
# Most-churned files: high change rate usually means high complexity or high risk
git log --format= --name-only --since='6 months ago' | sort | uniq -c | sort -rn | head -15

# Files changed most often together with the one you are editing — the hidden
# coupling that no import graph shows
git log --format='%H' -- path/to/file.py | while read sha; do
  git show --format= --name-only "$sha"
done | sort | uniq -c | sort -rn | head -10
```

The coupling query lists your own file first (it appears in every commit that
touched it) — ignore that row and read the ones below it.

A file that changes every week is either the heart of the product or an
unstable design; either way, read its tests before touching it. A file that
always changes alongside yours is coupled to it whether or not it imports it —
check whether your change needs a matching one there. That hidden coupling is
invisible to an import graph and is the usual reason a "self-contained" change
breaks something elsewhere.
