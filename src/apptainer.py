#/usr/bin/env python3
from pathlib import Path

from charms.operator_libs_linux.v0 import apt


APPTAINER_PPA_KEY: str = """
-----BEGIN PGP PUBLIC KEY BLOCK-----
Comment: Hostname: 
Version: Hockeypuck 2.1.0-223-gdc2762b

xsFNBGPKLe0BEADKAHtUqLFryPhZ3m6uwuIQvwUr4US17QggRrOaS+jAb6e0P8kN
1clzJDuh3C6GnxEZKiTW3aZpcrW/n39qO263OMoUZhm1AliqiViJgthnqYGSbMgZ
/OB6ToQeHydZ+MgI/jpdAyYSI4Tf4SVPRbOafLvnUW5g/vJLMzgTAxyyWEjvH9Lx
yjOAXpxubz0Wu2xcoefN0mKCpaPsa9Y8xmog1lsylU+H/4BX6yAG7zt5hIvadc9Z
Y/vkDLh8kNaEtkXmmnTqGOsLgH6Nc5dnslR6Gwq966EC2Jbw0WbE50pi4g21s6Wi
wdU27/XprunXhhLdv6PYUaqdXxPRdBh+9u0LmNZsAyUxT6EgN05TAWFtaMOz7I3B
V6IpHuLqmIcnqulHrLi+0D/aiCv53WEZrBRmDBGX7p52lcyS+Q+LFf0+iYeY7pRG
fPXboBDr+6DelkYFIxam06purSGR3T9RJyrMP7qMWiInWxcxBoCMNfy8VudP0DAy
r2yXmHZbgSGjfJey03dnNwQH7huBcQ1VLEqtL+bjn3HubmYK87FltX7xomETFqcl
QmiT+WBttFRGtO6SFHHiBXOXUn0ihwabtr6gRKeJssCnFS3Y46RDv4z3Je92roLt
TPY8F9CgZrGiAoKq530BzEhJB6vfW3faRnLKdLePX/LToCP0g2t2jKwkzQARAQAB
zRtMYXVuY2hwYWQgUFBBIGZvciBBcHB0YWluZXLCwY4EEwEKADgWIQT2sPUZPU8z
Ae9JH/Cv42U0/GIYrgUCY8ot7QIbAwULCQgHAgYVCgkICwIEFgIDAQIeAQIXgAAK
CRCv42U0/GIYrut4EAC06vTJP2wgnh3BIZ3n2HKaSp4QsuYKS7F7UQJ5Yt+PpnKn
Pgjq3R4fYzOHyASv+TCj9QkMaeqWGWb6Zw0n47EtrCW9U5099Vdk2L42KjrqZLiW
qQ11hwWXUlc1ZYSOb0J4WTumgO6MrUCFkmNrbRE7yB42hxr/AU/XNM38YjN2NyOK
2gvORRKFwlLKrjE+70HmoCW09Yk64BZl1eCubM/qy5tKzSlC910uz87FvZmrGKKF
rXa2HGlO4O3Ty7bMSeRKl9m1OYuffAXNwp3/Vale9eDHOeq58nn7wU9pSosmqrXb
SLOwqQylc1YoLZMj+Xjx644xm5e2bhyD00WiHeqHmvlfQQWCWaPt4i4K0nJuYXwm
BCA6YUgSfDZJfg/FxJdU7ero5F9st2GK4WDBiz+1Eftw6Ik/WnMDSxXaZ8pwnd9N
+aAEc/QKP5e8kjxJMC9kfvXGUVzZuMbkUV+PycZhUWl4Aelua91lnTicVYfpuVCC
GqY0StWQeOxLJneI+1FqLFoBOZghzoTY5AYCp99RjKqQvY1vF4uErltmNeN1vtBm
CZyDOLQuQfqWWAunUwXVuxMJIENSVeLXunhu9ac24Vnf2rFqH4XVMDxiKc6+sv+v
fKpamSQOUSmfWJTnry/LiYbspi1OB2x3GQk3/4ANw0S4L83A6oXHUMg8x7/sZw==
=E71P
-----END PGP PUBLIC KEY BLOCK-----
"""


def os_series() -> str:
    """Return the operating system series"""
    OS_RELEASE = Path("/etc/os-release").read_text().split("\n")
    OS_RELEASE_CTXT = {
        k: v.strip("\"")
        for k, v in [item.split("=") for item in OS_RELEASE if item != '']
    }
    return OS_RELEASE_CTXT["VERSION_CODENAME"]


def install_apptainer() -> None:
    """Install the apptainer package using libapt."""

    package_name: str = "apptainer"
    keyring_path: Path = Path("/usr/share/keyrings/apptainer.asc")
    ppa_url: str = "https://ppa.launchpadcontent.net/apptainer/ppa/ubuntu"
    sources_list: str = f"deb [signed-by={keyring_path}] {ppa_url} {os_series()} main"

    # Install the key.
    if keyring_path.exists():
        keyring_path.unlink()
    keyring_path.write_text(APPTAINER_PPA_KEY)

    # Add the repo.
    repositories = apt.RepositoryMapping()
    repo = apt.DebianRepository.from_repo_line(sources_list)
    repositories.add(repo)

    # Install the apptainer package.
    try:
        # Run `apt-get update`
        apt.update()
        apt.add_package("apptainer")
    except apt.PackageNotFoundError:
        logger.error("a specified package not found in package cache or on system")
    except PackageError as e:
        logger.error("could not install package. Reason: %s", e.message)
