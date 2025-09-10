# ProtonVPN Helper

A simple tool to authenticate with ProtonVPN and fetch logical servers.

## Building

Build the container image using Podman:

```bash
podman build -t protonvpn-helper .
```

## Running

Set the required environment variables:

- `PROTON_USERNAME`: Your ProtonVPN username or email
- `PROTON_PASSWORD`: Your ProtonVPN password

Run the container, mounting a volume to access the output file:

```bash
podman run --rm -e PROTON_USERNAME -e PROTON_PASSWORD -v $(pwd):/output protonvpn-helper
```

The script will authenticate and write the logical servers to `/output/server_list.json`.
