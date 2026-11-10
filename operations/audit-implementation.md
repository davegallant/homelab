# Configuration audit implementation

Execute on local main, in separate commits by concern. Do not push or deploy.

- Preserve Compose rollback images; move image cleanup to opt-in maintenance.
- Add a rendered Grafana alert for watchdog last-success age, absence and suspension.
- Derive an inventory from tracked Applications and Ansible imports; validate a
  small lifecycle catalog instead of duplicating deployment configuration.
- Add a read-only live retirement report for retained PVCs and missing owners.
- Remove obsolete runner pilot prose while retaining current trust constraints.
- Document isolated restore acceptance criteria for SQL, SQLite and mixed NAS data.
- Define exposure, monitoring, retirement and incident-artifact retention patterns.

Use existing tools, test new Python behavior with fixtures before implementation,
run repository checks and review each diff before committing. No service is removed
without live ownership and usage evidence. Historical material remains available
until its recovery value has been assessed. Live restore drills require isolated
resources and explicit handling of production identities.
