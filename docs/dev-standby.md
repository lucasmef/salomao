# Dev standby on the shared VPS

Development workflows prepare the current code and database state, then keep dev
services stopped to save RAM. Production deploys are unchanged and still restart
and healthcheck production services.

## Services

- Salomao dev: `salomao-dev.service` on port `8101`
- Salomao Inter dev: `salomao-inter-dev.service` on port `8102`
- doit dev: `doit-dev.service` on port `8111`

## Stop dev services

Run these commands in an interactive SSH session with sudo privileges:

```bash
sudo systemctl stop salomao-dev.service salomao-inter-dev.service doit-dev.service
```

## Prevent dev services from starting on boot

```bash
sudo systemctl disable salomao-dev.service salomao-inter-dev.service doit-dev.service
```

## Start dev temporarily

```bash
sudo systemctl start salomao-dev.service salomao-inter-dev.service doit-dev.service
```

Healthchecks:

```bash
curl --fail http://127.0.0.1:8101/api/v1/health
curl --fail http://127.0.0.1:8111/api/health
```

## Return dev to standby after use

```bash
sudo systemctl stop salomao-dev.service salomao-inter-dev.service doit-dev.service
```

## Check status

```bash
systemctl is-active salomao-dev.service salomao-inter-dev.service doit-dev.service
systemctl is-enabled salomao-dev.service salomao-inter-dev.service doit-dev.service
```

`systemctl start` does not enable startup on boot. If the services were disabled,
they stay disabled after temporary use.
