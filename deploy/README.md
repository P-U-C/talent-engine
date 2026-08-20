# deploy

Everything the pipeline needs that is not Python.

It used to live only on the box that ran it: four shell scripts in `~/scripts`,
two systemd units in `/etc/systemd/system`, an ingress file in
`/etc/cloudflared`, and a crontab nobody had written down. The code was in git;
the system was not. Losing the machine would have meant reconstructing the
running shape of this thing from memory.

| File | What it is |
|---|---|
| `install.sh` | idempotent setup. Links the cron scripts back into the repo, checks the credential file, prints the root-owned steps rather than doing them |
| `cron.txt` | the three scheduled jobs, with the reasoning for each schedule |
| `daily-scout.sh` | nightly sourcing run, then recon on what it found |
| `applicant-watch.sh` | rebuilds the board every 15 minutes; alerts when an applicant is stuck unscored |
| `backup-talent-engine.sh` | nightly backup of the audit log, contacts and decisions |
| `systemd/` | the intake service and the tunnel, as they run |
| `cloudflared/sponsorships.yml` | ingress allowlist. `${TUNNEL_ID}` is filled in at install; the credentials JSON never leaves the box |
| `intake.env.example` | every credential the system reads, by name, with what each is for. No values |

`~/scripts/*.sh` are symlinks into this directory, so cron keeps its familiar
paths and an edit here is live immediately. The alternative -- copying -- leaves
you with two files that drift and no way to tell which one actually runs.

Start with [`../docs/PIPELINE.md`](../docs/PIPELINE.md) for what the system does
and the contracts it holds to.
