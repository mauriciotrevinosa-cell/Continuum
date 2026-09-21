# Paid image generation: the runbook

Everything between "nothing costs money" and the first foundation batch, in
the order it has to happen. Each step is safe to stop at.

Nothing here has been run against the vendor. No request has been made, no
money has been spent, and the batch has not been started.

## 0. What is already true

* The provider (`google.image`) is wired behind Continuum's own contracts. It
  receives a materialized request and returns pixels; it never chooses
  references, never reads the Vault, never decides what a panel means.
* **The only secret you supply is the API key.** Endpoint, method, both model
  tiers and the licence note ship with defaults.
* Having the provider registered is not permission to spend. Three separate
  gates still stand between a key and a charge: the locality policy, the
  spend policy, and the ledger.

| Tier | Setting | Used for |
| --- | --- | --- |
| HIGH (authority) | `CONTINUUM_GOOGLE_IMAGE_MODEL_HIGH` | production character sheets, multi-reference calibration, anything later work is built on |
| CHEAP (exploration) | `CONTINUUM_GOOGLE_IMAGE_MODEL_CHEAP` | exploration, comparison batches, throwaway candidates |

The cheap tier is never the authority for a sheet or for multi-reference
calibration. The smoke test and every `CHARACTER_SHEET` item default to HIGH.

## 1. Bring the database up to the current schema

Two migrations (0019, 0020) add the spend ledger, props and training tables.
They are additive, and the script backs up first and verifies after.

```bash
docker compose up -d db
uv run python scripts/migrate_application_db.py            # dry run: shows what is pending
uv run python scripts/migrate_application_db.py --apply    # back up, migrate, verify
```

The backup lands in `backups/` (git-ignored - it holds the real catalogue).
If `pg_dump` is not on PATH the script stops and prints the `docker exec`
equivalent rather than migrating without a backup.

## 2. Put the key in `.env`

```bash
CONTINUUM_GOOGLE_API_KEY=<your key>
```

That is the whole provider configuration. Check it:

```bash
uv run python scripts/paid_image_smoke_test.py
```

With no key it prints `Not configured yet. Set: CONTINUUM_GOOGLE_API_KEY`.

## 3. Open the two policies, deliberately

Remote is not paid and paid is not remote, so both are separate decisions:

```bash
CONTINUUM_LOCALITY_POLICY=REMOTE_ALLOWED
CONTINUUM_SPEND_POLICY=PAID_ALLOWED_WITH_CAP
CONTINUUM_SPEND_CAP_USD=10.0
```

Until both are set the smoke test stops with the axis that blocked it and
reserves nothing.

## 4. Record the prices

Continuum will not invent a price, and it refuses to spend on a request whose
cost it does not know. Read the provider's current pricing page, then:

```bash
uv run python scripts/configure_image_prices.py \
    --high-usd <USD per image> --cheap-usd <USD per image> \
    --confirmed-on <YYYY-MM-DD> --write .env
```

It prints what each tier will cost, how many images the cap covers, and the
exact `CONTINUUM_IMAGE_PRICE_LIST` line. Every reservation records the price
and the note, so a wrong number is visible in the ledger afterwards.

A row priced at zero is refused: it would reserve nothing and bill for real.

## 5. One paid image

```bash
uv run python scripts/paid_image_smoke_test.py --execute --approved-by "<your name>"
```

In order: resolve the provider by name **through the policy**, price it,
reserve the estimate under the cap, make exactly one request, store the bytes
content-addressed, record a reference carrying the full lineage (provider,
model, tier, endpoint, method, prompt, seed, size, licence, the spend entry it
was paid from), settle the reservation, stop.

The image is a candidate. Nothing approves it - look at it first.

Without `--execute` the same command is a dry run: it prints the URL it would
POST to, the estimate and the remaining budget, and reserves nothing. If the
request fails, the reservation is released and the budget is untouched.

## 6. The foundation batch

Only after an image you are happy with.

```bash
cp docs/foundation-batch.example.json <somewhere outside the repo>/batch.json
# edit it: your cast, your outfits, your props, your CAL ids

uv run python scripts/foundation_batch.py --manifest <path>/batch.json
uv run python scripts/foundation_batch.py --manifest <path>/batch.json \
    --reserve --approved-by "<your name>"
```

The first command prices every item and checks the total against what is left
of the cap; it reserves nothing. The second holds the money - every item or
none - and still renders nothing: each artifact is produced afterwards through
its own ordinary flow, and each one settles its own reservation when it runs.

Keep your real manifest out of the repository. It names your cast.

## 7. Where the cap is actually enforced

`continuum_production.budget.paid_call` wraps every call that can reach a paid
provider - the character-sheet renderer, the panel-stage renderer and the
smoke test. It behaves in three ways:

* a provider that costs nothing is called with nothing held;
* a **paid provider with no ledger is refused**, not billed. A caller that
  forgot the budget must not be the caller that discovers the budget did not
  apply;
* otherwise: reserve the estimate, call, settle on success, release on
  failure.

The worker builds the ledger from the settings, so a paid render requested
through the ordinary UI is held and settled exactly like the smoke test.

## 8. What is still outside Continuum

* Billing and quota on the vendor account.
* Confirming the current per-image prices.
* Looking at the image and deciding.
