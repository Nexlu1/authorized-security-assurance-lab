# Local Target Containment Baseline

This is a planning control. It does not authorize target activation or technical security testing.

## Planned target

- OWASP WebGoat `v2025.3`
- official image `webgoat/webgoat:v2025.3`
- owned local computer only
- synthetic lab-only data and credentials
- WebGoat mapping `127.0.0.1:8080:8080`
- WebWolf mapping `127.0.0.1:9090:9090`

## Network checks required before activation

Current Docker documentation states that publishing without an explicit host address normally exposes a published port on all host interfaces. Explicit loopback publishing (`127.0.0.1`) is therefore required for this lab.

Docker also warns that releases older than Engine 28.0.0 had a same-L2 reachability issue for ports published to localhost. The engine version must be checked before relying on loopback publishing alone.

Do not rely on the requested `docker run` command as proof of containment. Verify the effective port mappings and network mode after startup.

The lab must not use host-network mode, daemon `allow-direct-routing`, bridge `trusted_host_interfaces`, or another deliberate direct-routing configuration that defeats the intended local-only boundary.

Sources rechecked **2026-08-25** immediately before G1 activation preflight; current Docker port-publishing guidance continues to state that explicit `127.0.0.1` publishing restricts access to the Docker host and continues to carry the pre-28.0.0 same-L2 warning:

- https://docs.docker.com/engine/network/port-publishing/
- https://docs.docker.com/engine/network/drivers/host/

## Stop conditions

Stop activation if the effective bind is non-loopback, host/direct-routing semantics are unexpected, a real credential or real data appears, or local-only reachability cannot be established confidently.
