# ENV.md — Sandbox Environment

The operator or evaluation harness supplies the deployment environment. Keep
those values. This file supplies defaults for an otherwise unconfigured session;
`AGENTS.md`, `BOOTSTRAP.md`, and `TOOLS.md` reference it.

`/sandbox/.bashrc` is root-owned (mode `444`) in the nemoclaw sandbox,
so do not write a shell init file. The exports below preserve existing values.
The VSS CLI is already installed at `/usr/local/bin/vss`; no PATH repair,
checkout, or dependency installation is needed.

## Exports

```bash
# Sandbox host alias, for Docker Compose deployments only — those
# publish their services on host ports. Skills curl ${HOST_IP} for those
# runtime calls (never localhost, never a literal IP) so the same skill
# works in-sandbox and on bare metal.
export HOST_IP="${HOST_IP-host.openshell.internal}"

# Kubernetes deployments publish nothing on host ports: every HTTP
# surface sits behind one path-based Ingress, so operate skills take the
# Ingress origin as their single public endpoint. It differs per
# deployment. Preserve VSS_PUBLIC_URL, including an explicit empty value;
# only when unset use the harness's explicit VSS_GATEWAY_ORIGIN.
# The deployment notebook can also
# fill this export at upload time. Never replace an operator origin with a guess.
export VSS_PUBLIC_URL="${VSS_PUBLIC_URL-${VSS_GATEWAY_ORIGIN-}}"
```

## Empty VSS_PUBLIC_URL

First check `vss configure show`: an existing CLI configuration may already
name the deployment. If neither the environment nor the CLI configuration names
one, ask the user before a call that requires it. In a non-interactive evaluation,
report the missing configuration and stop. Do not discover or deploy a stack:

> I need the Ingress origin of the VSS deployment you want me to operate.

Then `export VSS_PUBLIC_URL=<answer>` for the session and write it to
`memory/YYYY-MM-DD.md`, so the next session can offer it back instead of
asking again. Keep the port in it: `vss configure` records the origin
verbatim, and the Elasticsearch client rejects a URL without one.

The selected origin must be allowed by the sandbox's policy. A policy denial is
a configuration problem to report; do not change the policy or route around it.
